"""Tiny display helpers shared by the UI adapters.

Pure move out of ``ui_adapter`` so ``portfolio_adapter`` can format values
without importing the general adapter (which would create an import cycle).
"""

from __future__ import annotations

from typing import Any

DASH = "—"


def fmt_or_dash(value: Any, digits: int = 2, percent: bool = False) -> str:
    """Format a number for display; ``None`` becomes an em dash, never 0."""
    if value is None:
        return DASH
    if percent:
        return f"{value:.{digits}%}"
    return f"{value:,.{digits}f}"


def _abbreviate(value: Any, unit: str, decimals: int, with_symbol: bool) -> str:
    """Shared K/M/B/T formatting (see ``abbreviate_number``)."""
    if value is None:
        return DASH
    number = float(value)
    if number == 0:
        return "0"
    if unit == "percent":
        return f"{number * 100:.1f}%"
    if unit == "pure":
        return f"{number:,.4f}".rstrip("0").rstrip(".") or "0"
    if unit == "USD/shares":
        text = f"${abs(number):,.2f}" if with_symbol else f"{abs(number):,.2f}"
        return f"({text})" if number < 0 else text
    magnitude = abs(number)
    # Natural bucket first; if the scaled value rounds up to 1000, promote
    # to the next larger unit (999_999 -> "1.00M", not "1000.00K").
    buckets = ((1e15, None), (1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K"))
    index = len(buckets)
    for position, (factor, _) in enumerate(buckets):
        if magnitude >= factor:
            index = position
            break
    if index < len(buckets):
        factor, suffix = buckets[index]
        scaled = magnitude / factor
        if suffix and index > 0 and round(scaled, decimals) >= 1000:
            factor, suffix = buckets[index - 1]
            scaled = magnitude / factor
        text = f"{scaled:.{decimals}f}{suffix}" if suffix else f"{magnitude:.1e}"
    else:
        text = f"{magnitude:,.{decimals}f}"
    if unit == "USD" and with_symbol:
        text = f"${text}"
    elif unit == "shares":
        text = f"{text} sh"
    return f"({text})" if number < 0 else text


def abbreviate_number(value: Any, unit: str = "USD", decimals: int = 2) -> str:
    """K/M/B/T display for large numbers, currency-aware.

    ``416_161_000_000, "USD"`` -> ``"$416.16B"``;
    ``-19_001_000_000, "USD"`` -> ``"($19.00B)"``;
    ``14_776_353_000, "shares"`` -> ``"14.78B sh"``;
    ``42.15, "USD"`` -> ``"$42.15"``. Percent/pure values are already
    short and are not abbreviated; ``None`` -> em dash; zero -> ``"0"``.
    """
    return _abbreviate(value, unit, decimals, with_symbol=True)


def abbreviate_value(value: Any, unit: str = "USD", decimals: int = 2) -> str:
    """Same as :func:`abbreviate_number` but without the currency symbol.

    The unit is appended as a suffix when it is not a currency
    (``"14.78B sh"``); currency values render bare (``"416.16B"``).
    """
    return _abbreviate(value, unit, decimals, with_symbol=False)
