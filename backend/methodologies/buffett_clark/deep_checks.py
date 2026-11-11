"""Deep Buffett/Clark checks — durable advantage, owner earnings, value, growth.

The seven rules in ``methodology.py`` are the book's financial-statement
signatures of a durable competitive advantage (gross margin, interest burden,
debt, cash, capex, retained earnings). This module adds the quantitative checks
the book implies but does not spell out as ratios: returns on capital, the
durability of those returns, owner earnings, book-value compounding, a
not-from-canon DCF margin of safety and long-run growth.

Sources are the book (Mary Buffett & David Clark, *Warren Buffett and the
Interpretation of Financial Statements*, 2001) when a page states the idea.
A criterion that is a public-knowledge derivation (ROIC, owner earnings,
book-value-per-share CAGR, P/E bands, the DCF) carries
``page="public knowledge"`` and a caution naming the approximation. The book
explicitly has no valuation method (notes §9), so every valuation rule is an
approximation rather than a citation.

The checks never touch the network or the database. ``price`` is the live
price, ``dcf`` an optional pre-computed valuation and ``prices`` an optional
price service used only by the historical-P/E rule; each missing input degrades
one rule to ``passed=None`` instead of failing the evaluation.
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

_BOOK = "Warren Buffett and the Interpretation of Financial Statements"
_EDITION = "1st ed. (Spanish translation)"
_YEAR = 2001
_ERA = "2001"

#: Rule categories used by the CLI groups and docs.
CATEGORIES = (
    "durable_advantage",
    "owner_earnings",
    "valuation",
    "growth",
)


def _book(page: str, caution: str | None = None) -> SourceRef:
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
    return _book("public knowledge", f"approximation — {note}")


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


def _roe(row: NormalizedFinancials) -> float | None:
    if row.net_income is None or row.stockholders_equity is None:
        return None
    if row.stockholders_equity <= 0:
        return None
    return float(row.net_income) / float(row.stockholders_equity)


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
        - abs(float(row.capital_expenditure))
    )


def _gross_margin(row: NormalizedFinancials) -> float | None:
    if row.revenue is None or row.revenue <= 0:
        return None
    if row.gross_profit is not None:
        return float(row.gross_profit) / float(row.revenue)
    if row.cogs is not None:
        return 1.0 - float(row.cogs) / float(row.revenue)
    return None


def _cagr(values: list[float], years: int) -> float | None:
    """CAGR over ``years`` from newest-first values with positive endpoints."""
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
# durable advantage
# ---------------------------------------------------------------------------
def _roic_current(rows, _price, _dcf, _prices, _ticker) -> WeightedResult:
    check = CHECKS_BY_ID["buffett_clark.deep_roic_current"]
    latest = _latest(rows)
    roic = _roic(latest) if latest is not None else None
    if roic is None:
        return result(check, None, "ROIC not computable (EBIT or capital missing)")
    return result(
        check,
        roic >= 0.15,
        f"ROIC {roic:.1%} vs >= 15%",
        value=roic,
        threshold=0.15,
    )


def _roic_5y(rows, _price, _dcf, _prices, _ticker) -> WeightedResult:
    check = CHECKS_BY_ID["buffett_clark.deep_roic_5y"]
    values = [value for row in rows[:5] if (value := _roic(row)) is not None]
    if len(values) < 5:
        return result(check, None, f"only {len(values)} years of ROIC (need 5)")
    years_above = sum(1 for value in values if value >= 0.15)
    return result(
        check,
        years_above == len(values),
        f"ROIC >= 15% in {years_above}/{len(values)} years",
        value=float(years_above),
        threshold=float(len(values)),
    )


def _roe_15(rows, _price, _dcf, _prices, _ticker) -> WeightedResult:
    check = CHECKS_BY_ID["buffett_clark.deep_roe_15"]
    latest = _latest(rows)
    roe = _roe(latest) if latest is not None else None
    if roe is None:
        return result(check, None, "ROE not computable (net income or equity missing)")
    return result(
        check,
        roe >= 0.15,
        f"ROE {roe:.1%} vs >= 15%",
        value=roe,
        threshold=0.15,
    )


def _low_capex(rows, _price, _dcf, _prices, _ticker) -> WeightedResult:
    check = CHECKS_BY_ID["buffett_clark.deep_low_capex"]
    latest = _latest(rows)
    if (
        latest is None
        or latest.net_income is None
        or latest.capital_expenditure is None
    ):
        return result(check, None, "net income or capex missing")
    if latest.net_income <= 0:
        return result(check, False, "negative net income makes the ratio meaningless")
    ratio = abs(float(latest.capital_expenditure)) / float(latest.net_income)
    return result(
        check,
        ratio < 0.25,
        f"capex/net income {ratio:.1%} vs < 25%",
        value=ratio,
        threshold=0.25,
    )


def _predictable_earnings(rows, _price, _dcf, _prices, _ticker) -> WeightedResult:
    check = CHECKS_BY_ID["buffett_clark.deep_predictable_earnings"]
    eps = [value for row in rows[:10] if (value := _eps(row)) is not None]
    if len(eps) < 5:
        return result(check, None, f"only {len(eps)} EPS years (need 5)")
    rates = [
        eps[index] / eps[index + 1] - 1.0
        for index in range(len(eps) - 1)
        if eps[index + 1] > 0
    ]
    if len(rates) < 4:
        return result(check, None, "not enough positive EPS history")
    deviation = statistics.pstdev(rates)
    return result(
        check,
        deviation < 0.15,
        f"EPS growth stdev {deviation:.1%} vs < 15% (10y window)",
        value=deviation,
        threshold=0.15,
    )


def _low_debt(rows, _price, _dcf, _prices, _ticker) -> WeightedResult:
    check = CHECKS_BY_ID["buffett_clark.deep_low_debt"]
    latest = _latest(rows)
    if latest is None or latest.stockholders_equity is None:
        return result(check, None, "equity missing")
    if latest.stockholders_equity <= 0:
        return result(check, False, "negative book equity")
    debt = (
        latest.long_term_debt
        if latest.long_term_debt is not None
        else latest.total_debt
    )
    if debt is None:
        return result(check, None, "debt missing")
    ratio = float(debt) / float(latest.stockholders_equity)
    return result(
        check,
        ratio < 0.50,
        f"debt/equity {ratio:.2f} vs < 0.50",
        value=ratio,
        threshold=0.50,
    )


def _gross_margin_stability(rows, _price, _dcf, _prices, _ticker) -> WeightedResult:
    check = CHECKS_BY_ID["buffett_clark.deep_gross_margin_stability"]
    margins = [value for row in rows[:5] if (value := _gross_margin(row)) is not None]
    if len(margins) < 5:
        return result(
            check, None, f"only {len(margins)} years of gross margin (need 5)"
        )
    deviation = statistics.pstdev(margins)
    return result(
        check,
        deviation < 0.03,
        f"gross margin stdev {deviation:.1%} vs < 3pp (5y)",
        value=deviation,
        threshold=0.03,
    )


# ---------------------------------------------------------------------------
# owner earnings
# ---------------------------------------------------------------------------
def _owner_earnings_positive(rows, _price, _dcf, _prices, _ticker) -> WeightedResult:
    check = CHECKS_BY_ID["buffett_clark.deep_owner_earnings_positive"]
    latest = _latest(rows)
    value = _owner_earnings(latest) if latest is not None else None
    if value is None:
        return result(check, None, "net income, D&A or capex missing")
    return result(
        check,
        value > 0,
        f"owner earnings ${value:,.0f} (NI + D&A - capex proxy)",
        value=value,
        threshold=0.0,
    )


def _owner_earnings_growing(rows, _price, _dcf, _prices, _ticker) -> WeightedResult:
    check = CHECKS_BY_ID["buffett_clark.deep_owner_earnings_growing"]
    window = rows[:5]
    values = [value for row in window if (value := _owner_earnings(row)) is not None]
    if len(values) < 5:
        return result(check, None, f"only {len(values)} years of owner earnings")
    span = _year_span(window) or (len(values) - 1)
    growth = _cagr(values, span)
    if growth is None:
        return result(check, None, "owner earnings not positive at both endpoints")
    return result(
        check,
        growth > 0,
        f"owner-earnings CAGR {growth:+.1%} vs > 0% ({span}y)",
        value=growth,
        threshold=0.0,
    )


def _bvps_growth_10y(rows, _price, _dcf, _prices, _ticker) -> WeightedResult:
    check = CHECKS_BY_ID["buffett_clark.deep_bvps_growth_10y"]
    window = rows[:10]
    values = [value for row in window if (value := _bvps(row)) is not None]
    if len(values) < 8:
        return result(check, None, f"only {len(values)} years of book value/share")
    span = _year_span(window) or (len(values) - 1)
    growth = _cagr(values, span)
    if growth is None:
        return result(check, None, "book value per share not positive at both ends")
    return result(
        check,
        growth > 0.10,
        f"book value/share CAGR {growth:+.1%} vs > 10% ({span}y)",
        value=growth,
        threshold=0.10,
    )


# ---------------------------------------------------------------------------
# valuation
# ---------------------------------------------------------------------------
def _dcf_margin_of_safety_50(rows, price, dcf, _prices, _ticker) -> WeightedResult:
    check = CHECKS_BY_ID["buffett_clark.deep_dcf_margin_of_safety_50"]
    if price is None:
        return result(check, None, "no live price")
    margin = getattr(dcf, "margin_of_safety", None) if dcf is not None else None
    if margin is None:
        return result(check, None, "DCF not computable")
    intrinsic = getattr(dcf, "intrinsic_value_per_share", None)
    detail = f"DCF margin {margin:.1%} vs >= 50%"
    if intrinsic is not None:
        detail += f" (intrinsic ${intrinsic:,.2f} vs price ${price:,.2f})"
    return result(
        check,
        margin >= 0.50,
        detail,
        value=margin,
        threshold=0.50,
    )


def _pe_below_20(rows, price, _dcf, _prices, _ticker) -> WeightedResult:
    check = CHECKS_BY_ID["buffett_clark.deep_pe_below_20"]
    if price is None or price <= 0:
        return result(check, None, "no live price")
    earnings = [row.net_income for row in rows[:3] if row.net_income is not None]
    latest = _latest(rows)
    shares = _shares(latest) if latest is not None else 0
    if len(earnings) < 3 or shares <= 0:
        return result(check, None, "needs 3 years of earnings and shares")
    average = sum(float(value) for value in earnings) / 3.0
    eps = average / shares
    if eps <= 0:
        return result(check, None, "EPS not positive")
    pe = float(price) / eps
    return result(
        check,
        pe <= 20.0,
        f"P/E {pe:.1f} vs <= 20 (3y average EPS)",
        value=pe,
        threshold=20.0,
    )


def _pe_below_5y_average(rows, price, _dcf, prices, ticker) -> WeightedResult:
    check = CHECKS_BY_ID["buffett_clark.deep_pe_below_5y_average"]
    if price is None or price <= 0:
        return result(check, None, "no live price")
    if prices is None or ticker is None:
        return result(check, None, "no historical price service")
    getter = getattr(prices, "get_price_at_fiscal_year_end", None)
    if not callable(getter):
        return result(check, None, "price service has no fiscal-year-end prices")

    latest = _latest(rows)
    current_eps = _eps(latest) if latest is not None else None
    if current_eps is None or current_eps <= 0:
        return result(check, None, "latest EPS not positive")

    historical: list[float] = []
    for row in rows[1:6]:
        eps = _eps(row)
        if eps is None or eps <= 0:
            continue
        try:
            past_price = getter(ticker, row.fiscal_year)
        except Exception:  # noqa: BLE001, S112 — a price miss is a data gap
            continue
        if past_price is None or past_price <= 0:
            continue
        historical.append(float(past_price) / eps)
    if len(historical) < 3:
        return result(
            check,
            None,
            f"only {len(historical)} historical P/E points (need 3)",
        )
    average = statistics.fmean(historical)
    current = float(price) / current_eps
    return result(
        check,
        current < average,
        f"P/E {current:.1f} vs own {len(historical)}y average {average:.1f}",
        value=current,
        threshold=average,
    )


# ---------------------------------------------------------------------------
# growth
# ---------------------------------------------------------------------------
def _revenue_cagr_5(rows, _price, _dcf, _prices, _ticker) -> WeightedResult:
    check = CHECKS_BY_ID["buffett_clark.deep_revenue_cagr_5"]
    window = rows[:10]
    values = [
        (row.fiscal_year, float(row.revenue))
        for row in window
        if row.revenue is not None and row.revenue > 0
    ]
    if len(values) < 5:
        return result(check, None, f"only {len(values)} revenue years (need 5)")
    span = int(values[0][0]) - int(values[-1][0])
    if span <= 0:
        return result(check, None, "no year span")
    growth = (values[0][1] / values[-1][1]) ** (1.0 / span) - 1.0
    return result(
        check,
        growth >= 0.05,
        f"revenue CAGR {growth:.1%} vs >= 5% ({span}y)",
        value=growth,
        threshold=0.05,
    )


def _eps_cagr_10(rows, _price, _dcf, _prices, _ticker) -> WeightedResult:
    check = CHECKS_BY_ID["buffett_clark.deep_eps_cagr_10"]
    window = rows[:10]
    values = [value for row in window if (value := _eps(row)) is not None]
    if len(values) < 5:
        return result(check, None, f"only {len(values)} EPS years (need 5)")
    span = _year_span(window) or (len(values) - 1)
    growth = _cagr(values, span)
    if growth is None:
        return result(check, None, "EPS not positive at both endpoints")
    return result(
        check,
        growth >= 0.10,
        f"EPS CAGR {growth:.1%} vs >= 10% ({span}y)",
        value=growth,
        threshold=0.10,
    )


def _positive_earnings_10y(rows, _price, _dcf, _prices, _ticker) -> WeightedResult:
    check = CHECKS_BY_ID["buffett_clark.deep_positive_earnings_10y"]
    values = [row.net_income for row in rows[:10] if row.net_income is not None]
    if len(values) < 5:
        return result(check, None, f"only {len(values)} years of earnings (need 5)")
    positive = sum(1 for value in values if value > 0)
    return result(
        check,
        positive == len(values),
        f"net income > 0 in {positive}/{len(values)} years",
        value=float(positive),
        threshold=float(len(values)),
    )


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
CHECKS: tuple[WeightedCheck, ...] = (
    WeightedCheck(
        "buffett_clark.deep_roic_current",
        "ROIC >= 15%",
        "durable_advantage",
        2,
        "Return on invested capital for the latest fiscal year.",
        _public(
            "ROIC = NOPAT / (debt + equity - cash); the book discusses ROE/ROA, not ROIC"
        ),
        _roic_current,
    ),
    WeightedCheck(
        "buffett_clark.deep_roic_5y",
        "ROIC >= 15% (5y)",
        "durable_advantage",
        2,
        "Every available year of the last five must clear 15% ROIC.",
        _public(
            "5-year ROIC persistence quantifies the book's DCA durability thesis (p. 29, 56)"
        ),
        _roic_5y,
    ),
    WeightedCheck(
        "buffett_clark.deep_roe_15",
        "ROE >= 15%",
        "durable_advantage",
        1,
        "Latest net income at least 15% of book equity.",
        _book(
            "p. 34",
            "page cites the ROE/return-on-assets discussion; the 15% bar is an approximation",
        ),
        _roe_15,
    ),
    WeightedCheck(
        "buffett_clark.deep_low_capex",
        "Capex < 25% of net income",
        "durable_advantage",
        1,
        "Low capital expenditure relative to earnings (no heavy reinvestment).",
        _book(
            "p. 41",
            "the book says capex should be low relative to earnings; 25% is an approximation",
        ),
        _low_capex,
    ),
    WeightedCheck(
        "buffett_clark.deep_predictable_earnings",
        "Predictable earnings",
        "durable_advantage",
        1,
        "Standard deviation of yearly EPS growth below 15% over the last decade.",
        _public("EPS-growth dispersion is an earnings-predictability proxy"),
        _predictable_earnings,
    ),
    WeightedCheck(
        "buffett_clark.deep_low_debt",
        "Debt/equity < 0.50",
        "durable_advantage",
        1,
        "Long-term debt (or total debt when the split is unavailable) below half of equity.",
        _book(
            "p. 38, 41",
            "long-term debt is a DCA indicator; 0.50x is an approximation and total debt proxies long-term debt",
        ),
        _low_debt,
    ),
    WeightedCheck(
        "buffett_clark.deep_gross_margin_stability",
        "Gross margin stdev < 3pp",
        "durable_advantage",
        1,
        "Standard deviation of the gross margin below 3 percentage points over five years.",
        _book(
            "p. 56",
            "stdev < 3pp is a quantification of the book's 'stable or rising' gross margin",
        ),
        _gross_margin_stability,
    ),
    WeightedCheck(
        "buffett_clark.deep_owner_earnings_positive",
        "Positive owner earnings",
        "owner_earnings",
        1,
        "Net income + D&A - capex > 0 (maintenance capex proxy).",
        _public(
            "owner earnings = NI + D&A - capex; total capex stands in for maintenance capex"
        ),
        _owner_earnings_positive,
    ),
    WeightedCheck(
        "buffett_clark.deep_owner_earnings_growing",
        "Owner earnings growing (5y)",
        "owner_earnings",
        1,
        "Owner-earnings CAGR above zero across the last five fiscal years.",
        _public("rising underlying value (p. 29) proxied by owner-earnings growth"),
        _owner_earnings_growing,
    ),
    WeightedCheck(
        "buffett_clark.deep_bvps_growth_10y",
        "Book value/share CAGR > 10% (10y)",
        "owner_earnings",
        1,
        "Split-adjusted book value per share compounding above 10% over ten years.",
        _public(
            "retained-earnings compounding (p. 34) quantified as book value per share"
        ),
        _bvps_growth_10y,
    ),
    WeightedCheck(
        "buffett_clark.deep_dcf_margin_of_safety_50",
        "Price <= 0.5 x DCF intrinsic value",
        "valuation",
        2,
        "Two-stage DCF intrinsic value at least twice the current price.",
        _book(
            "p. 34",
            "the book says buy at a fair price but has no valuation method; the DCF and the 50% margin are not-from-canon approximations",
        ),
        _dcf_margin_of_safety_50,
    ),
    WeightedCheck(
        "buffett_clark.deep_pe_below_20",
        "P/E <= 20",
        "valuation",
        1,
        "Price no more than 20x three-year average earnings.",
        _public("the book has no valuation chapter with a P/E bar (notes §9)"),
        _pe_below_20,
    ),
    WeightedCheck(
        "buffett_clark.deep_pe_below_5y_average",
        "P/E below its own 5y average",
        "valuation",
        1,
        "Current P/E below the mean fiscal-year-end P/E of the prior years.",
        _public("relative-valuation check derived from historical prices"),
        _pe_below_5y_average,
    ),
    WeightedCheck(
        "buffett_clark.deep_revenue_cagr_5",
        "Revenue CAGR >= 5% (10y)",
        "growth",
        1,
        "Revenue compounding at least 5% across the available decade.",
        _book(
            "p. 29, 31",
            "the book's horizon is ten to twenty years; the 5% bar is an approximation",
        ),
        _revenue_cagr_5,
    ),
    WeightedCheck(
        "buffett_clark.deep_eps_cagr_10",
        "EPS CAGR >= 10% (10y)",
        "growth",
        1,
        "Split-adjusted earnings per share compounding at least 10%.",
        _public(
            "per-share compounding proxy; the book warns past growth is not a predictor (p. 111)"
        ),
        _eps_cagr_10,
    ),
    WeightedCheck(
        "buffett_clark.deep_positive_earnings_10y",
        "Positive earnings (10y)",
        "growth",
        1,
        "Every available fiscal year in the last decade must be profitable.",
        _public("earnings-durability proxy; not an explicit book threshold"),
        _positive_earnings_10y,
    ),
)

CHECKS_BY_ID: dict[str, WeightedCheck] = {check.rule_id: check for check in CHECKS}


def run_checks(
    rows: list[NormalizedFinancials],
    price: float | None,
    dcf: object | None = None,
    prices: object | None = None,
    ticker: str | None = None,
) -> list[WeightedResult]:
    """Evaluate every deep check against newest-first fundamentals."""
    return [check.evaluate(rows, price, dcf, prices, ticker) for check in CHECKS]


__all__ = ["CATEGORIES", "CHECKS", "CHECKS_BY_ID", "run_checks"]
