"""Company-type detection shared by the book methodologies and the DCF.

Several screens in the canon were written for product companies: banks and
insurers have structurally high leverage and no inventory (Lynch GARP, Graham,
Graham & Dodd, Buffett/Clark and Fisher all misread them), REITs are opaque to
a free-cash-flow lens, and hyper-growth companies burn cash while growing fast.
Centering that classification here means every consumer uses the same signals
instead of each one re-implementing a slightly different heuristic.

A company is typed by the first rule that matches (see
:func:`detect_company_type`):

1. ``sector_hint`` — a label containing ``financial``/``bank``/``insurance``
   -> FINANCIAL; ``real estate``/``reit`` -> REIT; ``utilities``/``utility``
   -> UTILITY.
2. Balance-sheet / cash-flow fingerprint of a financial company:
   - no inventory AND long-term debt > 5x net income;
   - total_liabilities / total_assets > 0.85;
   - positive net income, non-positive operating cash flow, and no reported
     capital expenditure (the bank whose CFO is dominated by operating
     asset/liability flows) while revenue is present.
3. Hyper-growth: 5-year revenue CAGR > 25% while free cash flow is negative.
4. Otherwise STANDARD; with no row and no sector hint, UNKNOWN.

Pure functions of data — no network, no database, no prices.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class CompanyType(str, Enum):
    """The company shape that decides which criteria make sense."""

    FINANCIAL = "FINANCIAL"  # banks, insurers, brokers, asset managers
    REIT = "REIT"  # real estate investment trusts
    UTILITY = "UTILITY"  # regulated utilities
    HYPER_GROWTH = "HYPER_GROWTH"  # revenue CAGR > 25% and negative FCF
    STANDARD = "STANDARD"  # everything else
    UNKNOWN = "UNKNOWN"  # no row and no sector to say anything


#: Sector-hint keywords per type. Matched as case-insensitive substrings so
#: provider labels ("Financial Services", "Banks—Diversified", "Real Estate
#: Investment Trusts") keep resolving without a brittle exact-match list.
_FINANCIAL_KEYWORDS = (
    "financial",
    "bank",
    "insurance",
    "asset management",
    "capital markets",
)
_REIT_KEYWORDS = ("real estate", "reit")
_UTILITY_KEYWORDS = ("utilities", "utility")


def _hint_matches(sector_hint: Any, keywords: tuple[str, ...]) -> bool:
    """True when a sector hint contains any keyword (case-insensitive)."""
    if not sector_hint:
        return False
    lowered = str(sector_hint).strip().lower()
    return any(keyword in lowered for keyword in keywords)


def _financial_fingerprint(row: Any) -> bool:
    """Balance-sheet / cash-flow signs that a financial company shows.

    Mirrors the signals the Lynch GARP screen historically used, extended with
    the bank cash-flow fingerprint (positive net income while operating cash
    flow is non-positive and capex is unreported) that the DCF relied on: all
    three are heuristics, not a taxonomy.
    """
    if row is None:
        return False
    inventory = getattr(row, "inventory", None)
    net_income = getattr(row, "net_income", None)
    debt = getattr(row, "long_term_debt", None)
    if debt is None:
        debt = getattr(row, "total_debt", None)
    if (
        inventory is None
        and debt is not None
        and net_income is not None
        and net_income > 0
        and debt / net_income > 5.0
    ):
        return True
    total_assets = getattr(row, "total_assets", None)
    total_liabilities = getattr(row, "total_liabilities", None)
    if (
        total_assets is not None
        and total_assets > 0
        and total_liabilities is not None
        and total_liabilities / total_assets > 0.85
    ):
        return True
    revenue = getattr(row, "revenue", None)
    operating_cash_flow = getattr(row, "operating_cash_flow", None)
    capital_expenditure = getattr(row, "capital_expenditure", None)
    return (
        revenue is not None
        and revenue > 0
        and net_income is not None
        and net_income > 0
        and operating_cash_flow is not None
        and operating_cash_flow <= 0
        and capital_expenditure is None
    )


def _revenue_cagr(history) -> float | None:
    """Annualized revenue CAGR over the newest-to-oldest span, or None."""
    rows = [
        r
        for r in (history or [])
        if r is not None
        and getattr(r, "revenue", None) is not None
        and getattr(r, "revenue", 0) > 0
    ]
    if len(rows) < 2:
        return None
    newest, oldest = rows[0], rows[-1]
    span = int(getattr(newest, "fiscal_year", 0) or 0) - int(
        getattr(oldest, "fiscal_year", 0) or 0
    )
    if span <= 0:
        return None
    return (float(newest.revenue) / float(oldest.revenue)) ** (1.0 / span) - 1.0


def _free_cash_flow(row: Any) -> float | None:
    """Free cash flow for a row: direct or ``OCF - capex``, or None."""
    if row is None:
        return None
    fcf = getattr(row, "free_cash_flow", None)
    if fcf is not None:
        return float(fcf)
    operating_cash_flow = getattr(row, "operating_cash_flow", None)
    capital_expenditure = getattr(row, "capital_expenditure", None)
    if operating_cash_flow is not None and capital_expenditure is not None:
        return float(operating_cash_flow) - float(capital_expenditure)
    return None


def detect_company_type(
    row: Any = None,
    fundamentals_history: Any = None,
    sector_hint: Any = None,
) -> CompanyType:
    """Classify a company; see the module docstring for the decision order.

    Args:
        row: The latest :class:`NormalizedFinancials` row (may be None).
        fundamentals_history: Newest-first rows used for the hyper-growth
            revenue CAGR (may be None when only the latest row is known).
        sector_hint: A sector label such as "Financial Services" or the
            row's ``sector`` field (may be None).
    """
    if _hint_matches(sector_hint, _FINANCIAL_KEYWORDS):
        return CompanyType.FINANCIAL
    if _hint_matches(sector_hint, _REIT_KEYWORDS):
        return CompanyType.REIT
    if _hint_matches(sector_hint, _UTILITY_KEYWORDS):
        return CompanyType.UTILITY
    if _financial_fingerprint(row):
        return CompanyType.FINANCIAL
    if row is not None:
        cagr = _revenue_cagr(fundamentals_history)
        fcf = _free_cash_flow(row)
        if cagr is not None and cagr > 0.25 and fcf is not None and fcf < 0:
            return CompanyType.HYPER_GROWTH
    if row is None:
        return CompanyType.UNKNOWN
    return CompanyType.STANDARD


def is_financial(row: Any = None, sector_hint: Any = None) -> bool:
    """True for banks/insurers where debt- and inventory-based rules break."""
    return detect_company_type(row, sector_hint=sector_hint) is CompanyType.FINANCIAL


def is_reit(row: Any = None, sector_hint: Any = None) -> bool:
    """True for real estate investment trusts."""
    return detect_company_type(row, sector_hint=sector_hint) is CompanyType.REIT


def is_utility(row: Any = None, sector_hint: Any = None) -> bool:
    """True for regulated utilities."""
    return detect_company_type(row, sector_hint=sector_hint) is CompanyType.UTILITY


def is_hyper_growth(
    row: Any = None, history: Any = None, sector_hint: Any = None
) -> bool:
    """True when revenue CAGR > 25% while free cash flow is negative."""
    return (
        detect_company_type(row, fundamentals_history=history, sector_hint=sector_hint)
        is CompanyType.HYPER_GROWTH
    )
