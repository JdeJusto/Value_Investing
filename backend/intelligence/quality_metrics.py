"""Reusable quality metrics computed from normalized financials.

This module is the core layer of the intelligence engine: every scoring
module (Buffett filter, moat analysis, composite model) consumes these
metrics. It depends only on :class:`NormalizedFinancials` and never
touches providers.
"""

from typing import Optional

from backend.analytics.ratios.roic import RoicCalculator
from backend.domain.value_objects.financials_normalized import NormalizedFinancials

DEFAULT_TAX_RATE = 0.21

_roic = RoicCalculator()


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def ordered_asc(rows: list[NormalizedFinancials]) -> list[NormalizedFinancials]:
    """Return rows sorted by fiscal year ascending (oldest first)."""
    return sorted(rows, key=lambda r: r.fiscal_year)


def effective_tax_rate(row: NormalizedFinancials) -> float | None:
    """Effective tax rate from the statements, with a sane default."""
    if row.tax_provision is not None and row.pretax_income and row.pretax_income != 0:
        return row.tax_provision / row.pretax_income
    return DEFAULT_TAX_RATE


def equity_of(row: NormalizedFinancials) -> float | None:
    """Book value of equity, derived from assets minus liabilities when needed."""
    if row.stockholders_equity is not None:
        return row.stockholders_equity
    if row.total_assets is not None and row.total_liabilities is not None:
        return row.total_assets - row.total_liabilities
    return None


def _mean_present(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def _stddev(values: list[float]) -> float | None:
    mean = _mean_present(values)
    if mean is None or len(values) < 2:
        return None
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return variance**0.5


# ----------------------------------------------------------------------
# Capital efficiency
# ----------------------------------------------------------------------
def roic(row: NormalizedFinancials) -> float | None:
    """Proper return on invested capital: NOPAT / (debt + equity - cash)."""
    tax_rate = effective_tax_rate(row)
    return _roic.calculate(
        ebit=row.ebit,
        tax_rate=tax_rate,
        total_debt=row.total_debt,
        equity=equity_of(row),
        cash=row.cash_and_equivalents,
    )


def multi_year_roic(rows: list[NormalizedFinancials]) -> list[float | None]:
    """ROIC for every available year, aligned with :func:`ordered_asc`."""
    return [roic(r) for r in ordered_asc(rows)]


def roe(row: NormalizedFinancials) -> float | None:
    """Return on equity: net income / book equity."""
    eq = equity_of(row)
    if row.net_income is None or not eq:
        return None
    return row.net_income / eq


def multi_year_roe(rows: list[NormalizedFinancials]) -> list[float | None]:
    return [roe(r) for r in ordered_asc(rows)]


# ----------------------------------------------------------------------
# Earnings quality
# ----------------------------------------------------------------------
def owner_earnings(row: NormalizedFinancials) -> float | None:
    """Owner earnings: net income + depreciation - capex (Buffett)."""
    if row.net_income is None:
        return None
    depreciation = row.depreciation_amortization or 0.0
    capex = row.capital_expenditure or 0.0
    return row.net_income + depreciation - capex


def earnings_cv(rows: list[NormalizedFinancials]) -> float | None:
    """Coefficient of variation of net income (lower = more consistent)."""
    income = [r.net_income for r in ordered_asc(rows) if r.net_income is not None]
    if len(income) < 2:
        return None
    mean = sum(income) / len(income)
    if mean == 0:
        return None
    sd = _stddev(income)
    return sd / abs(mean) if sd is not None else None


def max_yoy_decline(rows: list[NormalizedFinancials]) -> float | None:
    """Largest year-over-year drop in net income, as a negative fraction."""
    ordered = ordered_asc(rows)
    declines: list[float] = []
    for prev, curr in zip(ordered, ordered[1:]):
        if prev.net_income is not None and curr.net_income is not None:
            if prev.net_income != 0:
                declines.append((curr.net_income - prev.net_income) / prev.net_income)
    return min(declines) if declines else None


# ----------------------------------------------------------------------
# Growth
# ----------------------------------------------------------------------
def revenue_cagr(rows: list[NormalizedFinancials]) -> float | None:
    """Compound annual growth rate of revenue over the available period."""
    ordered = [r.revenue for r in ordered_asc(rows) if r.revenue is not None]
    if len(ordered) < 2 or ordered[0] <= 0 or ordered[-1] <= 0:
        return None
    years = len(ordered) - 1
    return (ordered[-1] / ordered[0]) ** (1.0 / years) - 1.0


def fcf_growth(rows: list[NormalizedFinancials]) -> float | None:
    """FCF trend: change between the first 3-year and last 3-year averages.

    Requires at least three FCF years: with exactly two the first and last
    windows are the same pair of values and would trivially produce 0.0,
    which is a misleading "flat" signal rather than an unknown trend.
    """
    ordered = ordered_asc(rows)
    fcfs = [r.free_cash_flow for r in ordered if r.free_cash_flow is not None]
    if len(fcfs) < 3:
        return None
    first = sum(fcfs[:3]) / min(len(fcfs), 3)
    last = sum(fcfs[-3:]) / min(len(fcfs), 3)
    if first == 0:
        return None
    return (last - first) / abs(first)


def positive_fcf_ratio(rows: list[NormalizedFinancials]) -> float | None:
    """Share of years with positive free cash flow."""
    ordered = ordered_asc(rows)
    fcfs = [r.free_cash_flow for r in ordered if r.free_cash_flow is not None]
    if not fcfs:
        return None
    return sum(1 for f in fcfs if f > 0) / len(fcfs)


# ----------------------------------------------------------------------
# Margins and capital intensity
# ----------------------------------------------------------------------
def gross_margin(row: NormalizedFinancials) -> float | None:
    if row.revenue and row.cogs is not None and row.revenue != 0:
        return (row.revenue - row.cogs) / row.revenue
    return None


def margin_statistics(
    rows: list[NormalizedFinancials],
) -> dict[str, float | None]:
    """Mean and variability of the gross margin plus its linear trend.

    ``trend`` is the least-squares slope of the margin over time, in
    percentage points per year (small negative values mean stability).
    """
    ordered = ordered_asc(rows)
    margins: list[tuple[int, float]] = []
    for i, r in enumerate(ordered):
        m = gross_margin(r)
        if m is not None:
            margins.append((i, m))
    if not margins:
        return {"mean": None, "cv": None, "trend": None}

    values = [m for _, m in margins]
    mean = sum(values) / len(values)
    sd = _stddev(values)
    cv = sd / mean if sd is not None and mean != 0 else None

    n = len(margins)
    xs = [x for x, _ in margins]
    if n >= 2 and max(xs) > min(xs):
        x_mean = sum(xs) / n
        y_mean = mean
        denom = sum((x - x_mean) ** 2 for x in xs)
        trend = (
            sum((x - x_mean) * (y - y_mean) for (x, y) in margins) / denom
            if denom != 0
            else 0.0
        )
    else:
        trend = 0.0
    return {"mean": mean, "cv": cv, "trend": trend}


def capital_intensity(rows: list[NormalizedFinancials]) -> float | None:
    """Average capex / revenue (higher = more asset-heavy)."""
    ordered = ordered_asc(rows)
    ratios: list[float] = []
    for r in ordered:
        if r.revenue and r.capital_expenditure is not None and r.revenue != 0:
            ratios.append(r.capital_expenditure / r.revenue)
    return _mean_present(ratios)


def revenue_cv(rows: list[NormalizedFinancials]) -> float | None:
    """Coefficient of variation of revenue (lower = more predictable)."""
    revenues = [r.revenue for r in ordered_asc(rows) if r.revenue is not None]
    if len(revenues) < 2:
        return None
    mean = sum(revenues) / len(revenues)
    if mean == 0:
        return None
    sd = _stddev(revenues)
    return sd / mean if sd is not None else None


# ----------------------------------------------------------------------
# Aggregated quality metrics
# ----------------------------------------------------------------------
def debt_trend(rows: list[NormalizedFinancials]) -> float | None:
    """Change in debt-to-equity between early and recent years (fraction)."""
    ordered = ordered_asc(rows)
    ratios: list[float | None] = []
    for r in ordered:
        eq = equity_of(r)
        if r.total_debt is not None and eq:
            ratios.append(r.total_debt / eq)
    present = [v for v in ratios if v is not None]
    if len(present) < 2:
        return None
    early = sum(present[:3]) / min(len(present), 3)
    recent = sum(present[-3:]) / min(len(present), 3)
    if early == 0:
        return None
    return (recent - early) / abs(early)


def net_income_change(rows: list[NormalizedFinancials]) -> float | None:
    """Year-over-year net income change for the latest year (fraction)."""
    ordered = ordered_asc(rows)
    if len(ordered) < 2:
        return None
    prev, last = ordered[-2], ordered[-1]
    if prev.net_income is None or not last.net_income:
        return None
    if prev.net_income == 0:
        return None
    return (last.net_income - prev.net_income) / abs(prev.net_income)


def compute_quality_metrics(
    rows: list[NormalizedFinancials],
) -> dict[str, float | None]:
    """Compute the full metric set once, for reuse across scoring modules."""
    roes = [v for v in multi_year_roe(rows) if v is not None]
    roics = [v for v in multi_year_roic(rows) if v is not None]
    ordered = ordered_asc(rows)
    if not ordered:
        # No history at all: every metric is unknown. Never crash on an
        # empty history (e.g. a company whose rows were all filtered out).
        return {
            "roic_mean": None,
            "roic_strong_years": None,
            "roe_mean": None,
            "book_value_per_share": None,
            "owner_earnings": None,
            "earnings_cv": None,
            "max_yoy_decline": None,
            "revenue_cagr": None,
            "revenue_cv": None,
            "gross_margin_mean": None,
            "gross_margin_cv": None,
            "gross_margin_trend": None,
            "capital_intensity": None,
            "positive_fcf_ratio": None,
            "fcf_growth": None,
            "debt_to_equity": None,
            "interest_coverage": None,
            "debt_trend": None,
            "net_income_change": None,
            "retained_earnings_positive": None,
        }
    last = ordered[-1]
    margins = margin_statistics(rows)
    equity = equity_of(last)
    interest = (
        last.ebit / last.interest_expense
        if last.ebit is not None
        and last.interest_expense is not None
        and last.interest_expense != 0
        else None
    )
    return {
        "roic_mean": _mean_present(roics),
        "roic_strong_years": (
            sum(1 for v in roics if v is not None and v >= 0.12) / len(roics)
            if roics
            else None
        ),
        "roe_mean": _mean_present(roes),
        "book_value_per_share": (
            equity / last.shares_outstanding
            if equity is not None and last.shares_outstanding
            else None
        ),
        "owner_earnings": owner_earnings(last),
        "earnings_cv": earnings_cv(rows),
        "max_yoy_decline": max_yoy_decline(rows),
        "revenue_cagr": revenue_cagr(rows),
        "revenue_cv": revenue_cv(rows),
        "gross_margin_mean": margins["mean"],
        "gross_margin_cv": margins["cv"],
        "gross_margin_trend": margins["trend"],
        "capital_intensity": capital_intensity(rows),
        "positive_fcf_ratio": positive_fcf_ratio(rows),
        "fcf_growth": fcf_growth(rows),
        "debt_to_equity": (
            last.total_debt / equity if last.total_debt is not None and equity else None
        ),
        "interest_coverage": interest,
        "debt_trend": debt_trend(rows),
        "net_income_change": net_income_change(rows),
        "retained_earnings_positive": (
            True
            if last.retained_earnings is not None and last.retained_earnings >= 0
            else False if last.retained_earnings is not None else None
        ),
    }
