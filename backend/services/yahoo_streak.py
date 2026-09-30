"""Consecutive-failure watcher for the Yahoo rate limit.

Yahoo answering HTTP 429 is a *silent* failure: the run completes, the report
is written, and every price-derived column is N/A. With the systemd timer
running daily, several days of that would pass unnoticed unless someone read
the report. This tracker turns it into a state machine with an explicit
alert.

State (``data/state/yahoo_health_streak.json``)::

    {
      "consecutive_failures": 3,
      "first_failure_at": "2026-09-25T07:00:00Z",
      "last_failure_at":  "2026-09-28T06:00:00Z",
      "last_success_at":  "2026-09-24T06:00:00Z",
      "alerted": true
    }

Rules:

- a failed preflight increments the streak; the first failure of a streak
  records ``first_failure_at``;
- a successful preflight resets the streak to 0, clears ``alerted`` and
  records ``last_success_at``;
- when the streak reaches ``yahoo_429_streak_threshold`` the alert fires
  **once per streak** (``alerted``), and a marker file
  ``data/alerts/yahoo_429_active.flag`` is created for anything external to
  poll (cron, dashboard, a human);
- the marker is removed on recovery.

Only runs that actually tried to fetch prices count: ``--no-prices`` skips the
streak entirely rather than reporting a success it did not verify.

The file and the marker are both under ``data/`` and gitignored. Nothing here
performs I/O beyond reading and writing those two small JSON/text files.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("backend.yahoo_streak")

DEFAULT_THRESHOLD = 3
DEFAULT_STATE_PATH = "data/state/yahoo_health_streak.json"
DEFAULT_FLAG_PATH = "data/alerts/yahoo_429_active.flag"

STATE_VERSION = "1"


def is_rate_limit(health) -> bool:
    """True when a failed preflight was actually a rate limit.

    A preflight can fail for very different reasons and they must not be
    conflated: a DNS or TLS failure is a local network problem, and calling it
    a "429" would raise a rate-limit alarm for the wrong cause (observed live:
    a temporary name-resolution failure reported as HTTP 429). Only an explicit
    429 (or a reason that says so) counts as a rate limit.
    """
    status = getattr(health, "http_status", None)
    if status == 429:
        return True
    reason = str(getattr(health, "reason", "") or "").lower()
    return "429" in reason or "rate limit" in reason or "too many requests" in reason


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_alerts_config(path: str | None = None) -> int:
    """Read ``yahoo_429_streak_threshold`` from config/alerts.yaml.

    Same shape as :func:`backend.services.refresh_service.load_refresh_config`:
    flat ``key: value``, parsed without a YAML dependency, missing file or
    keys fall back to :data:`DEFAULT_THRESHOLD`, and the environment variable
    ``YAHOO_429_STREAK_THRESHOLD`` wins over the file.
    """
    raw = os.environ.get("YAHOO_429_STREAK_THRESHOLD", "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass

    if path is None:
        root = Path(__file__).resolve().parents[2]
        path = str(root / "config" / "alerts.yaml")
    if not os.path.exists(path):
        return DEFAULT_THRESHOLD
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.split("#", 1)[0].strip()
                if not line or ":" not in line:
                    continue
                key, _, value = line.partition(":")
                if key.strip().lower() == "yahoo_429_streak_threshold":
                    try:
                        return max(1, int(value.strip()))
                    except ValueError:
                        return DEFAULT_THRESHOLD
    except OSError as exc:
        logger.warning("yahoo streak: could not read %s: %s", path, exc)
    return DEFAULT_THRESHOLD


@dataclass
class StreakUpdate:
    """Outcome of one preflight observation."""

    state: dict[str, Any] = field(default_factory=dict)
    alert_triggered: bool = False
    recovered: bool = False
    threshold: int = DEFAULT_THRESHOLD

    @property
    def consecutive_failures(self) -> int:
        return int(self.state.get("consecutive_failures", 0))

    @property
    def alerted(self) -> bool:
        return bool(self.state.get("alerted", False))

    def report_lines(self) -> list[str]:
        """Markdown lines for the report (empty when there is nothing to say)."""
        if not self.alerted:
            return []
        state = self.state
        rate_limited = bool(state.get("rate_limited", True))
        kind = "HTTP 429 (rate limit)" if rate_limited else "an unrelated failure"
        lines = [
            (
                f"Yahoo has been unavailable for the last "
                f"**{self.consecutive_failures} consecutive runs** "
                f"(threshold {self.threshold}) — {kind}."
            ),
            f"First failure: {state.get('first_failure_at') or 'unknown'} · "
            f"Last failure: {state.get('last_failure_at') or 'unknown'}"
            + (
                f" · Reason: {state.get('last_failure_reason')}"
                if state.get("last_failure_reason")
                else ""
            ),
            (
                "Impact: P/E, P/B, FCF yield, EV/EBIT and margin of safety are N/A, "
                "and `rank_score` loses its margin-of-safety and momentum "
                "components, so `BUY_SIGNAL` alerts can be suppressed."
            ),
            (
                "Action: verify manually with "
                "`curl -s -o /dev/null -w '%{http_code}\\n' -H 'User-Agent: Mozilla/5.0' "
                "'https://query1.finance.yahoo.com/v8/finance/chart/AAPL"
                "?range=1d&interval=1d'`, then re-run "
                "`python -m scripts.daily_workflow --universe sp500 --limit 20`."
            ),
        ]
        if not rate_limited:
            lines.insert(
                2,
                "> Not a rate limit: the preflight failed for another reason "
                "(DNS, TLS, timeout). Do not wait for a rate-limit window; "
                "check the local network first.",
            )
        return lines


class YahooStreakTracker:
    """Persistent consecutive-failure counter for the Yahoo preflight."""

    def __init__(
        self,
        state_path: str | os.PathLike[str] = DEFAULT_STATE_PATH,
        flag_path: str | os.PathLike[str] = DEFAULT_FLAG_PATH,
        threshold: int = DEFAULT_THRESHOLD,
        enabled: bool = True,
    ):
        self.state_path = Path(state_path)
        self.flag_path = Path(flag_path)
        self.threshold = max(1, int(threshold))
        self.enabled = bool(enabled)

    # ------------------------------------------------------------------
    def load(self) -> dict[str, Any]:
        """Stored state, or a fresh one. A corrupt file is never fatal."""
        blank = {
            "version": STATE_VERSION,
            "consecutive_failures": 0,
            "first_failure_at": None,
            "last_failure_at": None,
            "last_success_at": None,
            "alerted": False,
        }
        if not self.enabled:
            return blank
        try:
            with open(self.state_path, encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                return blank
        except FileNotFoundError:
            return blank
        except Exception as exc:  # noqa: BLE001 — corrupt state must not block
            logger.warning(
                "yahoo streak: unreadable state %s: %s", self.state_path, exc
            )
            return blank
        blank.update({k: v for k, v in data.items() if k in blank})
        try:
            blank["consecutive_failures"] = int(blank.get("consecutive_failures", 0))
        except (TypeError, ValueError):
            blank["consecutive_failures"] = 0
        blank["alerted"] = bool(blank.get("alerted", False))
        return blank

    def save(self, state: dict[str, Any]) -> None:
        if not self.enabled:
            return
        state = {**state, "version": STATE_VERSION, "updated_at": _now_iso()}
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_name(self.state_path.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(state, handle, indent=2)
            os.replace(tmp, self.state_path)
        except Exception as exc:  # noqa: BLE001 — telemetry must never break a run
            logger.warning("yahoo streak: could not write %s: %s", self.state_path, exc)

    # ------------------------------------------------------------------
    def _write_flag(self, text: str) -> None:
        try:
            self.flag_path.parent.mkdir(parents=True, exist_ok=True)
            self.flag_path.write_text(text, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("yahoo streak: could not write %s: %s", self.flag_path, exc)

    def _clear_flag(self) -> bool:
        """Remove the marker; True when one was actually there."""
        try:
            if self.flag_path.exists():
                self.flag_path.unlink()
                return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("yahoo streak: could not remove %s: %s", self.flag_path, exc)
        return False

    # ------------------------------------------------------------------
    def record_failure(
        self, reason: str = "", rate_limited: bool = True
    ) -> StreakUpdate:
        """Register a failed preflight; fires the alert at the threshold.

        ``rate_limited`` records *why* it failed, so a DNS or TLS error never
        raises a rate-limit alarm (see :func:`is_rate_limit`).
        """
        if not self.enabled:
            return StreakUpdate(state=self.load(), threshold=self.threshold)
        state = self.load()
        streak = int(state.get("consecutive_failures", 0)) + 1
        state["consecutive_failures"] = streak
        state["last_failure_at"] = _now_iso()
        state["last_failure_reason"] = reason or state.get("last_failure_reason")
        state["rate_limited"] = bool(rate_limited)
        if not state.get("first_failure_at"):
            state["first_failure_at"] = state["last_failure_at"]
        state["alerted"] = bool(state.get("alerted", False))

        triggered = False
        if streak >= self.threshold and not state["alerted"]:
            state["alerted"] = True
            triggered = True
            kind = "rate limit (HTTP 429)" if rate_limited else "unavailable"
            self._write_flag(
                f"Yahoo {kind} for {streak} consecutive runs.\n"
                f"rate_limited: {str(bool(rate_limited)).lower()}\n"
                f"first_failure_at: {state.get('first_failure_at')}\n"
                f"last_failure_at: {state.get('last_failure_at')}\n"
                f"threshold: {self.threshold}\n"
                f"reason: {state.get('last_failure_reason') or 'unknown'}\n"
            )
            logger.warning(
                "Yahoo %s alert: %d consecutive failures (threshold %d)",
                kind,
                streak,
                self.threshold,
            )
        self.save(state)
        return StreakUpdate(
            state=state,
            alert_triggered=triggered,
            recovered=False,
            threshold=self.threshold,
        )

    def record_success(self) -> StreakUpdate:
        """Register a working preflight: reset the streak, clear the alert."""
        if not self.enabled:
            return StreakUpdate(state=self.load(), threshold=self.threshold)
        state = self.load()
        was_failing = int(state.get("consecutive_failures", 0)) > 0
        state["consecutive_failures"] = 0
        state["first_failure_at"] = None
        state["last_failure_at"] = None
        state["last_success_at"] = _now_iso()
        state["alerted"] = False
        state.pop("last_failure_reason", None)
        removed = self._clear_flag()
        self.save(state)
        if was_failing:
            logger.info("Yahoo preflight recovered after a failing streak")
        return StreakUpdate(
            state=state,
            alert_triggered=False,
            recovered=was_failing or removed,
            threshold=self.threshold,
        )
