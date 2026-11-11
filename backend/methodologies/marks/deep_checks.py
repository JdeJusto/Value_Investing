"""Deep Marks checks — public-knowledge reconstruction.

The four original rules live in :mod:`backend.methodologies.marks.rules`; this
module expands them into a weightable framework in the v0.26/v0.27 style.

**Source caveat.** *The Most Important Thing* (2011) was **not available on
this machine** when the sprint was written (see
``docs/books_notes/the-most-important-thing.md``). Every rule here is therefore
labelled ``page="public knowledge"``: the thresholds are widely published
value/risk heuristics consistent with Marks' public writing, not quotes, page
references or page-level paraphrases. The ``us_caution`` on each
:class:`SourceRef` says so explicitly.

Two rules are explicit approximations:

* **P/E versus its own five-year average** and the **P/E percentile** in the
  cycle block use a constant-price proxy. FDB rows carry a fiscal year but no
  period-end date and the batch pipeline does not fetch point-in-time price
  history, so the comparison isolates the earnings trend rather than the
  historical multiple. The detail string says so.
* **Cycle position** is company-level only. Market-wide cycle temperature,
  the pendulum of psychology, second-level thinking and the credit cycle need
  data this system does not collect (see the deferred list in
  ``docs/marks_rules.md``).

``passed=None`` means the data needed to decide is missing; the shared
weighted aggregation decides whether the coverage is still enough.
"""

from __future__ import annotations

import statistics

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import SourceRef
from backend.methodologies.common.ratio_guards import is_meaningful_pbv
from backend.methodologies.common.weighted import (
    WeightedCheck,
    WeightedResult,
    result,
)

#: Rule categories used by the docs and the CLI groups.
CATEGORIES = ("valuation", "quality", "risk_control", "cycle_position")

_BOOK = "The Most Important Thing: Uncommon Sense for the Thoughtful Investor"
_EDITION = "1st edition"
_YEAR = 2011
_ERA = "2011"
_CAUTION = (
    "public-knowledge reconstruction, not from the book: the reference text "
    "was not available on this machine, so no quote, page number or "
    "page-level paraphrase is claimed; thresholds are public value and "
    "risk-control heuristics in the spirit of Marks' published writing"
)


def _source(note: str | None = None) -> SourceRef:
    caution = _CAUTION if note is None else f"{_CAUTION}; {note}"
    return SourceRef(
        book=_BOOK,
        edition=_EDITION,
        year=_YEAR,
        page="public knowledge",
        era=_ERA,
        us_caution=caution,
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
    if row is None:
        return None
    shares = _shares(row)
    if shares <= 0 or row.net_income is None:
        return None
    return float(row.net_income) / shares


def _operating_margin(row: NormalizedFinancials) -> float | None:
    revenue = row.revenue
    operating = row.operating_income
    if revenue is None or operating is None or revenue == 0:
        return None
    return float(operating) / float(revenue)


def _roic(row: NormalizedFinancials) -> float | None:
    """EBIT / (debt + equity - cash); None when inputs are missing.

    Kept pre-tax so the deep check agrees with the methodology's existing
    ``roic`` metric (two differently computed ROICs in one result would be
    confusing); the rule description names the formula.
    """
    if row is None:
        return None
    ebit = row.ebit if row.ebit is not None else row.operating_income
    if ebit is None or row.stockholders_equity is None:
        return None
    invested = (
        float(row.total_debt or 0.0)
        + float(row.stockholders_equity)
        - float(row.cash_and_equivalents or 0.0)
    )
    if invested <= 0:
        return None
    return float(ebit) / invested


def _fcf(row: NormalizedFinancials) -> float | None:
    if row is None:
        return None
    if row.free_cash_flow is not None:
        return float(row.free_cash_flow)
    if row.operating_cash_flow is not None and row.capital_expenditure is not None:
        return float(row.operating_cash_flow) - abs(float(row.capital_expenditure))
    return None


def _net_debt_to_ebitda(row: NormalizedFinancials) -> float | None:
    ebitda = row.ebitda
    if ebitda is None or ebitda <= 0:
        return None
    if row.total_debt is None:
        return None
    return (float(row.total_debt) - float(row.cash_and_equivalents or 0.0)) / float(
        ebitda
    )


def _interest_coverage(row: NormalizedFinancials) -> tuple[float | None, bool]:
    """(coverage, debt_free) — ``coverage`` is None when it cannot be read."""
    ebit = row.ebit if row.ebit is not None else row.operating_income
    interest = row.interest_expense
    debt_free = row.total_debt in (None, 0, 0.0)
    if ebit is None:
        return None, debt_free
    if interest is None:
        return None, debt_free
    if interest <= 0:
        return 0.0, True
    return float(ebit) / float(interest), False


def _revenue_cagr(rows: list[NormalizedFinancials], years: int = 5) -> float | None:
    with_revenue = [row for row in rows if row.revenue is not None and row.revenue > 0]
    if len(with_revenue) < 2:
        return None
    newest = with_revenue[0]
    window = [
        row for row in with_revenue if newest.fiscal_year - row.fiscal_year <= years
    ]
    oldest = window[-1]
    span = newest.fiscal_year - oldest.fiscal_year
    if span <= 0:
        return None
    return (float(newest.revenue) / float(oldest.revenue)) ** (1.0 / span) - 1.0


def _pe_series(
    rows: list[NormalizedFinancials], price: float | None, years: int
) -> list[float] | None:
    """Constant-price P/E series over the positive-EPS years of the window."""
    if price is None or price <= 0:
        return None
    eps_values = [
        value for row in rows[:years] if (value := _eps(row)) is not None and value > 0
    ]
    if len(eps_values) < 3:
        return None
    return [float(price) / value for value in eps_values]


# ---------------------------------------------------------------------------
# valuation
# ---------------------------------------------------------------------------
def _dcf_margin_of_safety(rows, price, _market_cap, dcf) -> WeightedResult:
    check = CHECKS_BY_ID["marks.deep_price_below_intrinsic_20"]
    if price is None:
        return result(check, None, "no live price")
    margin = getattr(dcf, "margin_of_safety", None) if dcf is not None else None
    if margin is None:
        return result(check, None, "DCF not computable")
    intrinsic = getattr(dcf, "intrinsic_value_per_share", None)
    detail = f"DCF margin {margin:.1%} vs >= 20%"
    if intrinsic is not None:
        detail += f" (intrinsic ${intrinsic:,.2f} vs price ${price:,.2f})"
    return result(
        check,
        margin >= 0.20,
        detail,
        value=margin,
        threshold=0.20,
    )


def _pe_below_own_5y_average(rows, price, _market_cap, _dcf) -> WeightedResult:
    check = CHECKS_BY_ID["marks.deep_pe_below_own_5y_average"]
    series = _pe_series(rows, price, 5)
    if series is None:
        return result(check, None, "needs a live price and 3+ positive EPS years")
    current, history = series[0], series[1:]
    average = statistics.fmean(history)
    return result(
        check,
        current < average,
        (
            f"P/E {current:.1f} vs own 5y average {average:.1f} "
            "(constant-price proxy: no point-in-time price history)"
        ),
        value=current,
        threshold=average,
    )


def _pb_below_2(rows, price, market_cap, _dcf) -> WeightedResult:
    check = CHECKS_BY_ID["marks.deep_pb_below_2"]
    latest = _latest(rows)
    cap = market_cap
    if cap is None and price is not None and latest is not None:
        shares = _shares(latest)
        cap = float(price) * shares if shares > 0 else None
    if cap is None or cap <= 0:
        return result(check, None, "no market cap")
    if latest is None or latest.stockholders_equity is None:
        return result(check, None, "book equity missing")
    if latest.stockholders_equity <= 0:
        return result(check, False, "negative book equity")
    pbv = float(cap) / float(latest.stockholders_equity)
    if not is_meaningful_pbv(pbv):
        return result(
            check,
            False,
            f"P/B {pbv:.2f} is not meaningful (extreme book ratio)",
            value=pbv,
            threshold=2.0,
        )
    return result(
        check,
        pbv < 2.0,
        f"P/B {pbv:.2f} vs < 2",
        value=pbv,
        threshold=2.0,
    )


def _earnings_yield_5(rows, price, _market_cap, _dcf) -> WeightedResult:
    check = CHECKS_BY_ID["marks.deep_earnings_yield_5"]
    if price is None or price <= 0:
        return result(check, None, "no live price")
    latest = _latest(rows)
    shares = _shares(latest) if latest is not None else 0
    earnings = [row.net_income for row in rows[:3] if row.net_income is not None]
    if len(earnings) < 3 or shares <= 0:
        return result(check, None, "needs 3 years of earnings and a share count")
    average = sum(float(value) for value in earnings) / 3.0
    eps = average / shares
    if eps <= 0:
        return result(
            check,
            False,
            "three-year average earnings are not positive",
            value=None,
            threshold=0.05,
        )
    earnings_yield = eps / float(price)
    return result(
        check,
        earnings_yield >= 0.05,
        f"earnings yield {earnings_yield:.1%} vs >= 5%",
        value=earnings_yield,
        threshold=0.05,
    )


# ---------------------------------------------------------------------------
# quality
# ---------------------------------------------------------------------------
def _roic_15(rows, _price, _market_cap, _dcf) -> WeightedResult:
    check = CHECKS_BY_ID["marks.deep_roic_15"]
    latest = _latest(rows)
    value = _roic(latest) if latest is not None else None
    if value is None:
        return result(check, None, "ROIC not computable (EBIT or capital missing)")
    return result(
        check,
        value >= 0.15,
        f"ROIC {value:.1%} vs >= 15%",
        value=value,
        threshold=0.15,
    )


def _fcf_positive_5y(rows, _price, _market_cap, _dcf) -> WeightedResult:
    check = CHECKS_BY_ID["marks.deep_fcf_positive_5y"]
    values = [value for row in rows[:5] if (value := _fcf(row)) is not None]
    if len(values) < 3:
        return result(check, None, f"only {len(values)} years of free cash flow")
    positive = sum(1 for value in values if value > 0)
    return result(
        check,
        positive == len(values),
        f"FCF > 0 in {positive}/{len(values)} years",
        value=float(positive),
        threshold=float(len(values)),
    )


def _margin_stability(rows, _price, _market_cap, _dcf) -> WeightedResult:
    check = CHECKS_BY_ID["marks.deep_margin_stability"]
    margins = [
        value for row in rows[:5] if (value := _operating_margin(row)) is not None
    ]
    if len(margins) < 3:
        return result(check, None, f"only {len(margins)} years of operating margin")
    deviation = statistics.pstdev(margins)
    return result(
        check,
        deviation < 0.05,
        f"operating margin stdev {deviation:.1%} vs < 5pp",
        value=deviation,
        threshold=0.05,
    )


def _revenue_growth_positive(rows, _price, _market_cap, _dcf) -> WeightedResult:
    check = CHECKS_BY_ID["marks.deep_revenue_growth_positive"]
    growth = _revenue_cagr(rows)
    if growth is None:
        return result(check, None, "needs 2+ years of positive revenue")
    return result(
        check,
        growth > 0.0,
        f"revenue CAGR {growth:.1%} vs > 0%",
        value=growth,
        threshold=0.0,
    )


# ---------------------------------------------------------------------------
# risk control
# ---------------------------------------------------------------------------
def _low_debt(rows, _price, _market_cap, _dcf) -> WeightedResult:
    check = CHECKS_BY_ID["marks.deep_low_debt"]
    latest = _latest(rows)
    value = _net_debt_to_ebitda(latest) if latest is not None else None
    if value is None:
        return result(check, None, "net debt/EBITDA not computable")
    return result(
        check,
        value <= 2.5,
        f"net debt/EBITDA {value:.1f}x vs <= 2.5x",
        value=value,
        threshold=2.5,
    )


def _interest_coverage_10(rows, _price, _market_cap, _dcf) -> WeightedResult:
    check = CHECKS_BY_ID["marks.deep_interest_coverage_10"]
    latest = _latest(rows)
    if latest is None:
        return result(check, None, "no fundamentals")
    coverage, debt_free = _interest_coverage(latest)
    if coverage is None:
        if debt_free:
            return result(check, True, "no interest expense (debt-free)")
        return result(check, None, "interest expense missing")
    return result(
        check,
        coverage >= 10.0,
        f"interest coverage {coverage:.1f}x vs >= 10x",
        value=coverage,
        threshold=10.0,
    )


def _no_dilution_5y(rows, _price, _market_cap, _dcf) -> WeightedResult:
    check = CHECKS_BY_ID["marks.deep_no_dilution_5y"]
    shares = [value for row in rows[:6] if (value := _shares(row)) > 0]
    if len(shares) < 3:
        return result(check, None, f"only {len(shares)} years of share counts")
    change = shares[0] / shares[-1] - 1.0
    return result(
        check,
        change <= 0.02,
        f"shares outstanding change {change:+.1%} vs <= +2%",
        value=change,
        threshold=0.02,
    )


# ---------------------------------------------------------------------------
# cycle position (company-level approximation)
# ---------------------------------------------------------------------------
def _pe_percentile_10y(rows, price, _market_cap, _dcf) -> WeightedResult:
    check = CHECKS_BY_ID["marks.deep_pe_percentile_10y"]
    series = _pe_series(rows, price, 10)
    if series is None or len(series) < 5:
        return result(check, None, "needs a live price and 5+ positive EPS years")
    current = series[0]
    percentile = sum(1 for value in series if value <= current) / len(series)
    return result(
        check,
        percentile <= 0.80,
        (
            f"P/E {current:.1f} at the {percentile:.0%} percentile of its own "
            "10y constant-price history vs <= 80%"
        ),
        value=percentile,
        threshold=0.80,
    )


def _not_peak_margin(rows, _price, _market_cap, _dcf) -> WeightedResult:
    check = CHECKS_BY_ID["marks.deep_not_peak_margin"]
    margins = [
        value for row in rows[:10] if (value := _operating_margin(row)) is not None
    ]
    if len(margins) < 3:
        return result(check, None, f"only {len(margins)} years of operating margin")
    current, prior = margins[0], statistics.fmean(margins[1:])
    gap = current - prior
    return result(
        check,
        gap <= 0.03,
        f"operating margin {current:.1%} vs own prior mean {prior:.1%} "
        f"(gap {gap:+.1f}pp; peak = > +3pp)",
        value=gap,
        threshold=0.03,
    )


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
CHECKS: tuple[WeightedCheck, ...] = (
    # valuation ---------------------------------------------------------------
    WeightedCheck(
        "marks.deep_price_below_intrinsic_20",
        "Price >= 20% below intrinsic value",
        "valuation",
        2,
        "DCF intrinsic value at least 20% above the current price.",
        _source("the not-from-canon two-stage DCF is reused as a rule input"),
        _dcf_margin_of_safety,
    ),
    WeightedCheck(
        "marks.deep_pe_below_own_5y_average",
        "P/E below its own 5y average",
        "valuation",
        1,
        "Current P/E below the company's five-year average multiple.",
        _source(
            "constant-price P/E proxy: FDB has no period-end dates and no "
            "point-in-time price history is fetched"
        ),
        _pe_below_own_5y_average,
    ),
    WeightedCheck(
        "marks.deep_pb_below_2",
        "P/B < 2",
        "valuation",
        1,
        "Market cap below twice book equity.",
        _source("asset-backed price sanity check"),
        _pb_below_2,
    ),
    WeightedCheck(
        "marks.deep_earnings_yield_5",
        "Earnings yield >= 5%",
        "valuation",
        1,
        "Three-year average EPS divided by price at least 5%.",
        _source("earnings yield versus the opportunity cost of cash"),
        _earnings_yield_5,
    ),
    # quality -----------------------------------------------------------------
    WeightedCheck(
        "marks.deep_roic_15",
        "ROIC >= 15%",
        "quality",
        2,
        "Return on invested capital for the latest fiscal year "
        "(EBIT / (debt + equity - cash)).",
        _source("durable economics are the quality signal"),
        _roic_15,
    ),
    WeightedCheck(
        "marks.deep_fcf_positive_5y",
        "Positive FCF (5y)",
        "quality",
        2,
        "Free cash flow positive in every available year of the last five.",
        _source("cash generation through the cycle"),
        _fcf_positive_5y,
    ),
    WeightedCheck(
        "marks.deep_margin_stability",
        "Stable operating margin",
        "quality",
        1,
        "Standard deviation of the operating margin below 5 percentage points.",
        _source("margin stability as a business-quality proxy"),
        _margin_stability,
    ),
    WeightedCheck(
        "marks.deep_revenue_growth_positive",
        "Revenue growth positive",
        "quality",
        1,
        "Revenue must grow over the available window.",
        _source("a shrinking top line erodes the margin of safety"),
        _revenue_growth_positive,
    ),
    # risk control ------------------------------------------------------------
    WeightedCheck(
        "marks.deep_low_debt",
        "Net debt/EBITDA <= 2.5x",
        "risk_control",
        1,
        "Leverage low enough to survive the down part of the cycle.",
        _source("prepare, do not predict"),
        _low_debt,
    ),
    WeightedCheck(
        "marks.deep_interest_coverage_10",
        "Interest coverage >= 10x",
        "risk_control",
        1,
        "EBIT must cover interest ten times; debt-free companies pass.",
        _source("survival-first coverage test"),
        _interest_coverage_10,
    ),
    WeightedCheck(
        "marks.deep_no_dilution_5y",
        "No dilution (5y)",
        "risk_control",
        2,
        "Split-adjusted share count flat or lower over five years.",
        _source("shareholders should not fund the risk"),
        _no_dilution_5y,
    ),
    # cycle position ----------------------------------------------------------
    WeightedCheck(
        "marks.deep_pe_percentile_10y",
        "P/E not in the top quintile of its 10y range",
        "cycle_position",
        1,
        "Current P/E at or below the 80th percentile of its own history.",
        _source(
            "company-level approximation; market-wide cycle temperature is "
            "deferred and the P/E history is a constant-price proxy"
        ),
        _pe_percentile_10y,
    ),
    WeightedCheck(
        "marks.deep_not_peak_margin",
        "Operating margin not at a peak",
        "cycle_position",
        1,
        "Current operating margin not more than 3pp above its own prior mean.",
        _source("mean-reversion check on company-level profitability"),
        _not_peak_margin,
    ),
)

CHECKS_BY_ID: dict[str, WeightedCheck] = {check.rule_id: check for check in CHECKS}


def run_checks(
    rows: list[NormalizedFinancials],
    price: float | None = None,
    market_cap: float | None = None,
    dcf: object | None = None,
) -> list[WeightedResult]:
    """Evaluate every deep check against newest-first fundamentals."""
    return [check.evaluate(rows, price, market_cap, dcf) for check in CHECKS]


__all__ = ["CATEGORIES", "CHECKS", "CHECKS_BY_ID", "run_checks"]
