"""Buffett/Munger quantitative rules (public-knowledge reconstruction).

The original wrapper delegated to the 4-pillar ``buffett_engine`` score. This
module keeps the same philosophy but makes every criterion explicit and
weightable, in the style of the v0.26.0 Graham deep expansion.

Sources are the published Berkshire letters and *The Essays of Warren Buffett*.
Where a criterion is a common public-knowledge derivation (ROIC definition,
owner-earnings proxy, DCF margin), the source is labelled as an
approximation rather than attributed to a specific page.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import Rule, SourceRef

_BOOK = "Berkshire Hathaway shareholder letters"
_EDITION = "1977-2023 (selected letters)"
_YEAR = 1977


def _letter(page: str, caution: str) -> SourceRef:
    return SourceRef(
        book=_BOOK,
        edition=_EDITION,
        year=_YEAR,
        page=page,
        era="1977-2023",
        us_caution=caution,
    )


def _public(note: str) -> SourceRef:
    return _letter("public-knowledge derivation", f"approximation — {note}")


#: Rule categories used by the CLI groups and docs.
CATEGORIES = (
    "moat",
    "financial_strength",
    "earnings_quality",
    "capital_allocation",
    "valuation",
    "management",
)


@dataclass(frozen=True)
class BuffettResult:
    """Outcome of one rule (``passed=None`` means insufficient data)."""

    rule_id: str
    name: str
    category: str
    weight: int
    passed: bool | None
    value: float | None
    threshold: float | None
    detail: str


@dataclass(frozen=True)
class BuffettCheck:
    rule_id: str
    name: str
    category: str
    weight: int
    description: str
    source: SourceRef
    evaluate: Callable[
        [list[NormalizedFinancials], float | None, object | None], BuffettResult
    ]

    def rule(self) -> Rule:
        return Rule(
            id=self.rule_id,
            name=self.name,
            description=self.description,
            kind="INFERRED",
            source=self.source,
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _latest(rows: list[NormalizedFinancials]) -> NormalizedFinancials | None:
    return rows[0] if rows else None


def _shares(row: NormalizedFinancials) -> float:
    shares = row.shares_outstanding or 0
    factor = row.split_adjustment_factor or 1.0
    return float(shares) * float(factor)


def _eps(row: NormalizedFinancials) -> float | None:
    shares = _shares(row)
    if shares <= 0 or row.net_income is None:
        return None
    return float(row.net_income) / shares


def _gross_margin(row: NormalizedFinancials) -> float | None:
    if row.revenue is None or row.revenue == 0:
        return None
    if row.gross_profit is not None:
        return float(row.gross_profit) / float(row.revenue)
    if row.cogs is not None:
        return 1.0 - float(row.cogs) / float(row.revenue)
    return None


def _operating_margin(row: NormalizedFinancials) -> float | None:
    if row.revenue is None or row.revenue == 0:
        return None
    ebit = row.ebit if row.ebit is not None else row.operating_income
    if ebit is None:
        return None
    return float(ebit) / float(row.revenue)


def _tax_rate(row: NormalizedFinancials) -> float:
    if (
        row.tax_provision is not None
        and row.pretax_income is not None
        and row.pretax_income > 0
    ):
        return max(0.0, min(0.5, float(row.tax_provision) / float(row.pretax_income)))
    return 0.21


def _roic(row: NormalizedFinancials) -> float | None:
    """NOPAT / (debt + equity - cash), the standard public-knowledge ROIC."""
    ebit = row.ebit if row.ebit is not None else row.operating_income
    if ebit is None:
        return None
    invested = (
        float(row.total_debt or 0.0)
        + float(row.stockholders_equity or 0.0)
        - float(row.cash_and_equivalents or 0.0)
    )
    if invested <= 0:
        return None
    return float(ebit) * (1.0 - _tax_rate(row)) / invested


def _fcf(row: NormalizedFinancials) -> float | None:
    if row.free_cash_flow is not None:
        return float(row.free_cash_flow)
    if row.operating_cash_flow is not None and row.capital_expenditure is not None:
        return float(row.operating_cash_flow) - float(row.capital_expenditure)
    return None


def _owner_earnings(row: NormalizedFinancials) -> float | None:
    """Net income + D&A - capex (maintenance capex is not in FDB)."""
    if row.net_income is None:
        return None
    if row.depreciation_amortization is None or row.capital_expenditure is None:
        return None
    return (
        float(row.net_income)
        + float(row.depreciation_amortization)
        - float(row.capital_expenditure)
    )


def _result(
    check: BuffettCheck,
    passed: bool | None,
    detail: str,
    *,
    value: float | None = None,
    threshold: float | None = None,
) -> BuffettResult:
    return BuffettResult(
        rule_id=check.rule_id,
        name=check.name,
        category=check.category,
        weight=check.weight,
        passed=passed,
        value=value,
        threshold=threshold,
        detail=detail,
    )


def _cagr(values: list[float]) -> float | None:
    """CAGR from newest-first positive values (year gaps ignored)."""
    if len(values) < 2:
        return None
    newest, oldest = values[0], values[-1]
    if newest <= 0 or oldest <= 0 or newest == oldest:
        return 0.0 if newest == oldest else None
    return (newest / oldest) ** (1.0 / (len(values) - 1)) - 1.0


# ---------------------------------------------------------------------------
# moat / quality
# ---------------------------------------------------------------------------
def _roic_current(rows, _price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.roic_current"]
    latest = _latest(rows)
    roic = _roic(latest) if latest is not None else None
    if roic is None:
        return _result(check, None, "ROIC not computable (EBIT or capital missing)")
    return _result(
        check,
        roic >= 0.15,
        f"ROIC {roic:.1%} vs >= 15%",
        value=roic,
        threshold=0.15,
    )


def _roic_persistence(rows, _price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.roic_10y_persistence"]
    values = [value for row in rows[:10] if (value := _roic(row)) is not None]
    if len(values) < 5:
        return _result(check, None, f"only {len(values)} years of ROIC")
    passed = all(value >= 0.15 for value in values)
    years_above = sum(1 for value in values if value >= 0.15)
    return _result(
        check,
        passed,
        f"ROIC >= 15% in {years_above}/{len(values)} years",
        value=float(years_above),
        threshold=float(len(values)),
    )


def _gross_margin_stability(rows, _price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.gross_margin_stability"]
    margins = [value for row in rows[:5] if (value := _gross_margin(row)) is not None]
    if len(margins) < 3:
        return _result(check, None, f"only {len(margins)} years of gross margin")
    deviation = statistics.pstdev(margins)
    return _result(
        check,
        deviation < 0.05,
        f"gross margin stdev {deviation:.1%} vs < 5pp",
        value=deviation,
        threshold=0.05,
    )


def _operating_margin_trend(rows, _price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.operating_margin_trend"]
    margins = [
        value for row in rows[:5] if (value := _operating_margin(row)) is not None
    ]
    if len(margins) < 3:
        return _result(check, None, f"only {len(margins)} years of operating margin")
    latest, oldest = margins[0], margins[-1]
    return _result(
        check,
        latest >= oldest - 0.02 and latest > 0,
        f"operating margin {oldest:.1%} -> {latest:.1%} (not down > 2pp)",
        value=latest,
        threshold=oldest - 0.02,
    )


def _pricing_power(rows, _price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.pricing_power"]
    revenues = [
        float(row.revenue)
        for row in rows[:5]
        if row.revenue is not None and row.revenue > 0
    ]
    margins = [value for row in rows[:5] if (value := _gross_margin(row)) is not None]
    if len(revenues) < 3 or len(margins) < 3:
        return _result(check, None, "needs 3 years of revenue and gross margin")
    growth = _cagr(revenues)
    if growth is None:
        return _result(check, None, "revenue CAGR not computable")
    margin_change = margins[0] - margins[-1]
    passed = growth >= 0.03 and margin_change >= -0.02
    return _result(
        check,
        passed,
        f"revenue CAGR {growth:.1%} (>= 3%) and gross margin change {margin_change:+.1%}",
        value=growth,
        threshold=0.03,
    )


# ---------------------------------------------------------------------------
# financial strength
# ---------------------------------------------------------------------------
def _debt_to_equity(rows, _price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.debt_equity_below_1"]
    latest = _latest(rows)
    if (
        latest is None
        or latest.total_debt is None
        or latest.stockholders_equity is None
    ):
        return _result(check, None, "debt or equity missing")
    if latest.stockholders_equity <= 0:
        return _result(check, False, "negative book equity")
    ratio = float(latest.total_debt) / float(latest.stockholders_equity)
    return _result(
        check,
        ratio < 1.0,
        f"debt/equity {ratio:.2f} vs < 1.0",
        value=ratio,
        threshold=1.0,
    )


def _interest_coverage(rows, _price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.interest_coverage_10"]
    latest = _latest(rows)
    if latest is None:
        return _result(check, None, "no fundamentals")
    ebit = latest.ebit if latest.ebit is not None else latest.operating_income
    if ebit is None:
        return _result(check, None, "EBIT missing")
    interest = latest.interest_expense
    if interest is None:
        if latest.total_debt in (None, 0, 0.0):
            return _result(check, True, "no interest expense (debt-free)")
        return _result(check, None, "interest expense missing")
    if interest <= 0:
        return _result(check, True, "no interest expense", value=0.0, threshold=10.0)
    coverage = float(ebit) / float(interest)
    return _result(
        check,
        coverage >= 10.0,
        f"interest coverage {coverage:.1f}x vs >= 10x",
        value=coverage,
        threshold=10.0,
    )


def _current_ratio(rows, _price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.current_ratio_1_5"]
    latest = _latest(rows)
    if (
        latest is None
        or latest.current_assets is None
        or latest.current_liabilities is None
    ):
        return _result(check, None, "current assets/liabilities missing")
    if latest.current_liabilities <= 0:
        return _result(check, None, "non-positive current liabilities")
    ratio = float(latest.current_assets) / float(latest.current_liabilities)
    return _result(
        check,
        ratio >= 1.5,
        f"current ratio {ratio:.2f} vs >= 1.5",
        value=ratio,
        threshold=1.5,
    )


def _fcf_positive_5y(rows, _price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.fcf_positive_5y"]
    values = [value for row in rows[:5] if (value := _fcf(row)) is not None]
    if len(values) < 3:
        return _result(check, None, f"only {len(values)} years of FCF")
    positive = sum(1 for value in values if value > 0)
    return _result(
        check,
        positive == len(values),
        f"FCF > 0 in {positive}/{len(values)} years",
        value=float(positive),
        threshold=float(len(values)),
    )


# ---------------------------------------------------------------------------
# earnings quality
# ---------------------------------------------------------------------------
def _net_margin(rows, _price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.net_margin_10"]
    latest = _latest(rows)
    if latest is None or latest.revenue in (None, 0) or latest.net_income is None:
        return _result(check, None, "revenue or net income missing")
    margin = float(latest.net_income) / float(latest.revenue)
    return _result(
        check,
        margin >= 0.10,
        f"net margin {margin:.1%} vs >= 10%",
        value=margin,
        threshold=0.10,
    )


def _fcf_conversion(rows, _price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.fcf_conversion_80"]
    latest = _latest(rows)
    if latest is None or latest.net_income is None:
        return _result(check, None, "net income missing")
    fcf = _fcf(latest)
    if fcf is None:
        return _result(check, None, "FCF missing")
    if latest.net_income <= 0:
        return _result(
            check, False, "negative net income with positive FCF", value=None
        )
    ratio = fcf / float(latest.net_income)
    return _result(
        check,
        ratio >= 0.80,
        f"FCF conversion {ratio:.0%} vs >= 80%",
        value=ratio,
        threshold=0.80,
    )


def _earnings_consistency(rows, _price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.earnings_consistency"]
    # Five years is one business cycle: long enough to catch fragility,
    # short enough not to be dominated by a single old recession year.
    eps = [value for row in rows[:5] if (value := _eps(row)) is not None]
    if len(eps) < 4:
        return _result(check, None, f"only {len(eps)} EPS years")
    rates = [
        eps[index] / eps[index + 1] - 1.0
        for index in range(len(eps) - 1)
        if eps[index + 1] > 0
    ]
    if len(rates) < 3:
        return _result(check, None, "not enough positive EPS history")
    deviation = statistics.pstdev(rates)
    return _result(
        check,
        deviation < 0.20,
        f"EPS growth stdev {deviation:.1%} vs < 20% (5y)",
        value=deviation,
        threshold=0.20,
    )


def _owner_earnings_positive(rows, _price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.owner_earnings_positive"]
    latest = _latest(rows)
    value = _owner_earnings(latest) if latest is not None else None
    if value is None:
        return _result(check, None, "net income, D&A or capex missing")
    return _result(
        check,
        value > 0,
        f"owner earnings ${value:,.0f} (NI + D&A - capex proxy)",
        value=value,
        threshold=0.0,
    )


# ---------------------------------------------------------------------------
# capital allocation
# ---------------------------------------------------------------------------
def _no_dilution(rows, _price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.no_dilution_5y"]
    shares = [value for row in rows[:6] if (value := _shares(row)) > 0]
    if len(shares) < 3:
        return _result(check, None, f"only {len(shares)} years of share counts")
    newest, oldest = shares[0], shares[-1]
    change = newest / oldest - 1.0
    return _result(
        check,
        change <= 0.02,
        f"shares outstanding change {change:+.1%} vs <= +2%",
        value=change,
        threshold=0.02,
    )


def _buybacks(rows, _price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.buybacks_3_of_5y"]
    window = [row for row in rows[:6] if row is not None]
    if len(window) < 3:
        return _result(check, None, f"only {len(window)} years of share data")
    count = 0
    for index in range(len(window) - 1):
        newer, older = window[index], window[index + 1]
        newer_shares, older_shares = _shares(newer), _shares(older)
        repurchased = (newer.repurchase_of_stock or 0) > 0
        if (
            newer_shares > 0
            and older_shares > 0
            and newer_shares < older_shares * 0.995
        ) or repurchased:
            count += 1
    return _result(
        check,
        count >= 3,
        f"buybacks in {count}/{len(window) - 1} year-over-year periods",
        value=float(count),
        threshold=3.0,
    )


# ---------------------------------------------------------------------------
# valuation
# ---------------------------------------------------------------------------
def _dcf_margin_of_safety(rows, price, dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.dcf_margin_of_safety_20"]
    if price is None:
        return _result(check, None, "no live price")
    margin = getattr(dcf, "margin_of_safety", None) if dcf is not None else None
    if margin is None:
        return _result(check, None, "DCF not computable")
    intrinsic = getattr(dcf, "intrinsic_value_per_share", None)
    detail = f"DCF margin {margin:.1%} vs >= 20%"
    if intrinsic is not None:
        detail += f" (intrinsic ${intrinsic:,.2f} vs price ${price:,.2f})"
    return _result(
        check,
        margin >= 0.20,
        detail,
        value=margin,
        threshold=0.20,
    )


def _earnings_yield(rows, price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.earnings_yield_5"]
    if price is None or price <= 0:
        return _result(check, None, "no live price")
    earnings = [row.net_income for row in rows[:3] if row.net_income is not None]
    latest = _latest(rows)
    shares = _shares(latest) if latest is not None else 0
    if len(earnings) < 3 or shares <= 0:
        return _result(check, None, "needs 3 years of earnings and shares")
    average = sum(float(value) for value in earnings) / 3.0
    eps = average / shares
    if eps <= 0:
        return _result(check, None, "EPS not positive")
    yield_value = eps / float(price)
    return _result(
        check,
        yield_value >= 0.05,
        f"earnings yield {yield_value:.1%} vs >= 5%",
        value=yield_value,
        threshold=0.05,
    )


def _pe_below_20(rows, price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.pe_below_20"]
    if price is None or price <= 0:
        return _result(check, None, "no live price")
    earnings = [row.net_income for row in rows[:3] if row.net_income is not None]
    latest = _latest(rows)
    shares = _shares(latest) if latest is not None else 0
    if len(earnings) < 3 or shares <= 0:
        return _result(check, None, "needs 3 years of earnings and shares")
    average = sum(float(value) for value in earnings) / 3.0
    eps = average / shares
    if eps <= 0:
        return _result(check, None, "EPS not positive")
    pe = float(price) / eps
    return _result(
        check,
        pe <= 20.0,
        f"P/E {pe:.1f} vs <= 20",
        value=pe,
        threshold=20.0,
    )


# ---------------------------------------------------------------------------
# management (informational)
# ---------------------------------------------------------------------------
def _insider_ownership(rows, _price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.insider_ownership"]
    return _result(check, None, "insider ownership is not in FDB (informational)")


def _rd_ratio(rows, _price, _dcf) -> BuffettResult:
    check = CHECKS_BY_ID["buffett.rd_ratio_3"]
    latest = _latest(rows)
    if latest is None or latest.revenue in (None, 0):
        return _result(check, None, "revenue missing")
    if latest.research_development is None:
        return _result(check, None, "R&D not reported (not applicable)")
    ratio = float(latest.research_development) / float(latest.revenue)
    return _result(
        check,
        ratio >= 0.03,
        f"R&D/revenue {ratio:.1%} vs >= 3% (informational)",
        value=ratio,
        threshold=0.03,
    )


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
CHECKS: tuple[BuffettCheck, ...] = (
    BuffettCheck(
        "buffett.roic_current",
        "ROIC >= 15%",
        "moat",
        2,
        "Return on invested capital for the latest fiscal year.",
        _public("ROIC = NOPAT / (debt + equity - cash)"),
        _roic_current,
    ),
    BuffettCheck(
        "buffett.roic_10y_persistence",
        "ROIC >= 15% (10y persistence)",
        "moat",
        2,
        "Every available year of the last decade must clear 15% ROIC.",
        _letter("1987 letter (economic goodwill / high returns)", "public paraphrase"),
        _roic_persistence,
    ),
    BuffettCheck(
        "buffett.gross_margin_stability",
        "Stable gross margin",
        "moat",
        1,
        "Standard deviation of the gross margin below 5 percentage points.",
        _public("pricing power proxy"),
        _gross_margin_stability,
    ),
    BuffettCheck(
        "buffett.operating_margin_trend",
        "Operating margin not eroding",
        "moat",
        1,
        "Latest operating margin not more than 2pp below the 5-year base.",
        _public("moat erosion check"),
        _operating_margin_trend,
    ),
    BuffettCheck(
        "buffett.pricing_power",
        "Pricing power",
        "moat",
        1,
        "Revenue CAGR >= 3% without a gross-margin decline above 2pp.",
        _public("inflation pass-through proxy"),
        _pricing_power,
    ),
    BuffettCheck(
        "buffett.debt_equity_below_1",
        "Debt/equity < 1",
        "financial_strength",
        1,
        "Total debt must not exceed book equity.",
        _public("conservative leverage test"),
        _debt_to_equity,
    ),
    BuffettCheck(
        "buffett.interest_coverage_10",
        "Interest coverage >= 10x",
        "financial_strength",
        1,
        "EBIT must cover interest ten times; debt-free companies pass.",
        _letter("1990 letter (financial strength)", "public paraphrase"),
        _interest_coverage,
    ),
    BuffettCheck(
        "buffett.current_ratio_1_5",
        "Current ratio >= 1.5",
        "financial_strength",
        1,
        "Current assets at least 1.5x current liabilities.",
        _public("liquidity test"),
        _current_ratio,
    ),
    BuffettCheck(
        "buffett.fcf_positive_5y",
        "Positive FCF (5y)",
        "financial_strength",
        2,
        "Free cash flow positive in every available year of the last five.",
        _letter("1986 letter (owner earnings)", "public paraphrase"),
        _fcf_positive_5y,
    ),
    BuffettCheck(
        "buffett.net_margin_10",
        "Net margin >= 10%",
        "earnings_quality",
        2,
        "Latest net income at least 10% of revenue.",
        _letter("1979/1987 letters (high-margin franchises)", "public paraphrase"),
        _net_margin,
    ),
    BuffettCheck(
        "buffett.fcf_conversion_80",
        "FCF conversion >= 80%",
        "earnings_quality",
        1,
        "Free cash flow at least 80% of net income.",
        _public("cash conversion proxy"),
        _fcf_conversion,
    ),
    BuffettCheck(
        "buffett.earnings_consistency",
        "Stable EPS growth",
        "earnings_quality",
        1,
        "Standard deviation of yearly EPS growth below 20%.",
        _public("earnings predictability"),
        _earnings_consistency,
    ),
    BuffettCheck(
        "buffett.owner_earnings_positive",
        "Positive owner earnings",
        "earnings_quality",
        1,
        "Net income + D&A - capex > 0 (maintenance capex proxy).",
        _letter("1986 letter (owner earnings)", "approximation: capex used as proxy"),
        _owner_earnings_positive,
    ),
    BuffettCheck(
        "buffett.no_dilution_5y",
        "No dilution (5y)",
        "capital_allocation",
        2,
        "Split-adjusted shares outstanding flat or lower over five years.",
        _letter("1984/1996 letters (share issuance)", "public paraphrase"),
        _no_dilution,
    ),
    BuffettCheck(
        "buffett.buybacks_3_of_5y",
        "Buybacks in 3 of 5 years",
        "capital_allocation",
        1,
        "Share count fell or stock was repurchased in at least three periods.",
        _letter("2011 letter (buybacks)", "public paraphrase"),
        _buybacks,
    ),
    BuffettCheck(
        "buffett.dcf_margin_of_safety_20",
        "DCF margin of safety >= 20%",
        "valuation",
        2,
        "Intrinsic value at least 20% above the current price.",
        _public("two-stage DCF (not-from-canon valuation)"),
        _dcf_margin_of_safety,
    ),
    BuffettCheck(
        "buffett.earnings_yield_5",
        "Earnings yield >= 5%",
        "valuation",
        1,
        "Three-year average EPS divided by price at least 5%.",
        _letter("1977 letter (cheapness vs bonds)", "public paraphrase"),
        _earnings_yield,
    ),
    BuffettCheck(
        "buffett.pe_below_20",
        "P/E <= 20",
        "valuation",
        1,
        "Price no more than 20x three-year average earnings.",
        _public("Buffett tolerates a higher multiple than Graham"),
        _pe_below_20,
    ),
    BuffettCheck(
        "buffett.insider_ownership",
        "Insider ownership",
        "management",
        0,
        "Informational: insider ownership is not in FDB.",
        _public("requires a supplementary data source"),
        _insider_ownership,
    ),
    BuffettCheck(
        "buffett.rd_ratio_3",
        "R&D / revenue >= 3%",
        "management",
        0,
        "Informational innovation proxy; N/A when R&D is not reported.",
        _public("sector-dependent, informational"),
        _rd_ratio,
    ),
)

CHECKS_BY_ID: dict[str, BuffettCheck] = {check.rule_id: check for check in CHECKS}


def run_checks(
    rows: list[NormalizedFinancials],
    price: float | None,
    dcf: object | None = None,
) -> list[BuffettResult]:
    """Evaluate every rule against newest-first fundamentals."""
    return [check.evaluate(rows, price, dcf) for check in CHECKS]
