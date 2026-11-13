"""Optional price providers.

Resolution order:

1. ``name`` argument, if given.
2. ``PRICE_PROVIDER`` environment variable.
3. ``yfinance`` (default; no key required).

A non-yfinance provider is only selected when its key is present. If the
selected provider fails at request time, ``PriceService`` tries the other
configured provider and finally falls back to Yahoo. No key ever appears in
code, tests or logs.
"""

from __future__ import annotations

import os

from backend.services.price_providers.base import PriceProvider

SUPPORTED_PROVIDERS = ("yfinance", "fmp", "tiingo")
_KEY_VARS = {"fmp": "FMP_API_KEY", "tiingo": "TIINGO_API_KEY"}


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
    present. Yahoo is not included: ``PriceService`` handles it with its own
    retry/throttle logic after this list is exhausted.
    """
    requested = resolve_provider_name(name)
    order: list[str] = []
    if requested != "yfinance":
        order.append(requested)
    for candidate in ("fmp", "tiingo"):
        if candidate != requested and _has_key(candidate):
            order.append(candidate)
    return [get_provider(candidate) for candidate in order if _has_key(candidate)]
