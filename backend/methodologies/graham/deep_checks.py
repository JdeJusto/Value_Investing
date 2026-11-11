"""Deep Graham checks (Intelligent Investor ch. 14 and derived rules).

The original eight criteria live in ``methodology.py``; this module adds the
quantitative rules the book describes but the first implementation omitted.
Each check returns ``passed=None`` when the data is unavailable, so the
weighted score can decide whether the coverage is still enough.

Sources: ``Ch. 14`` for the rules that are literal book criteria; the rest are
public-knowledge derivations documented as such (Graham Number, NCAV, EPV).
The EPV check uses a fixed 9% discount rate, labelled in the detail.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable
from dataclasses import dataclass

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import Rule, SourceRef

#: Weight per original criterion (1 normal, 2 critical).
OLD_WEIGHTS = {
    "graham.criterion_1_size": 1,
    "graham.criterion_2_current_ratio": 2,
    "graham.criterion_3_debt_vs_working_capital": 1,
    "graham.criterion_4_dividend_history": 1,
    "graham.criterion_5_earnings_growth": 2,
    "graham.criterion_6_pe": 2,
    "graham.criterion_7_pbv": 2,
    "graham.criterion_8_pe_pbv_product": 2,
}

_BOOK = "The Intelligent Investor"
_EDITION = "4th revised, with commentary by Jason Zweig"
_YEAR = 1973
_ERA = "1973"


def _source(page: str, kind: str, caution: str | None = None) -> SourceRef:
    return SourceRef(
        book=_BOOK,
        edition=_EDITION,
        year=_YEAR,
        page=page,
        era=_ERA,
        us_caution=caution or kind,
    )


def _book_rule(page: str, caution: str | None = None) -> SourceRef:
    return _source(page, "book criterion", caution)


def _public_rule(note: str) -> SourceRef:
    return _source("Ch. 14 (derived)", f"public-knowledge approximation — {note}")


def _security_analysis_rule(page: str, caution: str) -> SourceRef:
    """A rule taken from *Security Analysis*, not *The Intelligent Investor*."""
    return SourceRef(
        book="Security Analysis",
        edition="1st ed. (1934)",
        year=1934,
        page=page,
        era="1934",
        us_caution=caution,
    )


@dataclass(frozen=True)
class DeepResult:
    """Outcome of one deep check (``passed=None`` means insufficient data)."""

    rule_id: str
    name: str
    category: str
    weight: int
    passed: bool | None
    value: float | None
    threshold: float | None
    detail: str


@dataclass(frozen=True)
class GrahamCheck:
    rule_id: str
    name: str
    category: str
    weight: int
    description: str
    source: SourceRef
    evaluate: Callable[[list[NormalizedFinancials], float | None], DeepResult]

    def rule(self) -> Rule:
        return Rule(
            id=self.rule_id,
            name=self.name,
            description=self.description,
            kind="INFERRED",
            source=self.source,
        )


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


def _bvps(row: NormalizedFinancials) -> float | None:
    shares = _shares(row)
    if shares <= 0 or row.stockholders_equity is None:
        return None
    return float(row.stockholders_equity) / shares


def _result(
    check: GrahamCheck,
    passed: bool | None,
    detail: str,
    *,
    value: float | None = None,
    threshold: float | None = None,
) -> DeepResult:
    return DeepResult(
        rule_id=check.rule_id,
        name=check.name,
        category=check.category,
        weight=check.weight,
        passed=passed,
        value=value,
        threshold=threshold,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# financial strength
# ---------------------------------------------------------------------------
def _debt_to_equity(rows, _price) -> DeepResult:
    check = CHECKS_BY_ID["graham.deep_debt_to_equity"]
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


def _interest_coverage(rows, _price) -> DeepResult:
    check = CHECKS_BY_ID["graham.deep_interest_coverage"]
    latest = _latest(rows)
    if latest is None:
        return _result(check, None, "no fundamentals")
    ebit = latest.ebit if latest.ebit is not None else latest.operating_income
    interest = latest.interest_expense
    if ebit is None:
        return _result(check, None, "EBIT missing")
    if interest is None:
        if latest.total_debt in (None, 0, 0.0):
            return _result(check, True, "no interest expense (debt-free)")
        return _result(check, None, "interest expense missing")
    if interest <= 0:
        return _result(check, True, "no interest expense", value=0.0, threshold=5.0)
    coverage = float(ebit) / float(interest)
    return _result(
        check,
        coverage >= 5.0,
        f"interest coverage {coverage:.1f}x vs >= 5x",
        value=coverage,
        threshold=5.0,
    )


def _positive_working_capital(rows, _price) -> DeepResult:
    check = CHECKS_BY_ID["graham.deep_positive_working_capital"]
    latest = _latest(rows)
    if (
        latest is None
        or latest.current_assets is None
        or latest.current_liabilities is None
    ):
        return _result(check, None, "working-capital split missing")
    value = float(latest.current_assets) - float(latest.current_liabilities)
    return _result(
        check,
        value > 0,
        f"working capital ${value:,.0f}",
        value=value,
        threshold=0.0,
    )


# ---------------------------------------------------------------------------
# earnings quality
# ---------------------------------------------------------------------------
def _positive_earnings_10y(rows, _price) -> DeepResult:
    check = CHECKS_BY_ID["graham.deep_positive_earnings_10y"]
    values = [r.net_income for r in rows[:10] if r.net_income is not None]
    if len(values) < 5:
        return _result(check, None, f"only {len(values)} years of earnings")
    passed = all(v > 0 for v in values)
    return _result(
        check,
        passed,
        f"{sum(1 for v in values if v > 0)}/{len(values)} profitable years",
        value=float(len(values)),
        threshold=10.0,
    )


def _earnings_stability(rows, _price) -> DeepResult:
    check = CHECKS_BY_ID["graham.deep_earnings_stability"]
    eps = [e for r in rows[:10] if (e := _eps(r)) is not None]
    if len(eps) < 5:
        return _result(check, None, f"only {len(eps)} EPS years")
    rates = [
        eps[index] / eps[index + 1] - 1.0
        for index in range(len(eps) - 1)
        if eps[index + 1] > 0
    ]
    if len(rates) < 4:
        return _result(check, None, "not enough positive EPS history")
    deviation = statistics.pstdev(rates)
    return _result(
        check,
        deviation < 0.15,
        f"EPS growth stdev {deviation:.1%} vs < 15%",
        value=deviation,
        threshold=0.15,
    )


def _net_income_growing_3y(rows, _price) -> DeepResult:
    check = CHECKS_BY_ID["graham.deep_net_income_growing_3y"]
    values = [r.net_income for r in rows[:3]]
    if len(values) < 3 or any(v is None for v in values):
        return _result(check, None, "needs 3 years of net income")
    latest, prev, base = (float(v) for v in values)
    passed = latest > prev > base and latest > 0
    return _result(
        check,
        passed,
        f"net income ${base:,.0f} -> ${prev:,.0f} -> ${latest:,.0f}",
        value=latest / base - 1.0 if base > 0 else None,
    )


def _positive_eps_latest(rows, _price) -> DeepResult:
    check = CHECKS_BY_ID["graham.deep_positive_eps"]
    latest = _latest(rows)
    eps = _eps(latest) if latest is not None else None
    if eps is None:
        return _result(check, None, "latest EPS missing")
    return _result(
        check,
        eps > 0,
        f"latest EPS ${eps:.2f}",
        value=eps,
        threshold=0.0,
    )


# ---------------------------------------------------------------------------
# valuation
# ---------------------------------------------------------------------------
def _graham_number(rows, price) -> DeepResult:
    check = CHECKS_BY_ID["graham.deep_graham_number"]
    if price is None:
        return _result(check, None, "no live price")
    latest = _latest(rows)
    eps = _eps(latest) if latest is not None else None
    bvps = _bvps(latest) if latest is not None else None
    if eps is None or bvps is None or eps <= 0 or bvps <= 0:
        return _result(check, None, "EPS or book value not positive")
    number = math.sqrt(22.5 * eps * bvps)
    return _result(
        check,
        float(price) <= number,
        f"price ${price:.2f} vs Graham Number ${number:.2f}",
        value=number,
        threshold=float(price),
    )


def _pe_below_10(rows, price) -> DeepResult:
    check = CHECKS_BY_ID["graham.deep_pe_below_10"]
    if price is None:
        return _result(check, None, "no live price")
    recent = [r.net_income for r in rows[:3] if r.net_income is not None]
    latest = _latest(rows)
    if len(recent) < 3 or latest is None:
        return _result(check, None, "needs 3 years of earnings")
    shares = _shares(latest)
    avg = sum(float(v) for v in recent) / 3.0
    if shares <= 0 or avg <= 0:
        return _result(check, None, "EPS not positive")
    pe = float(price) / (avg / shares)
    return _result(
        check,
        pe <= 10.0,
        f"P/E {pe:.1f} vs <= 10 (enterprising)",
        value=pe,
        threshold=10.0,
    )


# ---------------------------------------------------------------------------
# growth
# ---------------------------------------------------------------------------
def _revenue_growth_inflation(rows, _price) -> DeepResult:
    check = CHECKS_BY_ID["graham.deep_revenue_growth"]
    values = [
        (r.fiscal_year, r.revenue)
        for r in rows[:10]
        if r.revenue is not None and r.revenue > 0
    ]
    if len(values) < 5:
        return _result(check, None, f"only {len(values)} revenue years")
    newest_year, newest = values[0]
    oldest_year, oldest = values[-1]
    span = int(newest_year) - int(oldest_year)
    if span <= 0:
        return _result(check, None, "no year span")
    cagr = (float(newest) / float(oldest)) ** (1.0 / span) - 1.0
    return _result(
        check,
        cagr >= 0.03,
        f"revenue CAGR {cagr:.1%} vs >= 3%",
        value=cagr,
        threshold=0.03,
    )


# ---------------------------------------------------------------------------
# dividends
# ---------------------------------------------------------------------------
def _payout_ratio(rows, _price) -> DeepResult:
    check = CHECKS_BY_ID["graham.deep_payout_ratio"]
    latest = _latest(rows)
    if latest is None or latest.net_income is None:
        return _result(check, None, "net income missing")
    if latest.dividends_paid in (None, 0, 0.0):
        return _result(check, None, "no dividend paid")
    if latest.net_income <= 0:
        return _result(check, False, "negative earnings with a dividend")
    ratio = float(latest.dividends_paid) / float(latest.net_income)
    return _result(
        check,
        ratio < 0.80,
        f"payout {ratio:.1%} vs < 80%",
        value=ratio,
        threshold=0.80,
    )


def _no_dividend_suspension(rows, _price) -> DeepResult:
    check = CHECKS_BY_ID["graham.deep_no_dividend_suspension"]
    values = [r.dividends_paid for r in rows[:20] if r.dividends_paid is not None]
    if len(values) < 5:
        return _result(check, None, f"only {len(values)} dividend years")
    paid = sum(1 for v in values if v > 0)
    return _result(
        check,
        paid == len(values),
        f"{paid}/{len(values)} years with a dividend",
        value=float(paid),
        threshold=float(len(values)),
    )


# ---------------------------------------------------------------------------
# margin of safety
# ---------------------------------------------------------------------------
def _epv_margin_of_safety(rows, price) -> DeepResult:
    check = CHECKS_BY_ID["graham.deep_epv_margin"]
    if price is None:
        return _result(check, None, "no live price")
    latest = _latest(rows)
    if latest is None:
        return _result(check, None, "no fundamentals")
    ebit = latest.ebit if latest.ebit is not None else latest.operating_income
    shares = _shares(latest)
    if ebit is None or shares <= 0:
        return _result(check, None, "EBIT or shares missing")
    tax = 0.21
    if (
        latest.tax_provision is not None
        and latest.pretax_income is not None
        and latest.pretax_income > 0
    ):
        tax = max(
            0.0, min(0.5, float(latest.tax_provision) / float(latest.pretax_income))
        )
    epv = float(ebit) * (1.0 - tax) / 0.09
    epv_per_share = epv / shares
    target = (2.0 / 3.0) * epv_per_share
    return _result(
        check,
        float(price) <= target,
        f"price ${price:.2f} vs 2/3 EPV ${target:.2f} (9% discount)",
        value=epv_per_share,
        threshold=target,
    )


def _ncav_margin_of_safety(rows, price) -> DeepResult:
    check = CHECKS_BY_ID["graham.deep_ncav_margin"]
    if price is None:
        return _result(check, None, "no live price")
    latest = _latest(rows)
    if (
        latest is None
        or latest.current_assets is None
        or latest.total_liabilities is None
    ):
        return _result(check, None, "balance sheet incomplete for NCAV")
    shares = _shares(latest)
    if shares <= 0:
        return _result(check, None, "no share count")
    ncav = float(latest.current_assets) - float(latest.total_liabilities)
    if ncav <= 0:
        return _result(check, False, "negative NCAV", value=ncav, threshold=0.0)
    ncav_per_share = ncav / shares
    target = float(price) * 1.5
    return _result(
        check,
        ncav_per_share > target,
        f"NCAV/share ${ncav_per_share:.2f} vs > 1.5 x price ${target:.2f}",
        value=ncav_per_share,
        threshold=target,
    )


CHECKS: tuple[GrahamCheck, ...] = (
    GrahamCheck(
        "graham.deep_debt_to_equity",
        "Debt/Equity below 1",
        "financial_strength",
        1,
        "Total debt must not exceed book equity.",
        _public_rule("conservative debt test"),
        _debt_to_equity,
    ),
    GrahamCheck(
        "graham.deep_interest_coverage",
        "Interest coverage >= 5x",
        "financial_strength",
        1,
        "EBIT must cover interest expense at least five times.",
        _public_rule(
            "interest coverage is a conservative extension, not one of the "
            "seven defensive criteria"
        ),
        _interest_coverage,
    ),
    GrahamCheck(
        "graham.deep_positive_working_capital",
        "Positive working capital",
        "financial_strength",
        1,
        "Current assets must exceed current liabilities.",
        _book_rule("Ch. 14, criterion 2"),
        _positive_working_capital,
    ),
    GrahamCheck(
        "graham.deep_positive_earnings_10y",
        "Positive earnings (10y)",
        "earnings_quality",
        2,
        "Every available fiscal year in the last decade must be profitable.",
        _book_rule("Ch. 14, criterion 5 (earnings stability)"),
        _positive_earnings_10y,
    ),
    GrahamCheck(
        "graham.deep_earnings_stability",
        "Stable EPS growth",
        "earnings_quality",
        1,
        "Standard deviation of yearly EPS growth below 15%.",
        _public_rule(
            "the book's earnings-stability criterion is 'no deficit in 10 "
            "years'; the dispersion threshold is an extension"
        ),
        _earnings_stability,
    ),
    GrahamCheck(
        "graham.deep_net_income_growing_3y",
        "Net income growing (3y)",
        "earnings_quality",
        1,
        "Latest net income above the previous two years.",
        _public_rule("short-term growth check"),
        _net_income_growing_3y,
    ),
    GrahamCheck(
        "graham.deep_positive_eps",
        "Positive latest EPS",
        "earnings_quality",
        1,
        "The latest diluted EPS must be positive.",
        _book_rule("Ch. 14, criterion 5"),
        _positive_eps_latest,
    ),
    GrahamCheck(
        "graham.deep_graham_number",
        "Price below Graham Number",
        "valuation",
        2,
        "Price <= sqrt(22.5 x EPS x book value per share).",
        _public_rule("Graham Number derived from the 22.5 rule"),
        _graham_number,
    ),
    GrahamCheck(
        "graham.deep_pe_below_10",
        "P/E <= 10 (enterprising)",
        "valuation",
        0,
        "Informational enterprising-investor P/E bar (not scored).",
        _book_rule("Ch. 15, enterprising investor"),
        _pe_below_10,
    ),
    GrahamCheck(
        "graham.deep_revenue_growth",
        "Revenue CAGR >= 3%",
        "growth",
        1,
        "Revenue must at least keep pace with long-run inflation.",
        _public_rule("inflation proxy"),
        _revenue_growth_inflation,
    ),
    GrahamCheck(
        "graham.deep_payout_ratio",
        "Payout ratio < 80%",
        "dividends",
        1,
        "Dividends must leave room for reinvestment and safety.",
        _public_rule("dividend safety"),
        _payout_ratio,
    ),
    GrahamCheck(
        "graham.deep_no_dividend_suspension",
        "No dividend suspension",
        "dividends",
        1,
        "No zero-dividend year in the available history.",
        _book_rule("Ch. 14, criterion 4"),
        _no_dividend_suspension,
    ),
    GrahamCheck(
        "graham.deep_epv_margin",
        "Price below 2/3 EPV",
        "margin_of_safety",
        1,
        "Price <= 2/3 of Earnings Power Value at a 9% discount.",
        _public_rule("EPV with a fixed 9% discount rate"),
        _epv_margin_of_safety,
    ),
    GrahamCheck(
        "graham.deep_ncav_margin",
        "NCAV above 1.5x price",
        "margin_of_safety",
        1,
        "Net current asset value per share above 1.5x the price.",
        _security_analysis_rule(
            "p. 5 (net-net working capital test)",
            "price < 2/3 of net current asset value; rare in modern markets",
        ),
        _ncav_margin_of_safety,
    ),
)

CHECKS_BY_ID: dict[str, GrahamCheck] = {check.rule_id: check for check in CHECKS}


def run_checks(
    rows: list[NormalizedFinancials], price: float | None
) -> list[DeepResult]:
    """Evaluate every deep check against the newest-first fundamentals."""
    return [check.evaluate(rows, price) for check in CHECKS]
