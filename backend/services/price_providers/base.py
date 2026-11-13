"""Price-provider abstraction.

``PriceProvider`` returns plain dicts so the rest of the application never
depends on a provider's SDK. ``date`` is a :class:`datetime.date`; the other
fields are floats or ``None``. Prices are adjusted closes whenever the provider
exposes one, matching the Yahoo series used by the backtest.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol


class PriceProvider(Protocol):
    """Minimal interface implemented by yfinance, FMP and Tiingo."""

    name: str

    def fetch_historical(
        self, ticker: str, start: str, end: str
    ) -> list[dict[str, object]]:
        """Return bars ascending by date: ``{date, open, high, low, close, volume}``."""
        ...

    def fetch_current(self, ticker: str) -> dict[str, object] | None:
        """Return the latest bar, or ``None`` when the provider has no quote."""
        ...


def _bar(
    when: date,
    *,
    open_: object = None,
    high: object = None,
    low: object = None,
    close: object = None,
    volume: object = None,
) -> dict[str, object] | None:
    """Build a normalized bar; ``None`` when the close is not numeric."""
    if close is None:
        return None
    try:
        close_value = float(close)
    except (TypeError, ValueError):
        return None

    def _number(value: object) -> float | None:
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    return {
        "date": when,
        "open": _number(open_),
        "high": _number(high),
        "low": _number(low),
        "close": close_value,
        "volume": _number(volume),
    }


def _iso_date(value: object) -> date | None:
    """Parse an ISO date/datetime string (Tiingo includes a time suffix)."""
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None
