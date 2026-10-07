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
2. Balance-sheet / cash-flow fingerprint of a financial company — applied
   only when no sector hint is known (a known non-financial sector wins:
   Ford's captive finance arm looks bank-like by leverage, but the sector
   says cyclical):
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


class FinancialSubtype(str, Enum):
    """Granular financial-company classification for precise N/A messaging.

    Subtypes are detected from the sector hint (when available) or from
    balance-sheet fingerprints. A company typed as FINANCIAL may be further
    classified as one of these, or FINANCIAL_OTHER when the specific kind
    cannot be determined.
    """

    BANK = "BANK"  # depository banks, credit unions
    INSURANCE = "INSURANCE"  # life, P&C, reinsurance
    PAYMENTS = "PAYMENTS"  # payment processors, networks (Visa, Mastercard)
    ASSET_MANAGEMENT = "ASSET_MANAGEMENT"  # asset managers, ETF providers
    CAPITAL_MARKETS = "CAPITAL_MARKETS"  # broker-dealers, exchanges
    FINANCIAL_OTHER = "FINANCIAL_OTHER"  # diversified financials, other


#: Sector-hint keywords per type. Matched as case-insensitive substrings so
#: provider labels ("Financial Services", "Banks—Diversified", "Real Estate
#: Investment Trusts") keep resolving without a brittle exact-match list.
_FINANCIAL_KEYWORDS = (
    "financial",
    "bank",
    "credit union",
    "insurance",
    "payment",
    "asset management",
    "asset manager",
    "capital markets",
    "capital market",
    "broker",
    "exchange",
    "diversified financial",
    "financial services",
)
_REIT_KEYWORDS = ("real estate", "reit")
_UTILITY_KEYWORDS = ("utilities", "utility")

#: Subtype keywords ordered by specificity (first match wins).
_FINANCIAL_SUBTYPE_KEYWORDS = (
    ("bank", FinancialSubtype.BANK),
    ("credit union", FinancialSubtype.BANK),
    ("insurance", FinancialSubtype.INSURANCE),
    ("reinsurance", FinancialSubtype.INSURANCE),
    ("payment", FinancialSubtype.PAYMENTS),
    ("asset management", FinancialSubtype.ASSET_MANAGEMENT),
    ("asset manager", FinancialSubtype.ASSET_MANAGEMENT),
    ("capital market", FinancialSubtype.CAPITAL_MARKETS),
    ("broker", FinancialSubtype.CAPITAL_MARKETS),
    ("exchange", FinancialSubtype.CAPITAL_MARKETS),
    ("diversified financial", FinancialSubtype.FINANCIAL_OTHER),
    ("financial services", FinancialSubtype.FINANCIAL_OTHER),
)


def _hint_matches(sector_hint: Any, keywords: tuple[str, ...]) -> bool:
    """True when a sector hint contains any keyword (case-insensitive)."""
    if not sector_hint:
        return False
    lowered = str(sector_hint).strip().lower()
    return any(keyword in lowered for keyword in keywords)


def _detect_financial_subtype(sector_hint: Any) -> FinancialSubtype:
    """Return the most specific FinancialSubtype from a sector hint.

    Falls back to FINANCIAL_OTHER when the hint is known-financial but no
    subtype keyword matches.
    """
    if not sector_hint:
        return FinancialSubtype.FINANCIAL_OTHER
    lowered = str(sector_hint).strip().lower()
    for keyword, subtype in _FINANCIAL_SUBTYPE_KEYWORDS:
        if keyword in lowered:
            return subtype
    return FinancialSubtype.FINANCIAL_OTHER


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
    # A known non-financial sector wins over the balance-sheet fingerprint:
    # Ford's captive finance arm pushes total_liabilities/total_assets over
    # 0.85, but the company is a cyclical automaker, not a bank. The
    # fingerprint remains the fallback when no sector is known.
    if not sector_hint and _financial_fingerprint(row):
        return CompanyType.FINANCIAL
    if row is not None:
        cagr = _revenue_cagr(fundamentals_history)
        fcf = _free_cash_flow(row)
        if cagr is not None and cagr > 0.25 and fcf is not None and fcf < 0:
            return CompanyType.HYPER_GROWTH
    if row is None:
        return CompanyType.UNKNOWN
    return CompanyType.STANDARD


def detect_financial_subtype(
    row: Any = None,
    fundamentals_history: Any = None,
    sector_hint: Any = None,
) -> FinancialSubtype:
    """Classify a financial company into a granular subtype.

    Returns FINANCIAL_OTHER when the company is not FINANCIAL, or when the
    specific kind cannot be determined.

    Args:
        row: The latest :class:`NormalizedFinancials` row (may be None).
        fundamentals_history: Newest-first rows (unused; for API symmetry).
        sector_hint: A sector label such as "Banks—Diversified" or the
            row's ``sector`` field (may be None).
    """
    # Only meaningful for financial companies; return OTHER otherwise.
    company_type = detect_company_type(row, fundamentals_history, sector_hint)
    if company_type is not CompanyType.FINANCIAL:
        return FinancialSubtype.FINANCIAL_OTHER
    return _detect_financial_subtype(sector_hint)


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


#: Ticker overrides for financial subtype when sector is generic "Financial Services"
#: or missing. Source: company legal names in FDB (Visa -> PAYMENTS, etc.).
_FINANCIAL_SUBTYPE_TICKER_OVERRIDE = {
    # Payments
    "V": FinancialSubtype.PAYMENTS,
    "MA": FinancialSubtype.PAYMENTS,
    "PYPL": FinancialSubtype.PAYMENTS,
    "SQ": FinancialSubtype.PAYMENTS,
    "FISV": FinancialSubtype.PAYMENTS,
    "FIS": FinancialSubtype.PAYMENTS,
    "GPN": FinancialSubtype.PAYMENTS,
    "ADP": FinancialSubtype.PAYMENTS,
    "PAYX": FinancialSubtype.PAYMENTS,
    # Asset management
    "BLK": FinancialSubtype.ASSET_MANAGEMENT,
    "TROW": FinancialSubtype.ASSET_MANAGEMENT,
    "IVZ": FinancialSubtype.ASSET_MANAGEMENT,
    "AMG": FinancialSubtype.ASSET_MANAGEMENT,
    "BEN": FinancialSubtype.ASSET_MANAGEMENT,
    "JHG": FinancialSubtype.ASSET_MANAGEMENT,
    "APO": FinancialSubtype.ASSET_MANAGEMENT,
    "KKR": FinancialSubtype.ASSET_MANAGEMENT,
    "BX": FinancialSubtype.ASSET_MANAGEMENT,
    "CG": FinancialSubtype.ASSET_MANAGEMENT,
    # Capital markets / broker-dealers
    "GS": FinancialSubtype.CAPITAL_MARKETS,
    "MS": FinancialSubtype.CAPITAL_MARKETS,
    "SCHW": FinancialSubtype.CAPITAL_MARKETS,
    "IBKR": FinancialSubtype.CAPITAL_MARKETS,
    "NDAQ": FinancialSubtype.CAPITAL_MARKETS,
    "CME": FinancialSubtype.CAPITAL_MARKETS,
    "ICE": FinancialSubtype.CAPITAL_MARKETS,
    # Banks
    "JPM": FinancialSubtype.BANK,
    "BAC": FinancialSubtype.BANK,
    "WFC": FinancialSubtype.BANK,
    "C": FinancialSubtype.BANK,
    "USB": FinancialSubtype.BANK,
    "PNC": FinancialSubtype.BANK,
    "TFC": FinancialSubtype.BANK,
    "COF": FinancialSubtype.BANK,
    # Insurance
    "AIG": FinancialSubtype.INSURANCE,
    "MET": FinancialSubtype.INSURANCE,
    "PRU": FinancialSubtype.INSURANCE,
    "TRV": FinancialSubtype.INSURANCE,
    "ALL": FinancialSubtype.INSURANCE,
    "CB": FinancialSubtype.INSURANCE,
    "PGR": FinancialSubtype.INSURANCE,
    "HIG": FinancialSubtype.INSURANCE,
}


def financial_na_reason(
    row: Any = None,
    fundamentals_history: Any = None,
    sector_hint: Any = None,
    ticker: str | None = None,
) -> str:
    """Return the N/A reason string for a financial company.

    The message is tailored to the detected financial subtype so users
    understand why the methodology doesn't apply. Falls back to the
    generic reason when the company is not financial or the subtype is
    indeterminate.

    If ``ticker`` is provided and matches a known override, that subtype
    takes precedence over sector-based detection (useful when the sector
    is generic "Financial Services" or missing).
    """
    # Ticker override takes precedence for well-known financials
    if ticker:
        override = _FINANCIAL_SUBTYPE_TICKER_OVERRIDE.get(ticker.upper())
        if override is not None:
            subtype = override
        else:
            subtype = detect_financial_subtype(row, fundamentals_history, sector_hint)
    else:
        subtype = detect_financial_subtype(row, fundamentals_history, sector_hint)

    if subtype is FinancialSubtype.BANK:
        return "bank — rules do not apply"
    if subtype is FinancialSubtype.INSURANCE:
        return "insurance company — rules do not apply"
    if subtype is FinancialSubtype.PAYMENTS:
        return "payment company — rules do not apply"
    if subtype is FinancialSubtype.ASSET_MANAGEMENT:
        return "asset manager — rules do not apply"
    if subtype is FinancialSubtype.CAPITAL_MARKETS:
        return "capital markets firm — rules do not apply"
    return "financial company — rules do not apply"
