"""Shared WACC computation for the DCF and the Yahoo provider.

Single source of truth for the CAPM cost of equity, the interest/debt cost of
debt and the market-value weights, so every caller produces the same number
for the same inputs. The defaults match ``DCFAssumptions`` (rf 4%, ERP 5%,
tax 21%, beta fallback 1.0).
"""

from __future__ import annotations

#: Defaults matching DCFAssumptions.
RISK_FREE_RATE = 0.04
EQUITY_RISK_PREMIUM = 0.05
TAX_RATE = 0.21


def compute_wacc(
    *,
    beta: float | None,
    interest_expense: float | None,
    total_debt: float | None,
    market_cap: float | None,
    book_equity: float | None = None,
    risk_free_rate: float = RISK_FREE_RATE,
    equity_risk_premium: float = EQUITY_RISK_PREMIUM,
    tax_rate: float = TAX_RATE,
) -> float:
    """WACC = E/V * CoE + D/V * CoD * (1 - tax).

    - Cost of equity = rf + beta * ERP; a missing or non-positive beta falls
      back to 1.0.
    - Cost of debt = interest / total debt when both are usable, otherwise the
      cost of equity (conservative fallback).
    - Weights use market cap, with book equity as the fallback; when no
      equity value can be priced the company is treated as all-equity and the
      cost of equity is returned.
    """
    effective_beta = beta if beta is not None and beta > 0 else 1.0
    cost_of_equity = risk_free_rate + effective_beta * equity_risk_premium

    cost_of_debt = cost_of_equity
    if interest_expense and interest_expense > 0 and total_debt and total_debt > 0:
        cost_of_debt = interest_expense / total_debt

    debt = float(total_debt) if total_debt and total_debt > 0 else 0.0
    equity = float(market_cap) if market_cap and market_cap > 0 else None
    if equity is None and book_equity and book_equity > 0:
        equity = float(book_equity)
    if equity is None or equity <= 0:
        return cost_of_equity
    total = equity + debt
    e_weight = equity / total
    d_weight = debt / total
    return e_weight * cost_of_equity + d_weight * cost_of_debt * (1.0 - tax_rate)
