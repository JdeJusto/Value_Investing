"""Numeric formatting for the financial tables (single source of truth).

Every number rendered by the Balance T-view and the statement tables goes
through these helpers so the same magnitude always looks the same: statement
convention (negatives in parentheses), thousands separators, explicit signs
for deltas, and an optional display scale (``k`` / ``M`` / ``B``).

Pure functions: no Streamlit, no I/O. The currency symbol is derived from
the data unit (``USD`` -> ``$``); the UI never converts currency.
"""

from __future__ import annotations

from typing import Any

#: Em dash for missing data — never render an absent value as 0.
DASH = "—"

#: Currency code -> display symbol. Unknown codes render as themselves.
CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}

#: Display scale -> (multiplier, suffix). "raw" = as reported in the data.
SCALES: dict[str, tuple[float, str]] = {
    "raw": (1.0, ""),
    "k": (1e3, "k"),
    "M": (1e6, "M"),
    "B": (1e9, "B"),
}


def currency_symbol(unit: str | None) -> str:
    """``"USD"`` -> ``"$"``; unknown or empty units render the code itself."""
    code = (unit or "").strip()
    return CURRENCY_SYMBOLS.get(code, code)


def is_monetary(unit: str | None) -> bool:
    """True for plain currency units (``USD``), False for shares/pure/ratios."""
    code = (unit or "").strip()
    if not code or "/" in code:
        return False
    return code.isalpha() and code.isupper() and len(code) == 3


def _default_decimals(scaled: float, scale: str) -> int:
    """Raw whole numbers render without decimals; everything else gets 2."""
    if scale == "raw":
        return 0 if float(scaled).is_integer() else 2
    return 2


def _format_amount(amount: float, symbol: str, suffix: str, decimals: int) -> str:
    negative = amount < 0
    magnitude = abs(amount)
    text = f"{magnitude:,.{decimals}f}{suffix}"
    text = f"{symbol}{text}" if symbol else text
    return f"({text})" if negative else text


def fmt_money(
    value: Any,
    unit: str = "USD",
    *,
    scale: str = "raw",
    decimals: int | None = None,
) -> str:
    """Format a monetary amount (``None`` -> em dash, zero -> ``"$0"``).

    ``scale`` is one of ``raw``/``k``/``M``/``B`` (see ``SCALES``); the sign
    convention is accounting style: negatives render parenthesized.
    ``decimals`` defaults to 0 for whole raw amounts, otherwise 2.
    """
    if value is None:
        return DASH
    factor, suffix = SCALES.get(scale, SCALES["raw"])
    scaled = float(value) / factor
    if decimals is None:
        decimals = _default_decimals(scaled, scale)
    return _format_amount(scaled, currency_symbol(unit), suffix, decimals)


def fmt_pct(value: Any, *, decimals: int = 1) -> str:
    """Format a fraction as a percentage (``0.0678`` -> ``"6.8%"``)."""
    if value is None:
        return DASH
    return f"{float(value) * 100:.{decimals}f}%"


def fmt_delta(
    value: Any,
    unit: str = "USD",
    *,
    scale: str = "raw",
    decimals: int | None = None,
) -> str:
    """Format a signed difference with an explicit sign (``"+$1.24B"``).

    Zero renders as ``"$0"`` (no sign); negatives keep the accounting
    parentheses so the sign never depends on color alone.
    """
    if value is None:
        return DASH
    factor, suffix = SCALES.get(scale, SCALES["raw"])
    scaled = float(value) / factor
    if scaled == 0:
        return f"{currency_symbol(unit)}0"
    if decimals is None:
        decimals = _default_decimals(scaled, scale)
    text = _format_amount(scaled, currency_symbol(unit), suffix, decimals)
    return f"+{text}" if scaled > 0 else text


def fmt_multiple(value: Any, *, decimals: int = 2) -> str:
    """Format a ratio as a multiple (``15.5`` -> ``"15.50x"``)."""
    if value is None:
        return DASH
    return f"{float(value):.{decimals}f}x"


def fmt_ratio(value: Any, *, decimals: int = 4) -> str:
    """Format a unitless ratio (``"pure"`` facts): up to 4 decimals."""
    if value is None:
        return DASH
    text = f"{float(value):,.{decimals}f}".rstrip("0").rstrip(".")
    return text or "0"
