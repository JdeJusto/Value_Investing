"""Optional price providers.

Resolution order:

1. ``name`` argument, if given.
2. ``PRICE_PROVIDER`` environment variable.
3. ``yfinance`` (default; no key required).

A non-yfinance provider is only selected when its key is present. If the
selected provider fails at request time, ``PriceService`` tries the other
configured provider and finally falls back to Yahoo. No key ever appears in
code, tests or logs.

Free tiers are tiny (FMP 250/day, Tiingo 50/hour), so batch operations go
through Yahoo's bulk downloader and only fall back to these providers for
individual tickers. A circuit breaker stops hammering a provider after a few
consecutive 429/403 responses and logs once, not once per ticker.
"""

from __future__ import annotations

import logging
import os
import threading
import time

from backend.services.price_providers.base import PriceProvider

logger = logging.getLogger("backend.price_providers")

SUPPORTED_PROVIDERS = ("yfinance", "fmp", "tiingo")
_KEY_VARS = {"fmp": "FMP_API_KEY", "tiingo": "TIINGO_API_KEY"}


class CircuitBreaker:
    """Disable a provider for a cooldown after N consecutive rate-limit errors.

    Only 429/403 responses (or messages that clearly say rate limit/forbidden)
    count: a transient 500 should not disable a provider. ``clock`` is
    injectable so tests do not sleep.
    """

    def __init__(
        self,
        threshold: int = 3,
        cooldown_seconds: float = 60.0,
        clock=time.monotonic,
    ) -> None:
        self.threshold = max(1, int(threshold))
        self.cooldown = max(0.0, float(cooldown_seconds))
        self._clock = clock
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}
        self._logged: set[str] = set()
        self._lock = threading.Lock()

    @staticmethod
    def is_rate_limit(exc: BaseException) -> bool:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (403, 429):
            return True
        message = str(exc).lower()
        return any(
            token in message
            for token in ("429", "403", "rate limit", "too many requests", "forbidden")
        )

    def is_open(self, provider_name: str) -> bool:
        with self._lock:
            opened = self._opened_at.get(provider_name)
            if opened is None:
                return False
            if self._clock() - opened <= self.cooldown:
                return True
            self._opened_at.pop(provider_name, None)
            self._failures.pop(provider_name, None)
            self._logged.discard(provider_name)
            return False

    def record_failure(self, provider_name: str, exc: BaseException) -> None:
        if not self.is_rate_limit(exc):
            return
        with self._lock:
            self._failures[provider_name] = self._failures.get(provider_name, 0) + 1
            if (
                self._failures[provider_name] >= self.threshold
                and provider_name not in self._opened_at
            ):
                self._opened_at[provider_name] = self._clock()
                if provider_name not in self._logged:
                    logger.warning(
                        "Circuit breaker OPEN for %s after %d consecutive "
                        "rate-limit/forbidden errors; skipping it for %.0fs",
                        provider_name,
                        self._failures[provider_name],
                        self.cooldown,
                    )
                    self._logged.add(provider_name)

    def record_success(self, provider_name: str) -> None:
        with self._lock:
            self._failures.pop(provider_name, None)
            self._opened_at.pop(provider_name, None)
            self._logged.discard(provider_name)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()
            self._opened_at.clear()
            self._logged.clear()


_BREAKER = CircuitBreaker()


def get_breaker() -> CircuitBreaker:
    """Process-level breaker shared by every PriceService caller."""
    return _BREAKER


def _has_key(provider: str) -> bool:
    variable = _KEY_VARS.get(provider)
    return bool(variable and os.environ.get(variable, "").strip())


def resolve_provider_name(name: str | None = None) -> str:
    """Return the requested provider, or yfinance when it cannot be used."""
    requested = name or os.environ.get("PRICE_PROVIDER", "yfinance") or "yfinance"
    requested = requested.strip().lower()
    if requested in _KEY_VARS and not _has_key(requested):
        return "yfinance"
    if requested not in SUPPORTED_PROVIDERS:
        return "yfinance"
    return requested


def get_provider(name: str | None = None) -> PriceProvider:
    """Return a provider instance; never raises for a missing key."""
    resolved = resolve_provider_name(name)
    if resolved == "fmp":
        from backend.services.price_providers.fmp_provider import FMPProvider

        return FMPProvider()
    if resolved == "tiingo":
        from backend.services.price_providers.tiingo_provider import TiingoProvider

        return TiingoProvider()
    from backend.services.price_providers.yfinance_provider import YFinanceProvider

    return YFinanceProvider()


def providers_for_fetch(name: str | None = None) -> list[PriceProvider]:
    """Ordered non-yfinance providers available for this request.

    The selected provider comes first, then any other provider whose key is
    present. Providers whose circuit breaker is open are skipped. Yahoo is not
    included: ``PriceService`` handles it with its own retry/throttle logic
    after this list is exhausted.
    """
    requested = resolve_provider_name(name)
    order: list[str] = []
    if requested != "yfinance":
        order.append(requested)
    for candidate in ("fmp", "tiingo"):
        if candidate != requested and _has_key(candidate):
            order.append(candidate)
    breaker = get_breaker()
    return [
        get_provider(candidate)
        for candidate in order
        if _has_key(candidate) and not breaker.is_open(candidate)
    ]
