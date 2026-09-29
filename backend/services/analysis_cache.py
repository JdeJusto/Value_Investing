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

# Bump when the normalization, the analysis logic or the ENTRY FORMAT changes:
# every entry becomes stale and is recomputed on the next run.
#   v1 -> fundamentals rows only
#   v2 -> fundamentals rows + the per-year DB lookups (shares outstanding,
#        fiscal-year-end). v1 files are ignored, not migrated: the history is
#        cheap to rebuild and a half-migrated entry would be a silent risk.
ANALYSIS_VERSION = "2"

DEFAULT_DIRECTORY = "data/cache/analysis"

# Per-year DB lookups cached next to the fundamentals. They are keyed by
# fiscal year (and by the diluted flag for shares) instead of a single
# scalar: get_shares_outstanding / get_fiscal_year_end_date take a fiscal
# year, and callers such as validate_sp500 compare several years side by
# side, so one value per company would answer the wrong question.
SECTION_SHARES = "shares_outstanding"
SECTION_FISCAL_YEAR_END = "fiscal_year_end_date"
# Fiscal years present in the FULL history (every source and period), the
# projection _data_reliability needs for its coverage ratio. Kept here because
# list_all() is a full read that used to run on every analyze() call.
SECTION_ALL_YEARS = "all_years"

# Marker for a lookup that was performed and found nothing, so the negative
# answer is cached too (stored as a string because JSON has no null sentinel
# distinct from "not looked up yet").
_ABSENT = "__absent__"


class AnalysisCache:
    """Per-ticker cache of normalized fundamentals and per-year DB lookups."""

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
        self._stats = {
            "hits": 0,
            "misses": 0,
            "writes": 0,
            "errors": 0,
            "lookup_hits": 0,
            "lookup_misses": 0,
        }

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
        except Exception:
            self._count("errors")
            return None
        return str(value) if value else None

    # ------------------------------------------------------------------
    def get(self, ticker: str, fingerprint: str) -> Optional[list[NormalizedFinancials]]:
        """Cached rows for this exact (ticker, fingerprint, version), or None."""
        rows = self._read_rows(ticker, fingerprint)
        if rows is None:
            return None
        self._count("hits")
        return rows

    def _read_rows(
        self, ticker: str, fingerprint: str
    ) -> Optional[list[NormalizedFinancials]]:
        """Load and validate the entry; ``None`` for any kind of miss."""
        if not self.enabled or not fingerprint:
            self._count("misses")
            return None
        try:
            with open(self.path_for(ticker), encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            self._count("misses")
            return None
        except Exception as exc:
            self._count("errors")
            logger.warning("analysis cache: unreadable entry for %s: %s", ticker, exc)
            self._count("misses")
            return None
        if (
            payload.get("version") != self.version
            or payload.get("fingerprint") != fingerprint
            or not isinstance(payload.get("fundamentals"), list)
        ):
            self._count("misses")
            return None
        try:
            return [NormalizedFinancials.from_dict(row) for row in payload["fundamentals"]]
        except Exception as exc:
            self._count("errors")
            logger.warning("analysis cache: bad payload for %s: %s", ticker, exc)
            self._count("misses")
            return None

    def put(
        self,
        ticker: str,
        fingerprint: str,
        rows: list[NormalizedFinancials],
    ) -> None:
        """Store rows for (ticker, fingerprint) atomically.

        Any per-year lookups already stored for the same (ticker, fingerprint)
        are preserved: a run that only analyses fundamentals must not drop the
        shares / fiscal-year-end values a valuation run collected.
        """
        if not self.enabled or not fingerprint or not rows:
            return
        self._write(
            ticker,
            fingerprint,
            fundamentals=[row.to_dict() for row in rows],
        )

    # ------------------------------------------------------------------
    # per-year DB lookups (shares outstanding, fiscal-year-end)
    # ------------------------------------------------------------------
    def _entry_present(
        self, ticker: str, fingerprint: str, section: str, key: str
    ) -> bool:
        """True when this exact (ticker, fingerprint, section, key) is stored.

        Distinguishes "already looked up, and there is no value" (cacheable
        negative) from "never looked up" (must query). Without it a stored
        ``None`` would be indistinguishable from a miss and the negative
        answer would never be cached.
        """
        payload = self._load(ticker, fingerprint)
        if payload is None:
            return False
        section_data = payload.get(section)
        return isinstance(section_data, dict) and str(key) in section_data

    def get_lookup(
        self,
        ticker: str,
        fingerprint: str,
        section: str,
        key: str,
    ):
        """A cached per-year lookup, or ``None`` for a miss/unknown value.

        ``None`` is also returned for a value that was looked up before and
        found to be absent, because the stored marker keeps the negative
        answer: without it, a missing concept would be re-queried on every
        run (the common case for small filers).
        """
        if not self.enabled or not fingerprint:
            return None
        payload = self._load(ticker, fingerprint)
        if payload is None:
            return None
        section_data = payload.get(section)
        if not isinstance(section_data, dict) or key not in section_data:
            return None
        self._count("lookup_hits")
        value = section_data[key]
        # Compared by value: the marker travels through JSON, so the loaded
        # string is a different object than the module-level constant.
        if value == _ABSENT:
            return None
        return value

    def put_lookup(
        self,
        ticker: str,
        fingerprint: str,
        section: str,
        key: str,
        value,
    ) -> None:
        """Store a per-year lookup (or the "known absent" marker)."""
        if not self.enabled or not fingerprint:
            return
        payload = self._load(ticker, fingerprint) or {
            "ticker": ticker.upper(),
            "fingerprint": fingerprint,
            "version": self.version,
        }
        section_data = payload.get(section)
        if not isinstance(section_data, dict):
            section_data = {}
        section_data[str(key)] = _ABSENT if value is None else value
        payload[section] = section_data
        self._write(ticker, fingerprint, fundamentals=None, extra=payload)

    # ------------------------------------------------------------------
    def _load(self, ticker: str, fingerprint: str) -> Optional[dict]:
        """Raw entry for (ticker, fingerprint) or None — no stats side effects."""
        if not self.enabled or not fingerprint:
            return None
        try:
            with open(self.path_for(ticker), encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            return None
        if (
            not isinstance(payload, dict)
            or payload.get("version") != self.version
            or payload.get("fingerprint") != fingerprint
        ):
            return None
        return payload

    def _write(
        self,
        ticker: str,
        fingerprint: str,
        fundamentals: Optional[list] = None,
        extra: Optional[dict] = None,
    ) -> None:
        """Atomic write of one entry (fundamentals and/or lookups)."""
        if not self.enabled or not fingerprint:
            return
        path = self.path_for(ticker)
        base = self._load(ticker, fingerprint) or {}
        base.update(
            {
                "ticker": ticker.upper(),
                "fingerprint": fingerprint,
                "version": self.version,
                "computed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )
        if fundamentals is not None:
            base["fundamentals"] = fundamentals
        elif "fundamentals" not in base and extra is None:
            return  # nothing to store yet
        if extra:
            for key, value in extra.items():
                if key not in ("ticker", "fingerprint", "version", "computed_at"):
                    base[key] = value
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(base, handle, separators=(",", ":"))
            os.replace(tmp, path)
        except Exception as exc:
            self._count("errors")
            logger.debug("analysis cache: could not store %s: %s", ticker, exc)
            return
        self._count("writes")

    def invalidate(self, ticker: str) -> None:
        try:
            self.path_for(ticker).unlink(missing_ok=True)
        except Exception:
            self._count("errors")
