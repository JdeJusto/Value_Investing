"""Snapshot-backed market data provider.

``SnapshotMarketProvider`` answers the ``MarketDataProvider`` interface
entirely from an in-memory quote snapshot — the dicts returned by
:meth:`PriceService.get_market_snapshots` (one Yahoo ``.info`` call per
ticker, fetched up front for the whole universe). The analysis phase can then
run with *zero* further network traffic while keeping exactly the same
values the live provider would have produced (price, market cap, enterprise
value, beta, shares all come from the same quote summary).

For tickers missing from the snapshot an optional ``fallback`` provider is
consulted so single-ticker flows (analyze-full, historical valuation) keep
working; inside the batched workflow the snapshot covers the whole universe
and falls back to ``None`` for genuinely unavailable quotes, degrading the
valuation fields (never the analysis) gracefully.
"""

from __future__ import annotations

from typing import Dict, Optional

from backend.domain.interfaces.provider import MarketDataProvider
from backend.services.price_service import _snapshot_price


class SnapshotMarketProvider(MarketDataProvider):
    """MarketDataProvider reading only from a prefetched quote snapshot."""

    #: Keys normalized from the raw Yahoo .info dict.
    _FIELD_KEYS = {
        "market_cap": "marketCap",
        "enterprise_value": "enterpriseValue",
        "beta": "beta",
        "shares_outstanding": "sharesOutstanding",
    }

    def __init__(
        self,
        snapshots: Optional[Dict[str, Optional[dict]]] = None,
        fallback: Optional[MarketDataProvider] = None,
    ) -> None:
        """``snapshots`` maps upper-case TICKER -> raw Yahoo .info dict (or
        None when that ticker could not be quoted). ``fallback`` is consulted
        only for tickers absent from the snapshot.
        """
        self._snapshots: Dict[str, Optional[dict]] = snapshots or {}
        self._fallback = fallback

    # ------------------------------------------------------------------
    def _has(self, ticker: str) -> bool:
        return ticker.upper() in self._snapshots

    def _value(self, ticker: str, field: str):
        """Field value for a snapshotted ticker (None is a real value)."""
        snap = self._snapshots.get(ticker.upper())
        if snap is None:
            return None
        if field == "price":
            return _snapshot_price(snap)
        if field == "company_name":
            return snap.get("longName") or snap.get("shortName")
        return snap.get(self._FIELD_KEYS.get(field, field))

    def _or_fallback(self, ticker: str, field: str, getter_name: str):
        if self._has(ticker):
            return self._value(ticker, field)
        if self._fallback is not None:
            try:
                return getattr(self._fallback, getter_name)(ticker)
            except Exception:  # noqa: BLE001 — a failing quote must not break analysis
                return None
        return None

    # ------------------------------------------------------------------
    # MarketDataProvider
    # ------------------------------------------------------------------
    def get_company_name(self, ticker: str) -> Optional[str]:
        return self._or_fallback(ticker, "company_name", "get_company_name")

    def get_market_cap(self, ticker: str) -> Optional[float]:
        value = self._or_fallback(ticker, "market_cap", "get_market_cap")
        return float(value) if value is not None else None

    def get_enterprise_value(self, ticker: str) -> Optional[float]:
        value = self._or_fallback(
            ticker, "enterprise_value", "get_enterprise_value"
        )
        return float(value) if value is not None else None

    def get_current_price(self, ticker: str) -> Optional[float]:
        value = self._or_fallback(ticker, "price", "get_current_price")
        return float(value) if value is not None else None

    def get_beta(self, ticker: str) -> Optional[float]:
        value = self._or_fallback(ticker, "beta", "get_beta")
        return float(value) if value is not None else None

    def get_shares_outstanding(self, ticker: str) -> Optional[int]:
        value = self._or_fallback(
            ticker, "shares_outstanding", "get_shares_outstanding"
        )
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None