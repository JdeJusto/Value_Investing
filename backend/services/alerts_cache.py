"""Per-day cache of the daily alert evaluation.

The alert engine calibrates its TRIGGER_EVENT floors across the whole analyzed
universe (``calibrate_trigger_thresholds`` takes the percentiles of every
company's delta), so the evaluation is a property of the *set*, not of one
company. The cache is therefore keyed by the day, the run and a digest of the
alert inputs, and it stores and replays the **whole** alert list. Caching per
ticker — as a naive design would — would recompute the percentiles over a
partial universe and silently change which triggers fire.

Why bother, given the alert stage is ~0.1 s of a ~30 min run? Measured
reality, stated up front:

- The **evaluation is not a bottleneck**: 0.1 s of a 1 682 s run (0.006 %).
  Caching it saves at most that, and the digest costs a fraction of it.
- The **hit rate is near zero in practice**, because the two inputs that
  change between runs change: every run rewrites ``daily_state.json`` (which
  feeds the SELL_WARNING comparison and therefore the digest) and prices move,
  which moves the composite scores. A resumed run of the same id on the same
  day is the only case that can hit, and even then only if nothing was
  rewritten in between.

What it does buy is **idempotence**: when it does hit, the same run replays
the exact same alert list instead of re-deriving it, so a resumed run cannot
re-emit alerts the report already carried. Keep it for that guarantee; do not
expect a measurable speed-up, and feel free to delete it if the extra file
per day is not worth it.

The digest is a compact projection of exactly what the engine reads
(composite score + confidence, Buffett score, opportunity, the delta metrics
and the previous total). It costs a fraction of the evaluation instead of
serializing whole analysis dicts. When a trigger starts reading a new field,
bump :data:`ALERTS_CACHE_VERSION` — the same discipline the fundamentals cache
follows with ``ANALYSIS_VERSION``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import date as date_cls
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger("backend.alerts_cache")

ALERTS_CACHE_VERSION = "1"

DEFAULT_DIRECTORY = "data/cache/alerts"


@dataclass(frozen=True)
class AlertsCacheEntry:
    """Stored alert list plus the key that proves it is still valid."""

    date: str
    run_id: str
    digest: str
    alerts: list[dict[str, Any]]


def _scalar(value: Any) -> Any:
    """JSON-safe, stable representation of one input value."""
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)


def input_digest(
    analyses: dict[str, Optional[dict]],
    previous: Optional[dict[str, dict]] = None,
) -> str:
    """Stable digest of the inputs the alert engine reads.

    Deliberately narrow (composite score/confidence, Buffett score,
    opportunity, delta metrics, previous total) so it stays much cheaper than
    the evaluation itself, and deliberately *not* per-company: the calibrated
    floors depend on the whole cross-section, so one change anywhere changes
    the digest and the evaluation is redone.
    """
    parts: list[list[Any]] = []
    for ticker in sorted(analyses):
        item = analyses[ticker] or {}
        composite = item.get("composite_score") or {}
        deltas = item.get("delta_metrics") or {}
        prior = ((previous or {}).get(ticker) or {}).get("composite_score") or {}
        parts.append(
            [
                ticker,
                _scalar(composite.get("total_score")),
                _scalar(composite.get("confidence")),
                _scalar(item.get("buffett_score")),
                _scalar(item.get("opportunity")),
                sorted(
                    (str(k), _scalar(v)) for k, v in deltas.items()
                ),
                _scalar(prior.get("total_score")),
            ]
        )
    blob = json.dumps(parts, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:16]


class AlertsCache:
    """One file per day: ``alerts_<YYYY-MM-DD>.json``."""

    def __init__(
        self,
        directory: str | os.PathLike[str] = DEFAULT_DIRECTORY,
        version: str = ALERTS_CACHE_VERSION,
        enabled: bool = True,
    ):
        self.directory = Path(directory)
        self.version = str(version)
        self.enabled = bool(enabled)
        self.hits = 0
        self.misses = 0
        self.writes = 0

    # ------------------------------------------------------------------
    def path_for(self, day: date_cls | str) -> Path:
        stamp = day if isinstance(day, str) else day.isoformat()
        safe = "".join(ch for ch in stamp if ch.isalnum() or ch in "-_")
        return self.directory / f"alerts_{safe}.json"

    # ------------------------------------------------------------------
    def get(
        self,
        day: date_cls | str,
        run_id: str,
        digest: str,
    ) -> Optional[list[dict[str, Any]]]:
        """Stored alerts for this exact (day, run, inputs), or None."""
        if not self.enabled:
            self.misses += 1
            return None
        try:
            with open(self.path_for(day), encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            self.misses += 1
            return None
        except Exception as exc:  # noqa: BLE001 — a corrupt entry is a miss
            logger.warning("alerts cache: unreadable entry for %s: %s", day, exc)
            self.misses += 1
            return None
        if (
            payload.get("version") != self.version
            or payload.get("date") != (day if isinstance(day, str) else day.isoformat())
            or payload.get("run_id") != run_id
            or payload.get("digest") != digest
            or not isinstance(payload.get("alerts"), list)
        ):
            self.misses += 1
            return None
        self.hits += 1
        return list(payload["alerts"])

    def put(
        self,
        day: date_cls | str,
        run_id: str,
        digest: str,
        alerts: Iterable[Any],
        as_dict=None,
    ) -> None:
        """Store the alert list for (day, run, inputs), atomically."""
        if not self.enabled:
            return
        items = list(alerts)
        if as_dict is not None:
            items = [as_dict(alert) for alert in items]
        path = self.path_for(day)
        payload = {
            "version": self.version,
            "date": day if isinstance(day, str) else day.isoformat(),
            "run_id": run_id,
            "digest": digest,
            "computed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "alerts": items,
        }
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, default=str)
            os.replace(tmp, path)
        except Exception as exc:  # noqa: BLE001 — caching must never break a run
            logger.warning("alerts cache: could not store %s: %s", day, exc)
            return
        self.writes += 1

    # ------------------------------------------------------------------
    def stats(self) -> dict[str, int]:
        return {"hits": self.hits, "misses": self.misses, "writes": self.writes}
