"""Dividend history fetched on demand, never persisted.

Graham's defensive-investor criterion 4 requires *uninterrupted* dividend
payments for at least 20 years. Financial-DataBase has a ``dividends`` table
for exactly this, but it is empty, so the criterion could never be evaluated.
This service closes that gap the same way prices are handled: it asks Yahoo
Finance for the dividend history, caches it in memory for 15 minutes, and
never writes it to any database.

Public API:

- ``get_dividends(ticker)`` -> list of :class:`DividendRecord` (ex-date,
  amount), most recent first.
- ``has_dividend_history(ticker, min_years)`` -> bool.
- ``consecutive_years(ticker)`` -> int, the current unbroken run of years
  with at least one dividend (the number criterion 4 actually tests).

Rules:

- Real-time from Yahoo; **never persisted** (same policy as prices).
- Respects the Yahoo availability preflight: when the provider is
  unreachable the service returns empty results instead of raising, so a
  rate limit degrades the criterion to INSUFFICIENT_DATA rather than
  breaking the run.
- A source that reports no dividends yields ``has_dividend_history == False``
  and ``consecutive_years == 0`` — a real answer, not an error.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("backend.dividend_service")

DEFAULT_CACHE_TTL_SECONDS = 900  # 15 minutes, like PriceService


@dataclass(frozen=True)
class DividendRecord:
    """One dividend payment."""

    ex_date: date
    amount: float


def _parse_dividends(raw) -> List[DividendRecord]:
    """Normalize a yfinance dividend Series into records, most recent first.

    yfinance returns a pandas Series indexed by tz-aware timestamps; the
    index can also be a plain list of timestamps depending on the version, so
    both are handled. Unparseable entries are skipped, not fatal.
    """
    records: List[DividendRecord] = []
    if raw is None:
        return records
    try:
        items = list(raw.items())
    except AttributeError:
        items = list(raw)
    for key, amount in items:
        # Skip NaT (Not a Time) keys — they can't be converted to dates
        # and would crash the sort below (NaT != NaT is True).
        try:
            if key != key:  # NaT check
                continue
        except (TypeError, ValueError):
            pass
        try:
            value = float(amount)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        if isinstance(key, datetime):
            ex_date = key.date()
        else:
            try:
                ex_date = datetime.fromisoformat(str(key)).date()
            except ValueError:
                continue
        records.append(DividendRecord(ex_date=ex_date, amount=value))
    records.sort(key=lambda r: r.ex_date, reverse=True)
    return records


class DividendService:
    """Fetch and cache dividend history from Yahoo Finance."""

    def __init__(
        self,
        cache_ttl: Optional[int] = None,
        health_fn=None,
        yf_ticker=None,
    ) -> None:
        self._cache: Dict[str, Tuple[float, List[DividendRecord]]] = {}
        self._cache_ttl = (
            int(cache_ttl)
            if cache_ttl is not None
            else int(time.time()) * 0 + DEFAULT_CACHE_TTL_SECONDS
        )
        self._lock = threading.Lock()
        # Injectable for tests; production uses the module-level helpers.
        self._health_fn = health_fn or _yahoo_available
        self._yf_ticker = yf_ticker or _yf_ticker

    # ------------------------------------------------------------------
    def _get_cached(self, ticker: str) -> Optional[List[DividendRecord]]:
        entry = self._cache.get(ticker)
        if entry is None:
            return None
        stored_at, records = entry
        if time.time() - stored_at < self._cache_ttl:
            return records
        with self._lock:
            self._cache.pop(ticker, None)
        return None

    def _set_cached(self, ticker: str, records: List[DividendRecord]) -> None:
        with self._lock:
            self._cache[ticker] = (time.time(), records)

    # ------------------------------------------------------------------
    def get_dividends(self, ticker: str) -> List[DividendRecord]:
        """Dividend history for ``ticker``, most recent first.

        Returns an empty list when the provider is unreachable or the company
        has never paid a dividend — both are valid answers, not errors.
        """
        ticker = ticker.upper()
        cached = self._get_cached(ticker)
        if cached is not None:
            return cached

        if not self._health_fn():
            logger.warning(
                "Yahoo preflight unavailable: no dividend fetch for %s", ticker
            )
            return []

        try:
            raw = self._yf_ticker(ticker).dividends
        except Exception as exc:  # noqa: BLE001 — a failed fetch is empty
            logger.warning("dividend fetch failed for %s: %s", ticker, exc)
            return []

        records = _parse_dividends(raw)
        self._set_cached(ticker, records)
        return records

    # ------------------------------------------------------------------
    def has_dividend_history(self, ticker: str, min_years: int = 20) -> bool:
        """True when the company has paid dividends for at least ``min_years``."""
        return self.consecutive_years(ticker) >= min_years

    def consecutive_years(self, ticker: str) -> int:
        """Length of the current unbroken run of dividend-paying years.

        Counts distinct calendar years with at least one payment, walking back
        from the most recent one; a gap ends the run. Companies that pay
        quarterly but skipped a year therefore show the run restarting after
        the gap, which is what criterion 4 tests.
        """
        records = self.get_dividends(ticker)
        if not records:
            return 0
        years = sorted({r.ex_date.year for r in records}, reverse=True)
        streak = 1
        for previous, current in zip(years, years[1:]):
            if previous - current == 1:
                streak += 1
            else:
                break
        return streak


# ----------------------------------------------------------------------
# module-level helpers (patch points for tests)
# ----------------------------------------------------------------------


def _yahoo_available() -> bool:
    """The Yahoo preflight verdict, shared with the price pipeline."""
    from backend.services.yahoo_health import check_yahoo_availability

    return check_yahoo_availability().available


def _yf_ticker(ticker: str):
    import yfinance as yf

    return yf.Ticker(ticker)


_default_service: Optional[DividendService] = None
_default_lock = threading.Lock()


def get_dividend_service() -> DividendService:
    """Process-level singleton."""
    global _default_service
    if _default_service is None:
        with _default_lock:
            if _default_service is None:
                _default_service = DividendService()
    return _default_service
