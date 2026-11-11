"""Deep Lynch/GARP checks — public-knowledge reconstruction.

The original five rules live in :mod:`backend.methodologies.lynch_garp.rules`;
this module adds the quantitative rules that make the GARP screen explicit and
weightable, in the v0.26/v0.27 style (Graham and Buffett).

**Source caveat.** *One Up on Wall Street* (1989) and *Beating the Street*
(1993) were **not available on this machine** when the sprint was written (see
``docs/books_notes/one-up-on-wall-street.md``). Every rule here is therefore
labelled ``page="public knowledge"``: the thresholds are the widely published
Lynch heuristics, not quotes, page references or page-level paraphrases. The
``us_caution`` on each :class:`SourceRef` says so explicitly.

Rules are evaluated against newest-first :class:`NormalizedFinancials`. A rule
returns ``passed=None`` when the data needed to decide is missing, so the
weighted aggregation (``backend.methodologies.common.weighted``) can decide
whether the remaining coverage is enough.

Two approximations are worth naming up front:

* **P/E versus its own five-year average.** FDB rows carry a fiscal year but no
  period-end date and no point-in-time price history is fetched (that would add
  a network call per ticker to batch runs). The rule therefore compares the
  current P/E with the P/E the company would have shown at *today's* price
  using each of the last five years' EPS. It isolates the earnings trend, not
  the historical multiple, and is labelled as such in the detail.
* **Category-specific rules** only enter the weighted score for the ticker's
  own Lynch category. The other five return ``None`` and are filtered out of
  the denominator (their ``N/A`` outcome stays visible in the metrics).
"""

from __future__ import annotations

import statistics

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import SourceRef
from backend.methodologies.common.ratio_guards import (
    is_meaningful_pbv,
    is_meaningful_pe,
)
from backend.methodologies.common.weighted import (
    WeightedCheck,
    WeightedResult,
    result,
)

#: Rule categories used by the docs and the CLI groups.
CATEGORIES = (
    "core_garp",
    "financial_health",
    "valuation",
    "category_specific",
)

_BOOK = "One Up on Wall Street / Beating the Street"
_EDITION = "1989 (One Up on Wall Street); 1993 (Beating the Street)"
_YEAR = 1989
_ERA = "1989-1993"
_CAUTION = (
    "public-knowledge reconstruction, not from the book: the reference text "
    "was not available on this machine, so no quote, page number or "
    "page-level paraphrase is claimed; thresholds are the published Lynch "
    "heuristics written for US markets in 1989-1993"
)

#: Lynch category keys (kept as strings so this module never imports the
#: methodology and creates a cycle).
CATEGORY_SLOW_GROWER = "SLOW_GROWER"
CATEGORY_STALWART = "STALWART"
CATEGORY_FAST_GROWER = "FAST_GROWER"
CATEGORY_CYCLICAL = "CYCLICAL"
CATEGORY_TURNAROUND = "TURNAROUND"
CATEGORY_ASSET_PLAY = "ASSET_PLAY"

#: The category-specific rules scored for each category.
CATEGORY_RULES: dict[str, frozenset[str]] = {
    CATEGORY_FAST_GROWER: frozenset({"lynch.deep_fast_grower_profile"}),
    CATEGORY_STALWART: frozenset({"lynch.deep_stalwart_profile"}),
    CATEGORY_SLOW_GROWER: frozenset(
        {"lynch.deep_slow_grower_income", "lynch.deep_slow_grower_dividend"}
    ),
    CATEGORY_CYCLICAL: frozenset({"lynch.deep_cyclical_position"}),
    CATEGORY_TURNAROUND: frozenset({"lynch.deep_turnaround_progress"}),
    CATEGORY_ASSET_PLAY: frozenset({"lynch.deep_asset_play_discount"}),
}
_CATEGORY_RULE_IDS = frozenset().union(*CATEGORY_RULES.values())


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


def _fcf(row: NormalizedFinancials) -> float | None:
    if row.free_cash_flow is not None:
        return float(row.free_cash_flow)
    if row.operating_cash_flow is not None and row.capital_expenditure is not None:
        return float(row.operating_cash_flow) - abs(float(row.capital_expenditure))
    return None


def _market_cap(
    price: float | None,
    latest: NormalizedFinancials | None,
    market_cap: float | None,
) -> float | None:
    if market_cap is not None and market_cap > 0:
        return float(market_cap)
    if price is not None and latest is not None:
        shares = _shares(latest)
        if shares > 0:
            return float(price) * shares
    return None


def _earnings_cagr(rows: list[NormalizedFinancials], years: int = 5) -> float | None:
    """Geometric net-income CAGR over the profitable years of the window."""
    profit = sorted(
        [
            row
            for row in rows[:years]
            if row.net_income is not None and row.net_income > 0
        ],
        key=lambda row: row.fiscal_year,
    )
    if len(profit) < 2:
        return None
    start, end = profit[0], profit[-1]
    span = end.fiscal_year - start.fiscal_year
    if span <= 0 or start.net_income <= 0 or end.net_income <= 0:
        return None
    return (float(end.net_income) / float(start.net_income)) ** (1.0 / span) - 1.0


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


def _pe(
    rows: list[NormalizedFinancials], price: float | None
) -> tuple[float | None, float | None]:
    """(P/E, EPS) for the latest year; both None when not computable."""
    if price is None or price <= 0:
        return None, None
    latest = _latest(rows)
    eps = _eps(latest) if latest is not None else None
    if eps is None or eps <= 0:
        return None, eps
    return float(price) / eps, eps


def _peg(
    rows: list[NormalizedFinancials], price: float | None
) -> tuple[float | None, float | None, float | None]:
    """(PEG, P/E, earnings growth); PEG None when any input is missing."""
    pe, _eps_value = _pe(rows, price)
    growth = _earnings_cagr(rows)
    if pe is None or growth is None or growth <= 0:
        return None, pe, growth
    return pe / (growth * 100.0), pe, growth


def _dividend_yield(
    latest: NormalizedFinancials | None, price: float | None
) -> float | None:
    if latest is None or price is None or price <= 0:
        return None
    dividends = latest.dividends_paid
    shares = _shares(latest)
    if dividends is None or dividends <= 0 or shares <= 0:
        return None
    return (float(dividends) / shares) / float(price)


def _payout(latest: NormalizedFinancials | None) -> float | None:
    if latest is None or latest.dividends_paid in (None, 0, 0.0):
        return None
    if latest.net_income is None or latest.net_income <= 0:
        return None
    return float(latest.dividends_paid) / float(latest.net_income)


def _inventory_vs_revenue(
    rows: list[NormalizedFinancials],
) -> tuple[float | None, float | None]:
    """(inventory growth, revenue growth) for the latest year, or Nones."""
    if len(rows) < 2:
        return None, None
    latest, prev = rows[0], rows[1]
    if (
        latest.inventory in (None, 0)
        or prev.inventory in (None, 0)
        or latest.revenue in (None, 0)
        or prev.revenue in (None, 0)
    ):
        return None, None
    return (
        float(latest.inventory) / float(prev.inventory) - 1.0,
        float(latest.revenue) / float(prev.revenue) - 1.0,
    )


def _dividend_years(rows: list[NormalizedFinancials], years: int) -> int:
    return sum(1 for row in rows[:years] if (row.dividends_paid or 0) > 0)


# ---------------------------------------------------------------------------
# core GARP
# ---------------------------------------------------------------------------
def _peg_below_1(rows, price, _market_cap, _category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_peg_below_1"]
    peg, pe, growth = _peg(rows, price)
    if pe is None:
        return result(check, None, "no live price or positive EPS")
    if not is_meaningful_pe(pe):
        return result(
            check,
            False,
            f"P/E {pe:.1f} is not meaningful (loss or extreme)",
            value=pe,
            threshold=1.0,
        )
    if growth is None:
        return result(check, None, "no earnings-growth series")
    if growth <= 0:
        return result(
            check,
            False,
            f"PEG undefined: earnings growth {growth:+.1%}",
            value=None,
            threshold=1.0,
        )
    return result(
        check,
        peg <= 1.0,
        f"PEG {peg:.2f} (P/E {pe:.1f} / growth {growth:.1%}) vs <= 1.0",
        value=peg,
        threshold=1.0,
    )


def _pe_below_30(rows, price, _market_cap, _category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_pe_below_30"]
    pe, _eps_value = _pe(rows, price)
    if pe is None:
        return result(check, None, "no live price or positive EPS")
    if not is_meaningful_pe(pe):
        return result(
            check,
            False,
            f"P/E {pe:.1f} is not meaningful (loss or extreme)",
            value=pe,
            threshold=30.0,
        )
    return result(
        check,
        pe < 30.0,
        f"P/E {pe:.1f} vs < 30",
        value=pe,
        threshold=30.0,
    )


def _earnings_growth_above_10(rows, _price, _market_cap, _category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_earnings_growth_above_10"]
    growth = _earnings_cagr(rows)
    if growth is None:
        return result(check, None, "needs 2+ profitable years of earnings")
    return result(
        check,
        growth > 0.10,
        f"earnings CAGR {growth:.1%} vs > 10%",
        value=growth,
        threshold=0.10,
    )


def _positive_earnings_5y(rows, _price, _market_cap, _category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_positive_earnings_5y"]
    values = [row.net_income for row in rows[:5] if row.net_income is not None]
    if len(values) < 3:
        return result(check, None, f"only {len(values)} years of earnings")
    positive = sum(1 for value in values if value > 0)
    return result(
        check,
        positive == len(values),
        f"positive earnings in {positive}/{len(values)} years",
        value=float(positive),
        threshold=float(len(values)),
    )


def _revenue_growth_positive_5y(rows, _price, _market_cap, _category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_revenue_growth_positive_5y"]
    values = [
        row.revenue for row in rows[:6] if row.revenue is not None and row.revenue > 0
    ]
    if len(values) < 4:
        return result(check, None, f"only {len(values)} years of revenue")
    changes = [
        values[index] / values[index + 1] - 1.0 for index in range(len(values) - 1)
    ]
    positive = sum(1 for change in changes if change > 0)
    return result(
        check,
        positive == len(changes),
        f"revenue grew in {positive}/{len(changes)} year-over-year periods",
        value=float(positive),
        threshold=float(len(changes)),
    )


# ---------------------------------------------------------------------------
# financial health
# ---------------------------------------------------------------------------
def _debt_to_equity(rows, _price, _market_cap, _category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_debt_equity_below_0_8"]
    latest = _latest(rows)
    if latest is None or latest.total_debt is None:
        return result(check, None, "total debt missing")
    if latest.stockholders_equity is None:
        return result(check, None, "book equity missing")
    if latest.stockholders_equity <= 0:
        return result(check, False, "negative book equity")
    ratio = float(latest.total_debt) / float(latest.stockholders_equity)
    return result(
        check,
        ratio < 0.8,
        f"debt/equity {ratio:.2f} vs < 0.8",
        value=ratio,
        threshold=0.8,
    )


def _current_ratio(rows, _price, _market_cap, _category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_current_ratio_1_5"]
    latest = _latest(rows)
    if (
        latest is None
        or latest.current_assets is None
        or latest.current_liabilities is None
    ):
        return result(check, None, "current assets/liabilities missing")
    if latest.current_liabilities <= 0:
        return result(check, None, "non-positive current liabilities")
    ratio = float(latest.current_assets) / float(latest.current_liabilities)
    return result(
        check,
        ratio > 1.5,
        f"current ratio {ratio:.2f} vs > 1.5",
        value=ratio,
        threshold=1.5,
    )


def _fcf_positive(rows, _price, _market_cap, _category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_fcf_positive"]
    latest = _latest(rows)
    value = _fcf(latest) if latest is not None else None
    if value is None:
        return result(check, None, "operating cash flow / capex missing")
    return result(
        check,
        value > 0,
        f"free cash flow ${value:,.0f}",
        value=value,
        threshold=0.0,
    )


def _inventory_vs_sales(rows, _price, _market_cap, _category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_inventory_vs_revenue"]
    latest = _latest(rows)
    if (
        latest is not None
        and latest.inventory is None
        and len(rows) > 1
        and rows[1].inventory is None
    ):
        return result(
            check,
            True,
            "no inventory reported (asset-light); inventory watch not applicable",
        )
    inv_growth, revenue_growth = _inventory_vs_revenue(rows)
    if inv_growth is None or revenue_growth is None:
        return result(check, None, "inventory or revenue data incomplete")
    return result(
        check,
        inv_growth <= revenue_growth,
        f"inventory growth {inv_growth:.1%} vs revenue growth {revenue_growth:.1%}",
        value=inv_growth,
        threshold=revenue_growth,
    )


def _cash_vs_debt(rows, _price, _market_cap, _category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_cash_vs_debt"]
    latest = _latest(rows)
    if latest is None:
        return result(check, None, "no fundamentals")
    debt = latest.total_debt
    if debt is None:
        debt = latest.long_term_debt
    if debt is None:
        return result(check, None, "debt missing")
    if latest.cash_and_equivalents is None:
        return result(check, None, "cash missing")
    cash = float(latest.cash_and_equivalents)
    if debt <= 0:
        return result(
            check,
            True,
            f"debt-free with ${cash:,.0f} of cash",
            value=cash,
            threshold=0.0,
        )
    ratio = cash / float(debt)
    return result(
        check,
        ratio > 0.5,
        f"cash/debt {ratio:.2f} vs > 0.5",
        value=ratio,
        threshold=0.5,
    )


# ---------------------------------------------------------------------------
# valuation
# ---------------------------------------------------------------------------
def _pb_below_3(rows, price, market_cap, _category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_pb_below_3"]
    latest = _latest(rows)
    cap = _market_cap(price, latest, market_cap)
    if cap is None:
        return result(check, None, "no market cap")
    if latest is None or latest.stockholders_equity is None:
        return result(check, None, "book equity missing")
    if latest.stockholders_equity <= 0:
        return result(check, False, "negative book equity")
    pbv = cap / float(latest.stockholders_equity)
    if not is_meaningful_pbv(pbv):
        return result(
            check,
            False,
            f"P/B {pbv:.2f} is not meaningful (extreme book ratio)",
            value=pbv,
            threshold=3.0,
        )
    return result(
        check,
        pbv < 3.0,
        f"P/B {pbv:.2f} vs < 3",
        value=pbv,
        threshold=3.0,
    )


def _pe_below_own_5y_average(rows, price, _market_cap, _category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_pe_below_own_5y_average"]
    if price is None or price <= 0:
        return result(check, None, "no live price")
    eps_values = [
        value for row in rows[:5] if (value := _eps(row)) is not None and value > 0
    ]
    if len(eps_values) < 3:
        return result(check, None, f"only {len(eps_values)} positive EPS years")
    current = float(price) / eps_values[0]
    history = [float(price) / value for value in eps_values[1:]]
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


def _slow_grower_dividend(rows, _price, _market_cap, category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_slow_grower_dividend"]
    if category != CATEGORY_SLOW_GROWER:
        return result(check, None, "not a slow grower")
    paid = _dividend_years(rows, 5)
    available = min(len(rows), 5)
    if available < 3:
        return result(check, None, "needs 3+ years of dividend history")
    required = min(4, available)
    return result(
        check,
        paid >= required,
        f"dividend paid in {paid}/{available} years (slow grower needs {required})",
        value=float(paid),
        threshold=float(required),
    )


# ---------------------------------------------------------------------------
# category-specific (only scored for the matching Lynch category)
# ---------------------------------------------------------------------------
def _fast_grower_profile(rows, price, _market_cap, category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_fast_grower_profile"]
    if category != CATEGORY_FAST_GROWER:
        return result(check, None, "not a fast grower")
    growth = _revenue_cagr(rows)
    if growth is None:
        return result(check, None, "revenue growth not computable")
    peg, _pe_value, _earnings = _peg(rows, price)
    in_band = 0.20 <= growth <= 0.25
    accepted = peg is not None and peg < 0.5
    peg_text = "n/a" if peg is None else f"{peg:.2f}"
    return result(
        check,
        in_band and accepted,
        (
            f"revenue CAGR {growth:.1%} (classic band 20-25%) and PEG "
            f"{peg_text} vs < 0.5"
        ),
        value=growth,
        threshold=0.25,
    )


def _stalwart_profile(rows, price, _market_cap, category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_stalwart_profile"]
    if category != CATEGORY_STALWART:
        return result(check, None, "not a stalwart")
    growth = _revenue_cagr(rows)
    pe, _eps_value = _pe(rows, price)
    if growth is None:
        return result(check, None, "revenue growth not computable")
    if pe is None or not is_meaningful_pe(pe):
        return result(
            check,
            False,
            "P/E not meaningful for the stalwart test",
            value=growth,
            threshold=15.0,
        )
    return result(
        check,
        0.10 <= growth <= 0.12 and pe < 15.0,
        f"revenue CAGR {growth:.1%} (10-12%) and P/E {pe:.1f} vs < 15",
        value=growth,
        threshold=0.12,
    )


def _slow_grower_income(rows, price, _market_cap, category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_slow_grower_income"]
    if category != CATEGORY_SLOW_GROWER:
        return result(check, None, "not a slow grower")
    latest = _latest(rows)
    dividend_yield = _dividend_yield(latest, price)
    payout = _payout(latest)
    if dividend_yield is None:
        return result(check, None, "no dividend or no live price")
    if payout is None:
        return result(
            check,
            False,
            "dividend paid without positive earnings",
            value=dividend_yield,
            threshold=0.05,
        )
    return result(
        check,
        dividend_yield > 0.05 and payout < 0.80,
        (
            f"dividend yield {dividend_yield:.1%} vs > 5% and payout "
            f"{payout:.0%} vs < 80%"
        ),
        value=dividend_yield,
        threshold=0.05,
    )


def _cyclical_position(rows, price, _market_cap, category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_cyclical_position"]
    if category != CATEGORY_CYCLICAL:
        return result(check, None, "not a cyclical")
    pe, _eps_value = _pe(rows, price)
    if pe is None or not is_meaningful_pe(pe):
        return result(check, None, "P/E not meaningful for a cyclical")
    inv_growth, revenue_growth = _inventory_vs_revenue(rows)
    if inv_growth is None:
        inventory_ok = True
        inventory_detail = "inventory not reported"
    else:
        inventory_ok = inv_growth <= revenue_growth
        inventory_detail = (
            f"inventory growth {inv_growth:.1%} vs revenue {revenue_growth:.1%}"
        )
    return result(
        check,
        inventory_ok and pe <= 15.0,
        f"{inventory_detail}; P/E {pe:.1f} vs <= 15 (low-cycle multiple)",
        value=pe,
        threshold=15.0,
    )


def _turnaround_progress(rows, _price, _market_cap, category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_turnaround_progress"]
    if category != CATEGORY_TURNAROUND:
        return result(check, None, "not a turnaround")
    if len(rows) < 2:
        return result(check, None, "needs two fiscal years")
    latest, prev = rows[0], rows[1]
    debt_latest = latest.total_debt
    debt_prev = prev.total_debt
    if debt_latest is None or debt_prev is None:
        return result(check, None, "debt data missing")
    fcf_latest = _fcf(latest)
    fcf_prev = _fcf(prev)
    if fcf_latest is None:
        return result(check, None, "free cash flow missing")
    debt_down = float(debt_latest) < float(debt_prev)
    fcf_positive = fcf_latest > 0
    detail = (
        f"debt ${float(debt_prev):,.0f} -> ${float(debt_latest):,.0f}; "
        f"FCF ${float(fcf_prev or 0.0):,.0f} -> ${fcf_latest:,.0f}"
    )
    return result(
        check,
        debt_down and fcf_positive,
        f"{detail} (needs debt down and FCF > 0)",
        value=fcf_latest,
        threshold=0.0,
    )


def _asset_play_discount(rows, price, market_cap, category) -> WeightedResult:
    check = CHECKS_BY_ID["lynch.deep_asset_play_discount"]
    if category != CATEGORY_ASSET_PLAY:
        return result(check, None, "not an asset play")
    latest = _latest(rows)
    cap = _market_cap(price, latest, market_cap)
    if cap is None or latest is None:
        return result(check, None, "no market cap")
    if latest.stockholders_equity is None or latest.stockholders_equity <= 0:
        return result(check, None, "book equity missing or negative")
    pbv = cap / float(latest.stockholders_equity)
    tangible = [
        float(value)
        for value in (
            latest.cash_and_equivalents,
            latest.inventory,
            latest.net_ppe,
        )
        if value is not None
    ]
    if not tangible:
        return result(
            check, None, "no tangible-asset lines for the hidden-assets proxy"
        )
    hidden = sum(tangible) / cap
    passed = pbv < 1.0 and hidden >= 0.5
    return result(
        check,
        passed,
        (
            f"P/B {pbv:.2f} vs < 1 and tangible assets / market cap "
            f"{hidden:.0%} vs >= 50% (hidden-assets proxy)"
        ),
        value=pbv,
        threshold=1.0,
    )


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
CHECKS: tuple[WeightedCheck, ...] = (
    # core GARP ---------------------------------------------------------------
    WeightedCheck(
        "lynch.deep_peg_below_1",
        "PEG <= 1",
        "core_garp",
        2,
        "P/E divided by the earnings growth rate must be at or below 1.",
        _source("PEG is the central Lynch heuristic"),
        _peg_below_1,
    ),
    WeightedCheck(
        "lynch.deep_pe_below_30",
        "P/E < 30",
        "core_garp",
        1,
        "Price must be below 30x the latest earnings.",
        _source("growth at a reasonable price, absolute ceiling"),
        _pe_below_30,
    ),
    WeightedCheck(
        "lynch.deep_earnings_growth_above_10",
        "Earnings growth > 10%",
        "core_garp",
        2,
        "Geometric net-income CAGR above 10% over the profitable years.",
        _source("growth is required for a GARP screen"),
        _earnings_growth_above_10,
    ),
    WeightedCheck(
        "lynch.deep_positive_earnings_5y",
        "Positive earnings (5y)",
        "core_garp",
        2,
        "Every available year of the last five must report positive earnings.",
        _source("Lynch avoids loss-makers outside the turnaround bucket"),
        _positive_earnings_5y,
    ),
    WeightedCheck(
        "lynch.deep_revenue_growth_positive_5y",
        "Revenue growth positive (5y)",
        "core_garp",
        1,
        "Revenue must grow in every available year-over-year comparison.",
        _source("the growth story must be visible in the top line"),
        _revenue_growth_positive_5y,
    ),
    # financial health --------------------------------------------------------
    WeightedCheck(
        "lynch.deep_debt_equity_below_0_8",
        "Debt/equity < 0.8",
        "financial_health",
        1,
        "Total debt must stay below 0.8x book equity.",
        _source("conservative balance sheet for a growth company"),
        _debt_to_equity,
    ),
    WeightedCheck(
        "lynch.deep_current_ratio_1_5",
        "Current ratio > 1.5",
        "financial_health",
        1,
        "Current assets at least 1.5x current liabilities.",
        _source("liquidity test"),
        _current_ratio,
    ),
    WeightedCheck(
        "lynch.deep_fcf_positive",
        "Positive free cash flow",
        "financial_health",
        2,
        "Operating cash flow minus capex must be positive.",
        _source("earnings must be backed by cash"),
        _fcf_positive,
    ),
    WeightedCheck(
        "lynch.deep_inventory_vs_revenue",
        "Inventory not outgrowing revenue",
        "financial_health",
        1,
        "Inventory growth must not exceed revenue growth (Lynch's watch).",
        _source("inventory build is Lynch's classic warning sign"),
        _inventory_vs_sales,
    ),
    WeightedCheck(
        "lynch.deep_cash_vs_debt",
        "Cash > 0.5x total debt",
        "financial_health",
        1,
        "Cash and equivalents must cover half of total debt.",
        _source("balance-sheet cushion"),
        _cash_vs_debt,
    ),
    # valuation ---------------------------------------------------------------
    WeightedCheck(
        "lynch.deep_pb_below_3",
        "P/B < 3",
        "valuation",
        1,
        "Market cap below three times book equity.",
        _source("price sanity check outside the asset-play bucket"),
        _pb_below_3,
    ),
    WeightedCheck(
        "lynch.deep_pe_below_own_5y_average",
        "P/E below its own 5y average",
        "valuation",
        1,
        "Current P/E below the five-year average multiple.",
        _source(
            "constant-price P/E proxy: FDB has no period-end dates and no "
            "point-in-time price history is fetched"
        ),
        _pe_below_own_5y_average,
    ),
    WeightedCheck(
        "lynch.deep_slow_grower_dividend",
        "Slow grower pays a dividend",
        "category_specific",
        1,
        (
            "A slow grower must have paid a dividend in at least four of "
            "five years. N/A for other categories."
        ),
        _source("slow growers are held for income; only scored for slow growers"),
        _slow_grower_dividend,
    ),
    # category-specific -------------------------------------------------------
    WeightedCheck(
        "lynch.deep_fast_grower_profile",
        "Fast grower: 20-25% growth and PEG < 0.5",
        "category_specific",
        1,
        "Revenue CAGR in Lynch's 20-25% band with a PEG below 0.5.",
        _source("fast growers must earn their premium"),
        _fast_grower_profile,
    ),
    WeightedCheck(
        "lynch.deep_stalwart_profile",
        "Stalwart: 10-12% growth and P/E < 15",
        "category_specific",
        1,
        "Moderate growth in the 10-12% band at a single-digit-teens multiple.",
        _source("stalwarts are bought at a reasonable price"),
        _stalwart_profile,
    ),
    WeightedCheck(
        "lynch.deep_slow_grower_income",
        "Slow grower: yield > 5% and payout < 80%",
        "category_specific",
        1,
        "High dividend yield with a payout ratio that leaves room to sustain it.",
        _source("slow-grower income test"),
        _slow_grower_income,
    ),
    WeightedCheck(
        "lynch.deep_cyclical_position",
        "Cyclical: no inventory build at a low-cycle P/E",
        "category_specific",
        1,
        "Inventory must not outgrow revenue while the P/E stays at or below 15.",
        _source("cyclicals are timed on inventory and the cycle, not growth"),
        _cyclical_position,
    ),
    WeightedCheck(
        "lynch.deep_turnaround_progress",
        "Turnaround: debt down and FCF positive",
        "category_specific",
        1,
        "Year-over-year debt reduction with free cash flow turning positive.",
        _source("the turnaround must be visible in the balance sheet"),
        _turnaround_progress,
    ),
    WeightedCheck(
        "lynch.deep_asset_play_discount",
        "Asset play: P/B < 1 and tangible-asset cover",
        "category_specific",
        1,
        "Market cap below book value with tangible assets covering half of it.",
        _source("hidden-asset proxy: cash + inventory + net PP&E"),
        _asset_play_discount,
    ),
)

CHECKS_BY_ID: dict[str, WeightedCheck] = {check.rule_id: check for check in CHECKS}


def run_checks(
    rows: list[NormalizedFinancials],
    price: float | None = None,
    market_cap: float | None = None,
    category: str | None = None,
) -> list[WeightedResult]:
    """Evaluate every deep check against newest-first fundamentals."""
    return [check.evaluate(rows, price, market_cap, category) for check in CHECKS]


def scored_results(
    results: list[WeightedResult], category: str | None
) -> list[WeightedResult]:
    """Drop the category-specific rules that do not apply to ``category``.

    Those rules stay in the metrics/reasons as ``N/A`` but never enter the
    weighted denominator: five always-inapplicable weight-1 rules would
    otherwise push a normal company over the 30% missing-weight guard.
    """
    applicable = CATEGORY_RULES.get(category or "", frozenset())
    return [
        item
        for item in results
        if item.rule_id not in _CATEGORY_RULE_IDS or item.rule_id in applicable
    ]


__all__ = [
    "CATEGORIES",
    "CATEGORY_RULES",
    "CHECKS",
    "CHECKS_BY_ID",
    "run_checks",
    "scored_results",
]
