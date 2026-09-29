"""Persistent per-run state for the daily workflow (resume across interruptions).

A long daily run (SEC refresh of up to ``--max-refresh`` companies + a
full-universe analysis) can take hours. If the process is interrupted — a
signal, a crash, a machine shutdown — the next run must continue from where
it stopped instead of redoing finished work. This module owns that
checkpoint:

- ``data/reports/daily_run_state.json`` (name via :data:`RUN_STATE_FILENAME`)
  is the live state of the current run.
- Writes are atomic (temp file + ``fsync`` + ``os.replace`` + directory
  ``fsync``), so a power loss leaves either the previous or the new state,
  never a truncated file.
- Progress is recorded after every completed ticker (analysis) and every
  attempted company (refresh); the file also survives a ``SIGKILL``
  because it always reflects the last flushed completion.
- On success the file is moved to
  ``daily_run_state_<run_id>.json`` in the same directory; a run abandoned
  because its universe/options changed is archived the same way.
- Resuming: same universe AND same options -> continue (skip completed
  tickers for the refresh stage, retry only transient failures); different
  options -> archive and start fresh.

The state is intentionally DB-free and price-free: analysis inputs live in
Financial-DataBase and prices are never persisted (they are re-fetched for
the report), so nothing here duplicates critical data.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("backend.run_state")

RUN_STATE_FILENAME = "daily_run_state.json"
STATE_VERSION = 1

# A failed ticker is retried on resume only when its reason looks
# transient. Data errors (no CIK mapping, no fundamentals, ...) are not
# retried: a resume cannot fix them and they would waste a refresh slot.
_TRANSIENT_MARKERS = (
    "timed out",
    "timeout",
    "rate limit",
    "http 403",
    "403",
    "429",
    "500",
    "502",
    "503",
    "504",
    "connection",
    "connect",
    "network",
    "unreachable",
    "temporar",
    "transient",
    "dns",
    "reset by peer",
)


def is_transient_failure(reason: str) -> bool:
    """True when a failure reason looks transient (network/rate limit)."""
    text = (reason or "").lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def new_run_id(now: Optional[datetime] = None) -> str:
    """A sortable run id: ``2026-09-25T08:00:00Z-abc123``."""
    moment = now or datetime.now(timezone.utc)
    return f"{moment:%Y-%m-%dT%H:%M:%SZ}-{secrets.token_hex(3)}"


def options_fingerprint(args: Any) -> dict[str, Any]:
    """The options that define run identity (a change means a fresh run)."""
    return {
        "universe": str(getattr(args, "universe", "")),
        "limit": getattr(args, "limit", None),
        "max_refresh": getattr(args, "max_refresh", None),
        "top": getattr(args, "top", None),
        "no_prices": bool(getattr(args, "no_prices", False)),
        "no_update": bool(getattr(args, "no_update", False)),
        "refresh": bool(getattr(args, "refresh", False)),
        "no_refresh": bool(getattr(args, "no_refresh", False)),
        "freshness_hours": getattr(args, "freshness_hours", None),
    }


def archive_path(out_dir: Path, run_id: str) -> Path:
    """Where an archived run state lives (completed or superseded runs)."""
    safe = run_id.replace("/", "_")
    return Path(out_dir) / f"daily_run_state_{safe}.json"


class RunState:
    """Live checkpoint of one daily workflow run (thread-safe, atomic)."""

    def __init__(self, path: Path, payload: dict[str, Any]):
        self.path = Path(path)
        self._payload = payload
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # constructors / lookup
    # ------------------------------------------------------------------
    @classmethod
    def create(
        cls,
        path: Path,
        *,
        universe_spec: str,
        options: dict[str, Any],
        total_tickers: int,
    ) -> "RunState":
        now = _now_iso()
        payload = {
            "version": STATE_VERSION,
            "run_id": new_run_id(),
            "started_at": now,
            "last_update_at": now,
            "universe": universe_spec,
            "total_tickers": int(total_tickers),
            "completed": [],
            "failed": {},
            "skipped": {},
            "current_stage": "refresh",
            "stage_progress": {"refresh": 0, "prices": 0, "analysis": 0},
            "prices_fetched": 0,
            "alerts_generated": 0,
            "network": {},
            "prices_stage": {"processed": 0, "failures": {}},
            "price_stage": {"status": "ok", "aborted_reason": None, "aborted_after": 0},
            "options": dict(options),
        }
        state = cls(path, payload)
        state.save()
        return state

    @classmethod
    def load(cls, path: Path) -> Optional["RunState"]:
        """Load a state file; a corrupt file is logged and ignored."""
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict) or "run_id" not in payload:
                raise ValueError("state file has no run_id")
            for key in ("completed", "failed", "skipped", "stage_progress"):
                payload.setdefault(key, [] if key == "completed" else {})
            payload.setdefault("options", {})
            payload.setdefault("network", {})
            payload.setdefault("prices_stage", {"processed": 0, "failures": {}})
            payload.setdefault(
                "price_stage",
                {"status": "ok", "aborted_reason": None, "aborted_after": 0},
            )
            payload.setdefault("universe", "")
            payload.setdefault("total_tickers", 0)
            return cls(path, payload)
        except FileNotFoundError:
            return None
        except Exception as exc:
            logger.warning("ignoring unreadable run state %s: %s", path, exc)
            return None

    @classmethod
    def find(cls, out_dir: Path, run_id: str) -> Optional["RunState"]:
        """Find a run by id: the live file first, then the archive."""
        out_dir = Path(out_dir)
        live = out_dir / RUN_STATE_FILENAME
        state = cls.load(live)
        if state is not None and state.run_id == run_id:
            return state
        archived = archive_path(out_dir, run_id)
        state = cls.load(archived)
        if state is not None and state.run_id == run_id:
            state.path = live  # resuming re-activates the live path
            return state
        return None

    # ------------------------------------------------------------------
    # accessors
    # ------------------------------------------------------------------
    @property
    def run_id(self) -> str:
        return str(self._payload["run_id"])

    @property
    def universe_spec(self) -> str:
        return str(self._payload.get("universe", ""))

    @property
    def total_tickers(self) -> int:
        return int(self._payload.get("total_tickers", 0))

    @property
    def options(self) -> dict[str, Any]:
        return dict(self._payload.get("options", {}))

    @property
    def current_stage(self) -> str:
        return str(self._payload.get("current_stage", ""))

    @property
    def completed(self) -> list[str]:
        return list(self._payload.get("completed", []))

    @property
    def completed_set(self) -> set[str]:
        return set(self._payload.get("completed", []))

    @property
    def failed(self) -> dict[str, str]:
        return dict(self._payload.get("failed", {}))

    @property
    def skipped(self) -> dict[str, str]:
        return dict(self._payload.get("skipped", {}))

    @property
    def stage_progress(self) -> dict[str, int]:
        return dict(self._payload.get("stage_progress", {}))

    @property
    def prices_fetched(self) -> int:
        return int(self._payload.get("prices_fetched", 0))

    @property
    def alerts_generated(self) -> int:
        return int(self._payload.get("alerts_generated", 0))

    @property
    def network(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._payload.get("network") or {})

    def note_network(self, network: Optional[dict[str, Any]]) -> None:
        """Merge network telemetry counters into the checkpoint.

        The counters are cumulative within a run, so the newest snapshot wins
        per field (a resumed run keeps accumulating into the same payload).
        """
        if not network:
            return
        with self._lock:
            current = dict(self._payload.get("network") or {})
            for key, value in network.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    current[key] = value
            self._payload["network"] = current
        self.save()

    @property
    def last_update_at(self) -> str:
        return str(self._payload.get("last_update_at", ""))

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._payload))

    def matches(self, *, universe_spec: str, options: dict[str, Any]) -> bool:
        """True when the stored run used the same universe and options."""
        return self.universe_spec == universe_spec and self.options == options

    def permanent_failures(self) -> set[str]:
        """Failed tickers whose reason is a data error (not retried)."""
        return {
            ticker
            for ticker, reason in self.failed.items()
            if not is_transient_failure(reason)
        }

    def transient_failures(self) -> set[str]:
        """Failed tickers whose reason is transient (retried on resume)."""
        return {
            ticker
            for ticker, reason in self.failed.items()
            if is_transient_failure(reason)
        }

    # ------------------------------------------------------------------
    # mutations (each one flushes the file atomically)
    # ------------------------------------------------------------------
    def set_stage(self, stage: str) -> None:
        with self._lock:
            self._payload["current_stage"] = stage
            self._save_locked()

    def note_progress(self, stage: str, ticker: Optional[str] = None) -> None:
        """Bump a stage counter (and remember the ticker for debugging)."""
        with self._lock:
            progress = self._payload.setdefault("stage_progress", {})
            progress[stage] = int(progress.get(stage, 0)) + 1
            if ticker:
                self._payload["last_ticker"] = ticker
            self._save_locked()

    def add_completed(self, ticker: str) -> None:
        with self._lock:
            completed = self._payload.setdefault("completed", [])
            if ticker not in completed:
                completed.append(ticker)
            self._payload.get("skipped", {}).pop(ticker, None)
            self._save_locked()

    def add_failed(self, ticker: str, reason: str) -> None:
        with self._lock:
            self._payload.setdefault("failed", {})[ticker] = str(reason)[:500]
            self._save_locked()

    def add_skipped(self, ticker: str, reason: str) -> None:
        with self._lock:
            self._payload.setdefault("skipped", {})[ticker] = str(reason)[:500]
            self._save_locked()

    def set_prices_fetched(self, count: int) -> None:
        with self._lock:
            self._payload["prices_fetched"] = int(count)
            self._save_locked()

    def set_prices_stage(self, processed: int, failures: dict[str, int]) -> None:
        """Store the price-stage outcome: how many tickers were processed and
        how the failures broke down by category.

        Categories come from
        :func:`backend.services.price_service.PriceService.classify_price_failure`
        (``yahoo_glitch``/``mapping``/``delisted``/``unknown``) plus
        ``no_yahoo``, which counts the tickers that were never attempted
        because the Yahoo preflight said the provider was unreachable.
        Unknown categories are kept as extra keys rather than dropped, so a
        new category shows up instead of disappearing.
        """
        clean: dict[str, int] = {}
        for key, value in (failures or {}).items():
            try:
                clean[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        with self._lock:
            self._payload["prices_stage"] = {
                "processed": int(processed),
                "failures": clean,
            }
            self._save_locked()

    def set_price_stage_status(
        self,
        status: str,
        aborted_reason: Optional[str] = None,
        aborted_after: int = 0,
    ) -> None:
        """Record the outcome of the price stage: ok, or aborted and why.

        An abort means the provider refused non-transiently (HTTP 429 rate
        limit, 401 invalid crumb) and the stage stopped early instead of
        working through the universe. ``aborted_after`` is the size of the
        failing streak that triggered it.
        """
        with self._lock:
            self._payload["price_stage"] = {
                "status": str(status or "ok"),
                "aborted_reason": aborted_reason,
                "aborted_after": int(aborted_after or 0),
            }
            self._save_locked()

    def note_price_failure(self, category: str, count: int = 1) -> None:
        """Increment one price-failure category in the checkpoint."""
        with self._lock:
            stage = self._payload.get("prices_stage")
            if not isinstance(stage, dict):
                stage = {"processed": 0, "failures": {}}
            failures = stage.get("failures")
            if not isinstance(failures, dict):
                failures = {}
            failures[category] = int(failures.get(category, 0)) + int(count)
            stage["failures"] = failures
            self._payload["prices_stage"] = stage
            self._save_locked()

    def price_stage_status(self) -> dict[str, Any]:
        """The price-stage outcome recorded in the checkpoint (never raises)."""
        with self._lock:
            stage = self._payload.get("price_stage")
            if isinstance(stage, dict):
                return dict(stage)
            # A state written before this field existed reads as "ok": a
            # missing key is not evidence of an abort.
            return {"status": "ok", "aborted_reason": None, "aborted_after": 0}

    def set_alerts_generated(self, count: int) -> None:
        with self._lock:
            self._payload["alerts_generated"] = int(count)
            self._save_locked()

    def save(self) -> None:
        with self._lock:
            self._save_locked()

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def archive(self) -> Path:
        """Move the live state file to ``daily_run_state_<run_id>.json``."""
        with self._lock:
            self._payload["last_update_at"] = _now_iso()
            target = archive_path(self.path.parent, self.run_id)
            self._save_locked()
            os.replace(self.path, target)
            _fsync_dir(self.path.parent)
            logger.info("run state archived: %s", target.name)
            return target

    def complete(self) -> Path:
        """Archive a successfully finished run and remove the live file."""
        with self._lock:
            self._payload["current_stage"] = "done"
            self._payload["finished_at"] = _now_iso()
        return self.archive()

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _save_locked(self) -> None:
        """Atomic write: temp file + fsync + rename + directory fsync."""
        self._payload["last_update_at"] = _now_iso()
        data = json.dumps(self._payload, indent=2, sort_keys=False)
        tmp = self.path.with_name(self.path.name + ".tmp")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)
        _fsync_dir(self.path.parent)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fsync_dir(path: Path) -> None:
    """Best-effort directory fsync so the rename itself is durable."""
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
