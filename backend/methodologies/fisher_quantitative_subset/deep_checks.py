"""Deep Fisher checks — the quantitative edge of the fifteen points.

``fisher_quantitative_subset`` originally implemented four of Fisher's fifteen
points (3, 5, 10, 13). This module expands the quantitative side with the
growth, profitability, cost and capital-discipline signals the book discusses
without ever reducing to a ratio: revenue growth (point 1), margin trend
(point 6), SG&A control, operating leverage, buybacks and free cash flow.

Fisher's method is qualitative by construction — the eleven scuttlebutt points
remain out of scope. The rules here are therefore *proxies*, and each one says
so in its ``SourceRef.us_caution``. The R&D/sales rule in particular carries
Fisher's own warning that the ratio is a "crude yardstick" (p. 54-55), which is
why it is informational (weight 0) rather than scored.

The checks are deterministic and never touch the network or the database.
"""

from __future__ import annotations

import statistics

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import SourceRef
from backend.methodologies.common.weighted import (
    WeightedCheck,
    WeightedResult,
    result,
)

_BOOK = "Common Stocks and Uncommon Profits"
_EDITION = "Wiley Investment Classics (reprint of 1996 revised ed.)"
_YEAR = 1958
_ERA = "1958"

#: Rule categories used by the CLI groups and docs.
CATEGORIES = (
    "growth_potential",
    "profitability",
    "cost_efficiency",
    "capital_discipline",
)

# Point 3 — R&D intensity relative to size, with a sector-aware bar. Kept here
# (not in methodology.py) so the deep check and the legacy rule share one
# table. R&D intensity is a *sector* property: 2% of revenue is generous for a
# consumer-staples firm but a warning for software. Tiers key on the sector
# label (Yahoo/GICS vocabulary) matched case-insensitively as substrings; an
# unrecognized or missing sector keeps the calibrated large-cap bar
# (PASS 8%, FAIL < 2%).
_RND_THRESHOLDS: tuple[tuple[tuple[str, ...], tuple[float, float]], ...] = (
    # Innovation-led sectors: R&D is the moat, demand ~8% of revenue.
    (("technology", "healthcare", "communication services"), (0.08, 0.04)),
    # Capital-goods sectors: steady, moderate development spending.
    (
        (
            "industrials",
            "consumer cyclical",
            "consumer discretionary",
            "materials",
            "basic materials",
        ),
        (0.04, 0.02),
    ),
    # Low-R&D sectors: a 2% spend already earns PASS; below 0.5% is "no R&D".
    (
        (
            "consumer defensive",
            "consumer staples",
            "staples",
            "utilities",
            "utility",
            "energy",
            "real estate",
            "financial",
        ),
        (0.02, 0.005),
    ),
)
_RND_THRESHOLDS_UNKNOWN: tuple[float, float] = (0.08, 0.02)


def rnd_thresholds_for(sector: str | None) -> tuple[float, float]:
    """(PASS, WATCH) R&D bars for a sector label, first match wins."""
    if sector:
        label = sector.lower()
        for keywords, thresholds in _RND_THRESHOLDS:
            if any(keyword in label for keyword in keywords):
                return thresholds
    return _RND_THRESHOLDS_UNKNOWN


def rnd_not_applicable(sector: str | None) -> bool:
    """True when the sector sits in the low-R&D tier (no R&D line expected)."""
    return bool(sector) and rnd_thresholds_for(sector) == _RND_THRESHOLDS[2][1]


def _pct(ratio: float) -> str:
    """Compact percent text: ``0.08 -> '8%'``, ``0.005 -> '0.5%'``."""
    text = f"{ratio:.1%}"
    return text[:-3] + "%" if text.endswith(".0%") else text


def _source(page: str, caution: str) -> SourceRef:
    return SourceRef(
        book=_BOOK,
        edition=_EDITION,
        year=_YEAR,
        page=page,
        era=_ERA,
        us_caution=caution,
    )


def _public(note: str) -> SourceRef:
    """A public-knowledge derivation, labelled as such (never a fake page)."""
    return _source("public knowledge", f"approximation — {note}")


def _latest(rows: list[NormalizedFinancials]) -> NormalizedFinancials | None:
    return rows[0] if rows else None


def _shares(row: NormalizedFinancials) -> float:
    shares = row.shares_outstanding or 0
    factor = row.split_adjustment_factor or 1.0
    return float(shares) * float(factor)


def _net_margin(row: NormalizedFinancials) -> float | None:
    if row.revenue is None or row.revenue <= 0 or row.net_income is None:
        return None
    return float(row.net_income) / float(row.revenue)


def _gross_margin(row: NormalizedFinancials) -> float | None:
    if row.revenue is None or row.revenue <= 0:
        return None
    if row.gross_profit is not None:
        return float(row.gross_profit) / float(row.revenue)
    if row.cogs is not None:
        return 1.0 - float(row.cogs) / float(row.revenue)
    return None


def _fcf(row: NormalizedFinancials) -> float | None:
    if row.free_cash_flow is not None:
        return float(row.free_cash_flow)
    if row.operating_cash_flow is not None and row.capital_expenditure is not None:
        return float(row.operating_cash_flow) - abs(float(row.capital_expenditure))
    return None


def _roic(row: NormalizedFinancials) -> float | None:
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
    tax = 0.21
    if (
        row.tax_provision is not None
        and row.pretax_income is not None
        and row.pretax_income > 0
    ):
        tax = max(0.0, min(0.5, float(row.tax_provision) / float(row.pretax_income)))
    return float(ebit) * (1.0 - tax) / invested


def _cagr(values: list[float], years: int) -> float | None:
    if len(values) < 2 or years <= 0:
        return None
    newest, oldest = values[0], values[-1]
    if newest <= 0 or oldest <= 0:
        return None
    return (newest / oldest) ** (1.0 / years) - 1.0


def _year_span(rows: list[NormalizedFinancials]) -> int | None:
    if len(rows) < 2 or rows[0].fiscal_year is None or rows[-1].fiscal_year is None:
        return None
    span = int(rows[0].fiscal_year) - int(rows[-1].fiscal_year)
    return span if span > 0 else None


# ---------------------------------------------------------------------------
# growth potential
# ---------------------------------------------------------------------------
def _revenue_growth_15(rows, _price, _sector) -> WeightedResult:
    check = CHECKS_BY_ID["fisher_quantitative_subset.deep_revenue_growth_15"]
    if len(rows) < 2:
        return result(check, None, "needs two years of revenue")
    latest, prior = rows[0].revenue, rows[1].revenue
    if latest is None or prior is None or latest <= 0 or prior <= 0:
        return result(check, None, "revenue missing or non-positive")
    growth = float(latest) / float(prior) - 1.0
    return result(
        check,
        growth > 0.15,
        f"revenue growth {growth:+.1%} YoY vs > 15%",
        value=growth,
        threshold=0.15,
    )


def _revenue_growth_consistent_5y(rows, _price, _sector) -> WeightedResult:
    check = CHECKS_BY_ID["fisher_quantitative_subset.deep_revenue_growth_consistent_5y"]
    window = rows[:6]
    revenues = [
        float(row.revenue)
        for row in window
        if row.revenue is not None and row.revenue > 0
    ]
    if len(revenues) < 5:
        return result(check, None, f"only {len(revenues)} revenue years (need 5)")
    deltas = [
        revenues[index] / revenues[index + 1] - 1.0
        for index in range(len(revenues) - 1)
        if revenues[index + 1] > 0
    ]
    if len(deltas) < 4:
        return result(check, None, "not enough year-over-year revenue changes")
    positive = sum(1 for delta in deltas if delta > 0)
    span = _year_span(window) or (len(revenues) - 1)
    growth = _cagr(revenues, span)
    if growth is None:
        return result(check, None, "revenue CAGR not computable")
    passed = positive >= 4 and growth >= 0.10
    return result(
        check,
        passed,
        (
            f"revenue up in {positive}/{len(deltas)} years and "
            f"CAGR {growth:.1%} vs >= 10%"
        ),
        value=growth,
        threshold=0.10,
    )


def _rnd_intensity(rows, _price, sector) -> WeightedResult:
    check = CHECKS_BY_ID["fisher_quantitative_subset.deep_rnd_intensity"]
    latest = _latest(rows)
    if latest is None or latest.revenue is None or latest.revenue <= 0:
        return result(check, None, "revenue missing")
    label = sector or latest.sector
    if latest.research_development is None:
        if rnd_not_applicable(label):
            return result(check, None, f"R&D is not a line item for {label}")
        return result(check, None, "R&D is not reported")
    ratio = float(latest.research_development) / float(latest.revenue)
    rnd_pass, _rnd_watch = rnd_thresholds_for(label)
    return result(
        check,
        ratio >= rnd_pass,
        (
            f"R&D {ratio:.1%} of revenue vs >= {_pct(rnd_pass)} for "
            f"{label or 'an unknown sector'} (informational)"
        ),
        value=ratio,
        threshold=rnd_pass,
    )


def _rnd_growth_pace(rows, _price, _sector) -> WeightedResult:
    check = CHECKS_BY_ID["fisher_quantitative_subset.deep_rnd_growth_pace"]
    window = rows[:4]
    rnd = [
        (row.fiscal_year, float(row.research_development))
        for row in window
        if row.research_development is not None and row.research_development > 0
    ]
    revenue = [
        (row.fiscal_year, float(row.revenue))
        for row in window
        if row.revenue is not None and row.revenue > 0
    ]
    if len(rnd) < 3 or len(revenue) < 3:
        return result(check, None, "needs 3 years of R&D and revenue")
    span = int(rnd[0][0]) - int(rnd[-1][0])
    if span <= 0:
        return result(check, None, "no year span")
    rnd_growth = (rnd[0][1] / rnd[-1][1]) ** (1.0 / span) - 1.0
    revenue_growth = (revenue[0][1] / revenue[-1][1]) ** (1.0 / span) - 1.0
    return result(
        check,
        rnd_growth >= revenue_growth,
        (
            f"R&D CAGR {rnd_growth:+.1%} vs revenue CAGR "
            f"{revenue_growth:+.1%} (informational)"
        ),
        value=rnd_growth,
        threshold=revenue_growth,
    )


# ---------------------------------------------------------------------------
# profitability
# ---------------------------------------------------------------------------
def _net_margin_15(rows, _price, _sector) -> WeightedResult:
    check = CHECKS_BY_ID["fisher_quantitative_subset.deep_net_margin_15"]
    latest = _latest(rows)
    margin = _net_margin(latest) if latest is not None else None
    if margin is None:
        return result(check, None, "revenue or net income missing")
    return result(
        check,
        margin > 0.15,
        f"net margin {margin:.1%} vs > 15%",
        value=margin,
        threshold=0.15,
    )


def _margin_improvement(rows, _price, _sector) -> WeightedResult:
    check = CHECKS_BY_ID["fisher_quantitative_subset.deep_margin_improvement"]
    margins = [value for row in rows[:5] if (value := _net_margin(row)) is not None]
    if len(margins) < 3:
        return result(check, None, f"only {len(margins)} years of net margin")
    latest, oldest = margins[0], margins[-1]
    change = latest - oldest
    return result(
        check,
        change > 0.005,
        f"net margin {oldest:.1%} -> {latest:.1%} (change {change:+.1%})",
        value=change,
        threshold=0.005,
    )


def _gross_margin_40(rows, _price, _sector) -> WeightedResult:
    check = CHECKS_BY_ID["fisher_quantitative_subset.deep_gross_margin_40"]
    latest = _latest(rows)
    margin = _gross_margin(latest) if latest is not None else None
    if margin is None:
        return result(check, None, "gross margin not reported")
    return result(
        check,
        margin > 0.40,
        f"gross margin {margin:.1%} vs > 40%",
        value=margin,
        threshold=0.40,
    )


# ---------------------------------------------------------------------------
# cost efficiency
# ---------------------------------------------------------------------------
def _sga_ratio_stable(rows, _price, _sector) -> WeightedResult:
    check = CHECKS_BY_ID["fisher_quantitative_subset.deep_sga_ratio_stable"]
    ratios = []
    for row in rows[:5]:
        if row.sga is None or row.revenue is None or row.revenue <= 0:
            continue
        ratios.append(float(row.sga) / float(row.revenue))
    if len(ratios) < 5:
        return result(check, None, f"only {len(ratios)} years of SG&A (need 5)")
    deviation = statistics.pstdev(ratios)
    return result(
        check,
        deviation < 0.02,
        f"SG&A/revenue stdev {deviation:.1%} vs < 2pp (5y)",
        value=deviation,
        threshold=0.02,
    )


def _operating_leverage(rows, _price, _sector) -> WeightedResult:
    check = CHECKS_BY_ID["fisher_quantitative_subset.deep_operating_leverage"]
    window = rows[:5]
    revenue = [
        float(row.revenue)
        for row in window
        if row.revenue is not None and row.revenue > 0
    ]
    operating = [
        float(row.operating_income)
        for row in window
        if row.operating_income is not None and row.operating_income > 0
    ]
    if len(revenue) < 3 or len(operating) < 3:
        return result(check, None, "needs 3 years of revenue and operating income")
    span = _year_span(window) or (min(len(revenue), len(operating)) - 1)
    revenue_growth = _cagr(revenue, span)
    operating_growth = _cagr(operating, span)
    if revenue_growth is None or operating_growth is None:
        return result(check, None, "growth rates not computable")
    return result(
        check,
        operating_growth > revenue_growth,
        (
            f"operating income CAGR {operating_growth:+.1%} vs revenue "
            f"CAGR {revenue_growth:+.1%}"
        ),
        value=operating_growth,
        threshold=revenue_growth,
    )


# ---------------------------------------------------------------------------
# capital discipline
# ---------------------------------------------------------------------------
def _no_dilution_5y(rows, _price, _sector) -> WeightedResult:
    check = CHECKS_BY_ID["fisher_quantitative_subset.deep_no_dilution_5y"]
    window = rows[:6]
    shares = [value for row in window if (value := _shares(row)) > 0]
    if len(shares) < 4:
        return result(check, None, f"only {len(shares)} years of share counts")
    change = shares[0] / shares[-1] - 1.0
    return result(
        check,
        change <= 0.02,
        f"split-adjusted shares change {change:+.1%} vs <= +2% (5y)",
        value=change,
        threshold=0.02,
    )


def _buybacks_3_of_5y(rows, _price, _sector) -> WeightedResult:
    check = CHECKS_BY_ID["fisher_quantitative_subset.deep_buybacks_3_of_5y"]
    window = rows[:6]
    if len(window) < 4:
        return result(check, None, f"only {len(window)} years of share data")
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
    return result(
        check,
        count >= 3,
        f"buybacks in {count}/{len(window) - 1} year-over-year periods",
        value=float(count),
        threshold=3.0,
    )


def _fcf_positive_5y(rows, _price, _sector) -> WeightedResult:
    check = CHECKS_BY_ID["fisher_quantitative_subset.deep_fcf_positive_5y"]
    values = [value for row in rows[:5] if (value := _fcf(row)) is not None]
    if len(values) < 4:
        return result(check, None, f"only {len(values)} years of free cash flow")
    positive = sum(1 for value in values if value > 0)
    return result(
        check,
        positive == len(values),
        f"FCF > 0 in {positive}/{len(values)} years",
        value=float(positive),
        threshold=float(len(values)),
    )


def _roic_15(rows, _price, _sector) -> WeightedResult:
    check = CHECKS_BY_ID["fisher_quantitative_subset.deep_roic_15"]
    latest = _latest(rows)
    roic = _roic(latest) if latest is not None else None
    if roic is None:
        return result(check, None, "ROIC not computable")
    return result(
        check,
        roic > 0.15,
        f"ROIC {roic:.1%} vs > 15%",
        value=roic,
        threshold=0.15,
    )


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
CHECKS: tuple[WeightedCheck, ...] = (
    WeightedCheck(
        "fisher_quantitative_subset.deep_revenue_growth_15",
        "Revenue growth > 15%",
        "growth_potential",
        2,
        "Latest year-over-year revenue growth above 15%.",
        _source(
            "47",
            "point 1 asks for multi-year sales potential, not a 15% annual bar; the threshold is a proxy",
        ),
        _revenue_growth_15,
    ),
    WeightedCheck(
        "fisher_quantitative_subset.deep_revenue_growth_consistent_5y",
        "Consistent revenue growth (5y)",
        "growth_potential",
        1,
        "Revenue up in at least four of the last five years and a 5y CAGR >= 10%.",
        _source(
            "47-48",
            "Fisher judges growth over several years; the 4/5-years and 10% CAGR bars are proxies",
        ),
        _revenue_growth_consistent_5y,
    ),
    WeightedCheck(
        "fisher_quantitative_subset.deep_rnd_intensity",
        "R&D intensity (sector-aware)",
        "growth_potential",
        0,
        "R&D spend as a share of sales, sector-aware; informational because Fisher calls it a crude yardstick.",
        _source(
            "54-55",
            "Fisher warns the R&D/sales ratio is a 'crude yardstick'; informational only (weight 0)",
        ),
        _rnd_intensity,
    ),
    WeightedCheck(
        "fisher_quantitative_subset.deep_net_margin_15",
        "Net margin > 15%",
        "profitability",
        1,
        "Latest net income above 15% of revenue.",
        _source(
            "63-64",
            "point 5 asks for a 'worthwhile' operating margin, not a 15% net bar; the threshold is a proxy",
        ),
        _net_margin_15,
    ),
    WeightedCheck(
        "fisher_quantitative_subset.deep_margin_improvement",
        "Margin trend improving",
        "profitability",
        1,
        "Latest net margin above the oldest margin in the five-year window by more than 0.5pp.",
        _source(
            "63",
            "point 6 looks at the direction of margins; the 0.5pp floor is an approximation",
        ),
        _margin_improvement,
    ),
    WeightedCheck(
        "fisher_quantitative_subset.deep_gross_margin_40",
        "Gross margin > 40%",
        "profitability",
        1,
        "Latest gross margin above 40%.",
        _public(
            "gross-margin level as a quality proxy; Fisher's point 5 is operating margin"
        ),
        _gross_margin_40,
    ),
    WeightedCheck(
        "fisher_quantitative_subset.deep_sga_ratio_stable",
        "SG&A ratio stable",
        "cost_efficiency",
        1,
        "Standard deviation of SG&A/revenue below 2pp over five years.",
        _source(
            "69",
            "point 10 asks about cost-analysis quality; SG&A stability is an accounting proxy",
        ),
        _sga_ratio_stable,
    ),
    WeightedCheck(
        "fisher_quantitative_subset.deep_operating_leverage",
        "Operating leverage",
        "cost_efficiency",
        1,
        "Operating income grows faster than revenue over the available window.",
        _public(
            "operating leverage is a cost-control proxy, not one of Fisher's points"
        ),
        _operating_leverage,
    ),
    WeightedCheck(
        "fisher_quantitative_subset.deep_no_dilution_5y",
        "No dilution (5y)",
        "capital_discipline",
        1,
        "Split-adjusted shares outstanding flat or lower over five years.",
        _source(
            "75",
            "point 13 rejects equity financing that cancels the shareholder's benefit",
        ),
        _no_dilution_5y,
    ),
    WeightedCheck(
        "fisher_quantitative_subset.deep_buybacks_3_of_5y",
        "Buybacks in 3 of 5 years",
        "capital_discipline",
        1,
        "Share count fell or stock was repurchased in at least three periods.",
        _source(
            "75",
            "point 13 is about financing growth without diluting; buybacks are the observable mirror",
        ),
        _buybacks_3_of_5y,
    ),
    WeightedCheck(
        "fisher_quantitative_subset.deep_fcf_positive_5y",
        "Positive FCF (5y)",
        "capital_discipline",
        2,
        "Free cash flow positive in every available year of the last five.",
        _public(
            "growth should be self-funding; point 13 implies it but sets no FCF bar"
        ),
        _fcf_positive_5y,
    ),
    WeightedCheck(
        "fisher_quantitative_subset.deep_roic_15",
        "ROIC > 15%",
        "capital_discipline",
        1,
        "Return on invested capital above 15% in the latest year.",
        _public("ROIC = NOPAT / (debt + equity - cash); a modern quality proxy"),
        _roic_15,
    ),
    WeightedCheck(
        "fisher_quantitative_subset.deep_rnd_growth_pace",
        "R&D keeps pace with revenue",
        "growth_potential",
        0,
        "R&D spending grows at least as fast as revenue (effectiveness proxy).",
        _public(
            "a spend-growth proxy cannot measure research effectiveness; informational"
        ),
        _rnd_growth_pace,
    ),
)

CHECKS_BY_ID: dict[str, WeightedCheck] = {check.rule_id: check for check in CHECKS}


def run_checks(
    rows: list[NormalizedFinancials],
    price: float | None = None,
    sector: str | None = None,
) -> list[WeightedResult]:
    """Evaluate every deep check against newest-first fundamentals."""
    return [check.evaluate(rows, price, sector) for check in CHECKS]


__all__ = [
    "CATEGORIES",
    "CHECKS",
    "CHECKS_BY_ID",
    "rnd_not_applicable",
    "rnd_thresholds_for",
    "run_checks",
]
