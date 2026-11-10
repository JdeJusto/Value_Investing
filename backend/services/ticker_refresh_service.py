"""Single-company refresh wrapper over the existing RefreshService.

SEC facts are synced through ``RefreshService.ensure_fresh_and_prices`` (the
same targeted ``sec sync <CIK>`` the daily workflow uses). Prices are fetched
on demand through ``PriceService`` and cached in memory only; this module never
persists or writes prices to Financial-DataBase.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from backend.services.refresh_service import RefreshService


@dataclass
class TickerRefreshResult:
    """Per-domain outcome of one ticker refresh."""

    ticker: str
    facts_synced: bool
    prices_synced: bool
    facts_error: str | None = None
    prices_error: str | None = None
    duration_seconds: float = 0.0


def _upper_set(values: list[str] | None) -> set[str]:
    return {str(value).upper() for value in (values or [])}


def _upper_failures(
    failures: list[tuple[str, str]] | None,
) -> dict[str, str]:
    return {str(ticker).upper(): str(reason) for ticker, reason in (failures or [])}


def refresh_ticker(
    ticker: str,
    *,
    facts: bool = True,
    prices: bool = True,
    service: Any | None = None,
) -> TickerRefreshResult:
    """Refresh facts and/or on-demand prices for one ticker.

    ``facts=True`` forces a targeted SEC sync even when the stored data is
    fresh. ``prices=True`` fetches the current Yahoo quote into the in-memory
    cache; prices are never persisted. The optional ``service`` is for tests.
    """
    symbol = str(ticker or "").strip().upper()
    result = TickerRefreshResult(symbol, False, False)
    if not symbol or (not facts and not prices):
        return result

    started = time.perf_counter()
    refresh = service or RefreshService()
    try:
        refreshed = refresh.ensure_fresh_and_prices(
            [symbol],
            force=True,
            skip_refresh=not facts,
            fetch_prices=prices,
        )
    except Exception as exc:  # noqa: BLE001 — report the domain, never crash
        message = f"{type(exc).__name__}: {exc}"
        if facts:
            result.facts_error = message
        if prices:
            result.prices_error = message
        result.duration_seconds = time.perf_counter() - started
        return result

    if facts:
        if symbol in _upper_set(getattr(refreshed, "refreshed", None)):
            result.facts_synced = True
        elif symbol in _upper_set(getattr(refreshed, "skipped", None)):
            result.facts_error = (
                getattr(refreshed, "sec_skipped_reason", None)
                or "SEC refresh skipped (already fresh or disabled)"
            )
        else:
            result.facts_error = _upper_failures(
                getattr(refreshed, "failed", None)
            ).get(symbol, "SEC sync did not report a status")

    if prices:
        price = (getattr(refreshed, "prices", None) or {}).get(symbol)
        if price is None:
            price_service = getattr(refresh, "_price_service", None)
            getter = getattr(price_service, "get_last_error", None)
            reason = getter(symbol) if callable(getter) else None
            result.prices_error = reason or (
                "Yahoo price unavailable (on-demand fetch returned no quote)"
            )
        else:
            result.prices_synced = True

    result.duration_seconds = time.perf_counter() - started
    return result
