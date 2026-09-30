"""Shared price prefetch cache for a screening session.

The screener fetches one real-time price per ticker; a batch prefetch turns
N individual Yahoo calls into one paced batch (``PriceService.
get_current_prices``) and the per-ticker reads then hit memory. When the
batch is unavailable or fails, ``prefetch`` falls back to per-ticker fetches
(the previous behavior) and ``get`` refetches an expired entry individually.

Prices are **never persisted** (project rule): the cache lives in memory for
the process/session and expires after ``ttl`` seconds.
"""

from __future__ import annotations

import threading
import time
from typing import Any

#: Default time-to-live: one screening session.
DEFAULT_TTL = 900


class PriceCache:
    """Thread-safe TTL cache of current prices, prefetched in batch."""

    def __init__(self, ttl: int = DEFAULT_TTL, service: Any = None) -> None:
        self._ttl = ttl
        self._service = service
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float | None, float]] = {}

    # ------------------------------------------------------------------
    def _price_service(self):
        if self._service is None:
            from backend.services.price_service import get_price_service

            self._service = get_price_service()
        return self._service

    @staticmethod
    def _safe_get(service, ticker: str) -> float | None:
        try:
            return service.get_current_price(ticker)
        except Exception:  # noqa: BLE001 — a missing quote must not break the screen
            return None

    # ------------------------------------------------------------------
    def prefetch(self, tickers: list[str]) -> None:
        """Warm the cache for many tickers in one batch call.

        Tickers already fresh in the cache are skipped, so a second screen in
        the same session only fetches the new names.
        """
        wanted = [t.upper() for t in tickers if t]
        if not wanted:
            return
        now = time.monotonic()
        with self._lock:
            missing = [
                ticker
                for ticker in wanted
                if ticker not in self._cache or self._cache[ticker][1] <= now
            ]
        if not missing:
            return

        service = self._price_service()
        try:
            prices = service.get_current_prices(missing)
        except Exception:  # noqa: BLE001 — fall back to per-ticker below
            prices = None
        if not isinstance(prices, dict) or not prices:
            prices = {ticker: self._safe_get(service, ticker) for ticker in missing}

        expires = now + self._ttl
        with self._lock:
            for ticker in missing:
                self._cache[ticker] = (prices.get(ticker), expires)

    def get(self, ticker: str) -> float | None:
        """Cached price, refetching it individually when missing or expired."""
        key = ticker.upper()
        now = time.monotonic()
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None and entry[1] > now:
                return entry[0]
            self._cache.pop(key, None)
        value = self._safe_get(self._price_service(), key)
        with self._lock:
            self._cache[key] = (value, now + self._ttl)
        return value

    # ------------------------------------------------------------------
    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)
