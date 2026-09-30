"""Greenblatt Magic Formula metrics.

From *The Little Book That Beats the Market* (2005):

- **Rule 1 — Return on Capital**: ``EBIT / (net working capital + net fixed
  assets)`` where net working capital is ``current assets - current
  liabilities`` floored at zero and net fixed assets is net PPE.
- **Rule 2 — Earnings Yield**: ``EBIT / Enterprise Value`` where
  ``EV = market cap + total debt - cash``.

Both return ``None`` when an input is missing; the caller decides whether
that is INSUFFICIENT_DATA or a ranking exclusion.
"""

from __future__ import annotations

from typing import Any


def return_on_capital(row: Any) -> float | None:
    """EBIT / (net working capital + net fixed assets), or None."""
    if row is None or row.ebit is None:
        return None
    current_assets = getattr(row, "current_assets", None)
    current_liabilities = getattr(row, "current_liabilities", None)
    net_ppe = getattr(row, "net_ppe", None)
    if current_assets is None or current_liabilities is None or net_ppe is None:
        return None
    net_working_capital = max(float(current_assets) - float(current_liabilities), 0.0)
    denominator = net_working_capital + float(net_ppe)
    if denominator <= 0:
        return None
    return float(row.ebit) / denominator


def earnings_yield(row: Any, market_cap: float | None) -> float | None:
    """EBIT / (market cap + total debt - cash), or None."""
    if row is None or row.ebit is None or market_cap is None or market_cap <= 0:
        return None
    debt = float(getattr(row, "total_debt", None) or 0.0)
    cash = float(getattr(row, "cash_and_equivalents", None) or 0.0)
    enterprise_value = float(market_cap) + debt - cash
    if enterprise_value <= 0:
        return None
    return float(row.ebit) / enterprise_value
