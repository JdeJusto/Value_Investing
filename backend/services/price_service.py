"""Real-time price service.

Fetches current and historical prices from Yahoo Finance on demand using
yfinance. Prices are NEVER persisted to any database — every request hits
the network (or a short-lived in-memory cache, default 15 minutes).

This service is the single entry point for price data in the algorithmic
layer of Value Investing. Fundamentals keep living in Financial-DataBase;
prices live here, in real time.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

import yfinance as yf

DEFAULT_CACHE_TTL_SECONDS = 900  # 15 minutes

# Categories for a failed price/quote fetch (see classify_price_failure).
PRICE_FAILURE_DELISTED = "delisted"
PRICE_FAILURE_GLITCH = "yahoo_glitch"
PRICE_FAILURE_MAPPING = "mapping"
PRICE_FAILURE_UNKNOWN = "unknown"


def _snapshot_price(snap: dict) -> Optional[float]:
    """Extract the live price from a Yahoo .info dict, or None.

    ``regularMarketPrice`` is the current quote (identical to the latest
    ``period="1d"`` close for actively-traded names); ``currentPrice`` is the
    fallback used for some instruments. Prefers a positive number.
    """
    for key in ("regularMarketPrice", "currentPrice", "lastPrice"):
        value = snap.get(key)
        if value is not None and float(value) > 0:
            return float(value)
    return None


class PriceService:
    """Fetch real-time prices from Yahoo Finance without persisting them.

    Uses a small in-memory cache (``_CACHE_TTL`` seconds) so a single run
    with repeated requests for the same ticker/range does not hammer Yahoo.
    The cache is process-local and memory-only — nothing is written to disk
    or any database.
    """

    def __init__(self, cache_ttl: Optional[int] = None) -> None:
        self._cache: Dict[str, Tuple[float, object]] = {}
        if cache_ttl is None:
            try:
                cache_ttl = int(os.getenv("PRICE_CACHE_TTL", str(DEFAULT_CACHE_TTL_SECONDS)))
            except (TypeError, ValueError):
                cache_ttl = DEFAULT_CACHE_TTL_SECONDS
        self._cache_ttl = cache_ttl

    # ------------------------------------------------------------------
    # cache helpers
    # ------------------------------------------------------------------
    def _get_cached(self, key: str):
        entry = self._cache.get(key)
        if entry is None:
            return None
        stored_at, value = entry
        if time.time() - stored_at < self._cache_ttl:
            return value
        del self._cache[key]
        return None

    def _set_cached(self, key: str, value) -> None:
        self._cache[key] = (time.time(), value)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def get_current_price(self, ticker: str) -> Optional[float]:
        """Return the latest closing price for a ticker, or None on failure."""
        key = f"current:{ticker.upper()}"
        cached = self._get_cached(key)
        if cached is not None:
            return float(cached)

        price = self._fetch_current_price(ticker)
        if price is not None:
            self._set_cached(key, price)
        return price

    def get_current_prices(
        self,
        tickers: List[str],
        batch_size: int = 25,
        delay: float = 0.2,
        workers: int = 1,
    ) -> Dict[str, Optional[float]]:
        """Batch current-price fetch with rate-limit pacing.

        Prices already in the in-memory cache are reused; the rest are
        fetched in batches of ``batch_size`` with a ``delay`` pause between
        batches so a large universe does not hammer Yahoo Finance. When
        ``workers`` > 1 the per-ticker fetches of each batch run concurrently
        in a bounded thread pool (the pause between batches still paces the
        requests). Nothing is persisted. Returns ``{TICKER: price-or-None}``.
        """
        prices: Dict[str, Optional[float]] = {}
        remaining = [t.upper() for t in tickers if t]
        while remaining:
            batch, remaining = remaining[:batch_size], remaining[batch_size:]
            if workers > 1:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    for ticker, price in zip(batch, pool.map(self.get_current_price, batch)):
                        prices[ticker] = price
            else:
                for ticker in batch:
                    prices[ticker] = self.get_current_price(ticker)
            if remaining and delay > 0:
                time.sleep(delay)
        return prices

    def get_historical_prices(
        self,
        ticker: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Tuple[date, float]]:
        """Return ``(date, close_price)`` pairs for a ticker and date range.

        Fetches fresh from Yahoo Finance; never persists. An empty list is
        returned when no data is available (or the provider fails).
        """
        key = f"hist:{ticker.upper()}:{start_date}:{end_date}"
        cached = self._get_cached(key)
        if cached is not None:
            return list(cached)

        prices = self._fetch_historical_prices(ticker, start_date, end_date)
        # Cache an immutable tuple so callers can't mutate the cached value.
        self._set_cached(key, tuple(prices))
        return prices

    def get_price_on_date(
        self,
        ticker: str,
        target_date: date,
        window_days: int = 15,
    ) -> Optional[float]:
        """Return the closing price of the trading day closest to a date.

        Apple's fiscal year, for example, ends in late September rather than
        December. This helper finds the closest available trading day within
        ``window_days`` on either side of ``target_date``.
        """
        if isinstance(target_date, str):
            target_date = date.fromisoformat(target_date)

        start = target_date - timedelta(days=window_days)
        # yfinance treats `end` as exclusive, so push it one day past.
        end = target_date + timedelta(days=window_days + 1)
        prices = self.get_historical_prices(ticker, start_date=start, end_date=end)
        if not prices:
            return None
        best_date, best_close = min(
            prices, key=lambda p: abs((p[0] - target_date).days)
        )
        return best_close

    def get_price_at_fiscal_year_end(
        self,
        ticker: str,
        fiscal_year: int,
        fiscal_year_end_date: Optional[date] = None,
    ) -> Optional[float]:
        """Return the closing price closest to a company's fiscal year end.

        ``fiscal_year_end_date`` can be supplied by the caller when the exact
        end date is known (e.g. from Financial-DataBase fundamentals);
        otherwise it defaults to December 31 of the fiscal year.
        """
        if fiscal_year_end_date is None:
            fiscal_year_end_date = date(fiscal_year, 12, 31)
        elif isinstance(fiscal_year_end_date, str):
            fiscal_year_end_date = date.fromisoformat(fiscal_year_end_date)
        return self.get_price_on_date(ticker, fiscal_year_end_date)

    def get_shares_outstanding(self, ticker: str) -> Optional[int]:
        """Return the current shares outstanding from Yahoo, or None."""
        key = f"shares:{ticker.upper()}"
        cached = self._get_cached(key)
        if cached is not None:
            return int(cached)

        try:
            info = yf.Ticker(ticker).info
            shares = info.get("sharesOutstanding")
            if shares is not None:
                shares = int(shares)
                self._set_cached(key, shares)
                return shares
        except Exception:  # noqa: BLE001 — provider failure must not break analysis
            pass
        return None

    # ------------------------------------------------------------------
    # market snapshots (single .info call per ticker)
    # ------------------------------------------------------------------
    def get_market_snapshots(
        self,
        tickers: List[str],
        batch_size: int = 25,
        delay: float = 0.2,
        workers: int = 1,
    ) -> Dict[str, Optional[dict]]:
        """Batch current market-quote snapshot fetch (Yahoo .info, one call).

        Each ticker yields the parsed Yahoo ``.info`` quote dict — which
        carries the price, market cap, enterprise value, beta and shares in a
        single request — so a whole universe can be snapshotted once and the
        per-ticker analysis can then run *without* any further network calls.
        Not cached itself (a new snapshot is requested on each call) but the
        derived ``current:{ticker}`` price and ``shares:{ticker}`` entries are
        warmed into the memory cache so downstream reads reuse identical
        values. Batching/pacing mirrors ``get_current_prices``. Nothing is
        persisted. Returns ``{TICKER: snapshot-dict-or-None}``.
        """
        snapshots: Dict[str, Optional[dict]] = {}
        remaining = [t.upper() for t in tickers if t]
        while remaining:
            batch, remaining = remaining[:batch_size], remaining[batch_size:]
            if workers > 1:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    for ticker, snap in zip(
                        batch, pool.map(self._fetch_market_snapshot, batch)
                    ):
                        snapshots[ticker] = snap
            else:
                for ticker in batch:
                    snapshots[ticker] = self._fetch_market_snapshot(ticker)
            if remaining and delay > 0:
                time.sleep(delay)

        for ticker, snap in snapshots.items():
            if not snap:
                continue
            price = _snapshot_price(snap)
            if price is not None:
                self._set_cached(f"current:{ticker}", float(price))
            shares = snap.get("sharesOutstanding")
            if shares is not None:
                try:
                    self._set_cached(f"shares:{ticker}", int(shares))
                except (TypeError, ValueError):
                    pass
        return snapshots

    def _fetch_market_snapshot(self, ticker: str) -> Optional[dict]:
        """One Yahoo .info parse for ``ticker``, or None on failure.

        The .info quote summary is far more resilient than the chart endpoint
        used for history() — it keeps working for lightly-traded names and
        delisted-with-data issues — but a single short retry still absorbs
        transient network errors. Nothing is persisted.
        """
        for attempt in (1, 2):
            try:
                info = yf.Ticker(ticker).info
                if isinstance(info, dict) and info:
                    return info
            except Exception:  # noqa: BLE001 — transient Yahoo errors
                pass
            if attempt == 1:
                time.sleep(0.75)
        return None

    # ------------------------------------------------------------------
    # failure categorization
    # ------------------------------------------------------------------
    def classify_price_failure(
        self,
        ticker: str,
        known_ticker: Optional[Callable[[str], Optional[bool]]] = None,
    ) -> str:
        """Categorize a failed quote fetch for ``ticker``.

        Yahoo's chart endpoint emits ``possibly delisted; no price data found``
        for transient rate-limit windows on very liquid names (CBOE, BBY,
        BRK-B, NXPI…), so a bare failure tells us nothing. This probe-based
        classifier distinguishes the real cases:

        - ``yahoo_glitch``  — a fresh probe *does* find data: the original
          failure was transient (rate limiting / empty window). Reported as a
          warning; the company is analyzed with market fields N/A.
        - ``mapping``       — Yahoo has no data at all AND ``known_ticker``
          says the symbol is not a known listed company: the universe entry
          cannot be resolved to a company (universe/mapping gap). Reported as
          an error.
        - ``delisted``       — ``known_ticker`` says the company IS listed but
          Yahoo has no data anywhere: genuinely unquoted (delisted /
          suspended). Skipped with an INFO log only.
        - ``unknown``        — no Yahoo data and no listing opinion
          available; treated like delisted but surfaced for follow-up.

        ``known_ticker`` is optional and must be side-effect free; when it is
        omitted the mapping/delisted split degrades to ``unknown``.
        """
        ticker = ticker.upper()
        if self._probe_has_data(ticker):
            return PRICE_FAILURE_GLITCH
        known: Optional[bool] = None
        if known_ticker is not None:
            try:
                known = known_ticker(ticker)
            except Exception:  # noqa: BLE001 — listing lookup must not break
                known = None
        if known is False:
            return PRICE_FAILURE_MAPPING
        if known is True:
            return PRICE_FAILURE_DELISTED
        return PRICE_FAILURE_UNKNOWN

    def _probe_has_data(self, ticker: str) -> bool:
        """True when Yahoo can currently quote ``ticker`` at all.

        Tries the resilient quote summary (.info) first, then the chart
        endpoint (history) as a fallback — either proves the earlier failure
        was transient.
        """
        for attempt in (1, 2):
            try:
                info = yf.Ticker(ticker).info
                if isinstance(info, dict) and info.get("quoteType") is not None:
                    return True
            except Exception:  # noqa: BLE001 — probe must never raise
                pass
            if attempt == 1:
                time.sleep(0.75)
        try:
            hist = yf.Ticker(ticker).history(period="1d")
            if hist is not None and not hist.empty:
                return True
        except Exception:  # noqa: BLE001 — probe must never raise
            pass
        return False

    def get_split_adjustment(self, ticker: str, target_date: date) -> float:
        """Return the split multiplier converting a value at ``target_date``
        to today's split-adjusted basis.

        Yahoo Finance returns *split-adjusted* historical prices, i.e. prices
        expressed per *current* share count. But fundamentals such as the
        shares outstanding reported in financial statements are *as-of* the
        reporting date, before later stock splits. Mixing the two corrupts
        per-share metrics (EPS, P/E, FCF yield).

        For a period reported on ``target_date`` the multiplier is the product
        of every split ratio that happened *after* that date. Multiplying
        as-reported shares by this factor yields shares on the same (current)
        basis as the split-adjusted price.

        Returns 1.0 when there is no split data (or on provider failure), so
        callers can safely fall back to the as-reported numbers.
        """
        if isinstance(target_date, str):
            target_date = date.fromisoformat(target_date)

        splits = self._fetch_splits(ticker)
        if not splits:
            return 1.0

        multiplier = 1.0
        for split_date, ratio in splits:
            # yfinance reports the split as (shares after) / (shares before),
            # e.g. 4.0 for a 4:1 split, so shares multiply by `ratio`.
            if split_date > target_date and ratio:
                multiplier *= float(ratio)
        return multiplier

    def _fetch_splits(self, ticker: str) -> List[Tuple[date, float]]:
        """Fetch the stock split history (date, ratio) for a ticker.

        Ratios are Yahoo's 'Stock Splits' values, i.e. the multiplier applied to the
        share count (4.0 for a 4:1 split, 7.0 for a 7:1 split). The result is
        cached per ticker for the TTL.
        """
        key = f"splits:{ticker.upper()}"
        cached = self._get_cached(key)
        if cached is not None:
            return list(cached)

        try:
            series = yf.Ticker(ticker).splits
            result: List[Tuple[date, float]] = []
            if series is not None and not series.empty:
                for idx, ratio in series.items():
                    d = idx.date() if isinstance(idx, datetime) else date.fromisoformat(str(idx))
                    result.append((d, float(ratio)))
            self._set_cached(key, tuple(result))
            return result
        except Exception:  # noqa: BLE001 — provider failure must not break analysis
            return []

    # ------------------------------------------------------------------
    # yfinance internals (kept separate for easy mocking in tests)
    # ------------------------------------------------------------------
    def _fetch_current_price(self, ticker: str) -> Optional[float]:
        """Latest close for ``ticker``, or None on failure.

        yfinance occasionally returns an empty ``period="1d"`` frame for a
        transient window (rate limiting); one short retry usually recovers
        it. Nothing is ever persisted.
        """
        for attempt in (1, 2):
            try:
                hist = yf.Ticker(ticker).history(period="1d")
                if hist is not None and not hist.empty:
                    return float(hist["Close"].iloc[-1])
            except Exception:  # noqa: BLE001 — transient Yahoo errors
                pass
            if attempt == 1:
                time.sleep(0.75)
        return None

    def _fetch_historical_prices(
        self,
        ticker: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Tuple[date, float]]:
        try:
            kwargs: Dict[str, object] = {}
            if start_date is not None:
                kwargs["start"] = start_date
            if end_date is not None:
                kwargs["end"] = end_date
            hist = yf.Ticker(ticker).history(**kwargs)
            if hist is None or hist.empty:
                return []

            prices: List[Tuple[date, float]] = []
            for idx, row in hist.iterrows():
                try:
                    d = idx.date() if isinstance(idx, datetime) else idx.date()
                except Exception:  # noqa: BLE001
                    d = date.fromisoformat(str(idx))
                close = row.get("Close")
                if close is None:
                    continue
                try:
                    prices.append((d, float(close)))
                except (TypeError, ValueError):
                    continue
            return prices
        except Exception:  # noqa: BLE001
            return []


def get_price_service() -> PriceService:
    """Get or create a PriceService instance (process-level singleton)."""
    global _PRICE_SERVICE
    if _PRICE_SERVICE is None:
        _PRICE_SERVICE = PriceService()
    return _PRICE_SERVICE


_PRICE_SERVICE: Optional[PriceService] = None


if __name__ == "__main__":
    service = PriceService()
    for ticker in ("AAPL", "MSFT"):
        price = service.get_current_price(ticker)
        print(f"{ticker}: current price = {price}")
        fy_end = service.get_price_at_fiscal_year_end(ticker, 2023)
        print(f"{ticker}: FY2023 price ~ {fy_end}")