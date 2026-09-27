"""File-backed cache of the fundamentals history, keyed by change-detection.

Why: measuring one ticker showed that ~96 % of the analysis is the database
read (``_load_history`` ≈ 134 ms) and only ~4 % is the arithmetic that
follows (≈ 6 ms). Re-reading the very same facts on every run is therefore
pure waste — and the arithmetic must run anyway, because price-derived
metrics (P/E, FCF yield, margin of safety) depend on the live quote.

The cache stores the :class:`NormalizedFinancials` rows under
``data/cache/analysis/<TICKER>.json`` and reuses them only when BOTH the
fundamentals fingerprint and the analysis version match:

- a new filing or a re-ingested fact changes the fingerprint -> recompute;
- a change in normalization/analysis logic bumps :data:`ANALYSIS_VERSION`
  -> every entry is ignored until rewritten;
- otherwise the rows are reused and only the arithmetic runs again.

Prices are never cached: they are fetched per run and are not persisted
anywhere (see PriceService). Nothing here touches the database; the
fingerprint is computed by the repository (one indexed aggregate) and this
cache degrades to a no-op when the repository cannot provide one (JSON /
SQL repositories), when it is disabled, or on any read/write error.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

from backend.domain.value_objects.financials_normalized import NormalizedFinancials

logger = logging.getLogger("backend.analysis_cache")

# Bump when the normalization or the analysis logic changes: every entry
# becomes stale and is recomputed on the next run.
ANALYSIS_VERSION = "1"

DEFAULT_DIRECTORY = "data/cache/analysis"


class AnalysisCache:
    """Per-ticker cache of normalized fundamentals rows."""

    def __init__(
        self,
        repository=None,
        directory: str | os.PathLike[str] = DEFAULT_DIRECTORY,
        version: str = ANALYSIS_VERSION,
        enabled: bool = True,
    ):
        self.repository = repository
        self.directory = Path(directory)
        self.version = str(version)
        self.enabled = bool(enabled) and repository is not None
        self._lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0, "writes": 0, "errors": 0}

    # ------------------------------------------------------------------
    @property
    def stats(self) -> dict[str, int]:
        with self._lock:
            return dict(self._stats)

    def reset_stats(self) -> None:
        with self._lock:
            for key in self._stats:
                self._stats[key] = 0

    def _count(self, key: str) -> None:
        with self._lock:
            self._stats[key] = self._stats.get(key, 0) + 1

    # ------------------------------------------------------------------
    def path_for(self, ticker: str) -> Path:
        safe = "".join(ch for ch in ticker.upper() if ch.isalnum() or ch in "-._")
        return self.directory / f"{safe}.json"

    def fingerprint_for(self, ticker: str) -> Optional[str]:
        """Cheap change-detector digest from the repository (None = no cache)."""
        if not self.enabled:
            return None
        getter = getattr(self.repository, "fundamentals_fingerprint", None)
        if not callable(getter):
            return None
        try:
            value = getter(ticker)
        except Exception:  # noqa: BLE001 — a fingerprint failure is a miss
            self._count("errors")
            return None
        return str(value) if value else None

    # ------------------------------------------------------------------
    def get(self, ticker: str, fingerprint: str) -> Optional[list[NormalizedFinancials]]:
        """Cached rows for this exact (ticker, fingerprint, version), or None."""
        if not self.enabled or not fingerprint:
            self._count("misses")
            return None
        try:
            with open(self.path_for(ticker), encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            self._count("misses")
            return None
        except Exception as exc:  # noqa: BLE001 — a corrupt entry is a miss
            self._count("errors")
            logger.warning("analysis cache: unreadable entry for %s: %s", ticker, exc)
            self._count("misses")
            return None
        if (
            payload.get("version") != self.version
            or payload.get("fingerprint") != fingerprint
            or not isinstance(payload.get("rows"), list)
        ):
            self._count("misses")
            return None
        try:
            rows = [NormalizedFinancials.from_dict(row) for row in payload["rows"]]
        except Exception as exc:  # noqa: BLE001 — never let the cache break a run
            self._count("errors")
            logger.warning("analysis cache: bad payload for %s: %s", ticker, exc)
            self._count("misses")
            return None
        self._count("hits")
        return rows

    def put(
        self,
        ticker: str,
        fingerprint: str,
        rows: list[NormalizedFinancials],
    ) -> None:
        """Store rows for (ticker, fingerprint) atomically."""
        if not self.enabled or not fingerprint or not rows:
            return
        path = self.path_for(ticker)
        payload = {
            "ticker": ticker.upper(),
            "fingerprint": fingerprint,
            "version": self.version,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rows": [row.to_dict() for row in rows],
        }
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"))
            os.replace(tmp, path)
        except Exception as exc:  # noqa: BLE001 — caching must never break a run
            self._count("errors")
            logger.debug("analysis cache: could not store %s: %s", ticker, exc)
            return
        self._count("writes")

    def invalidate(self, ticker: str) -> None:
        try:
            self.path_for(ticker).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001 — invalidation is best effort
            self._count("errors")
