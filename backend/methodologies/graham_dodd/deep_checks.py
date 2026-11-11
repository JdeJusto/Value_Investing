"""Deep Graham & Dodd checks from *Security Analysis* (1934).

The original five rules live in ``methodology.py``. This module adds the
quantitative tests the book describes but the first implementation omitted:
the net-net / NCAV bargain test, the balance-sheet ladder, the earnings-power
tests (including EPV) and the asset-value / margin-of-safety filters.

Each check returns ``passed=None`` (N/A) when the underlying data is missing,
so the weighted score can decide whether the remaining coverage is enough.
Graham & Dodd is deliberately strict; thresholds are *not* relaxed to force
positives on a modern large-cap universe.

Sources: page numbers come from ``docs/books_notes/security-analysis.md`` for
the rules the notes document (NWC/net-net p. 5, earnings stability and the
margin of safety p. 101, the bond standards p. 230, balance-sheet strength
p. 38/41). Derived rules (Graham Number, EPV, P/B, extra debt and coverage
ladders) are labelled ``public-knowledge derivation`` rather than attributed
to a page the notes do not support.
"""

from __future__ import annotations

import math
import statistics

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import SourceRef
from backend.methodologies.common.weighted import WeightedCheck, WeightedResult
from backend.methodologies.common.weighted import result as _result

_BOOK = "Security Analysis"
_EDITION = "1st ed. (Spanish translation)"
_YEAR = 1934
_ERA = "1934"

_NWC_CAUTION = (
    "NWC / net-net test calibrated to Depression-era markets; rarely triggers "
    "today for large caps"
)

#: EPV discount rate (public-knowledge convention, shared with the Graham deep
#: checks). The book does not print a rate.
_EPV_DISCOUNT_RATE = 0.09
#: Default tax rate when the row has no usable tax provision.
_DEFAULT_TAX_RATE = 0.21


def _book_rule(page: str, caution: str | None = None) -> SourceRef:
    """A criterion the book notes document at ``page``."""
    return SourceRef(
        book=_BOOK,
        edition=_EDITION,
        year=_YEAR,
        page=page,
        era=_ERA,
        us_caution=caution,
    )


def _derived(note: str) -> SourceRef:
    """A public-knowledge derivation from *Security Analysis* principles."""
    return SourceRef(
        book=_BOOK,
        edition=_EDITION,
        year=_YEAR,
        page="public-knowledge derivation",
        era=_ERA,
        us_caution=f"approximation — {note}",
    )


#: Rule categories used by the CLI groups and docs.
CATEGORIES = (
    "net_net",
    "balance_sheet",
    "earnings_power",
    "asset_value",
    "margin_of_safety",
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


def _bvps(row: NormalizedFinancials) -> float | None:
    shares = _shares(row)
    if shares <= 0 or row.stockholders_equity is None:
        return None
    return float(row.stockholders_equity) / shares


def _ncav(row: NormalizedFinancials) -> float | None:
    """Net current asset value: current assets - *all* liabilities (p. 5)."""
    if row.current_assets is None or row.total_liabilities is None:
        return None
    return float(row.current_assets) - float(row.total_liabilities)


def _working_capital(row: NormalizedFinancials) -> float | None:
    if row.current_assets is None or row.current_liabilities is None:
        return None
    return float(row.current_assets) - float(row.current_liabilities)


def _market_cap(row: NormalizedFinancials, price: float | None) -> float | None:
    if price is None or price <= 0:
        return None
    shares = _shares(row)
    if shares <= 0:
        return None
    return float(price) * shares


def _ebit(row: NormalizedFinancials) -> float | None:
    value = row.ebit if row.ebit is not None else row.operating_income
    return float(value) if value is not None else None


def _tax_rate(row: NormalizedFinancials) -> float:
    if (
        row.tax_provision is not None
        and row.pretax_income is not None
        and row.pretax_income > 0
    ):
        return max(0.0, min(0.5, float(row.tax_provision) / float(row.pretax_income)))
    return _DEFAULT_TAX_RATE


def _cagr(newest: float, oldest: float, span: int) -> float | None:
    if span <= 0 or newest <= 0 or oldest <= 0:
        return None
    return (newest / oldest) ** (1.0 / span) - 1.0


# ---------------------------------------------------------------------------
# net-net / NCAV bargain test (p. 5)
# ---------------------------------------------------------------------------
def _ncav_positive(rows, _price) -> WeightedResult:
    check = CHECKS_BY_ID["graham_dodd.net_net_ncav_positive"]
    latest = _latest(rows)
    ncav = _ncav(latest) if latest is not None else None
    if ncav is None:
        return _result(check, None, "current assets or total liabilities missing")
    return _result(
        check,
        ncav > 0,
        f"NCAV ${ncav:,.0f}",
        value=ncav,
        threshold=0.0,
    )


def _ncav_above_market_cap(rows, price) -> WeightedResult:
    check = CHECKS_BY_ID["graham_dodd.net_net_ncav_above_market_cap"]
    latest = _latest(rows)
    ncav = _ncav(latest) if latest is not None else None
    if latest is None or ncav is None:
        return _result(check, None, "NCAV inputs missing")
    mcap = _market_cap(latest, price)
    if mcap is None:
        return _result(check, None, "no live price or share count")
    if ncav <= 0:
        return _result(
            check, False, f"negative NCAV ${ncav:,.0f}", value=ncav, threshold=mcap
        )
    return _result(
        check,
        ncav > mcap,
        f"NCAV ${ncav:,.0f} vs market cap ${mcap:,.0f}",
        value=ncav,
        threshold=mcap,
    )


def _ncav_1_5x_market_cap(rows, price) -> WeightedResult:
    check = CHECKS_BY_ID["graham_dodd.net_net_ncav_1_5x_market_cap"]
    latest = _latest(rows)
    ncav = _ncav(latest) if latest is not None else None
    if latest is None or ncav is None:
        return _result(check, None, "NCAV inputs missing")
    mcap = _market_cap(latest, price)
    if mcap is None:
        return _result(check, None, "no live price or share count")
    target = 1.5 * mcap
    if ncav <= 0:
        return _result(
            check, False, f"negative NCAV ${ncav:,.0f}", value=ncav, threshold=target
        )
    return _result(
        check,
        ncav >= target,
        f"NCAV ${ncav:,.0f} vs 1.5 x market cap ${target:,.0f}",
        value=ncav,
        threshold=target,
    )


def _price_le_two_thirds_ncav(rows, price) -> WeightedResult:
    check = CHECKS_BY_ID["graham_dodd.net_net_price_le_two_thirds_ncav"]
    latest = _latest(rows)
    if latest is None or price is None:
        return _result(check, None, "no fundamentals or live price")
    ncav = _ncav(latest)
    shares = _shares(latest)
    if ncav is None or shares <= 0:
        return _result(check, None, "NCAV inputs or share count missing")
    if ncav <= 0:
        return _result(check, False, "negative NCAV", value=ncav, threshold=0.0)
    ncav_per_share = ncav / shares
    target = (2.0 / 3.0) * ncav_per_share
    return _result(
        check,
        float(price) <= target,
        f"price ${price:,.2f} vs 2/3 NCAV/share ${target:,.2f}",
        value=float(price),
        threshold=target,
    )


# ---------------------------------------------------------------------------
# balance sheet
# ---------------------------------------------------------------------------
def _current_ratio_2(rows, _price) -> WeightedResult:
    check = CHECKS_BY_ID["graham_dodd.balance_current_ratio_2"]
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
        ratio >= 2.0,
        f"current ratio {ratio:.2f} vs >= 2.0",
        value=ratio,
        threshold=2.0,
    )


def _debt_below_equity(rows, _price) -> WeightedResult:
    check = CHECKS_BY_ID["graham_dodd.balance_debt_below_equity"]
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


def _positive_working_capital(rows, _price) -> WeightedResult:
    check = CHECKS_BY_ID["graham_dodd.balance_positive_working_capital"]
    latest = _latest(rows)
    value = _working_capital(latest) if latest is not None else None
    if value is None:
        return _result(check, None, "current assets/liabilities missing")
    return _result(
        check,
        value > 0,
        f"working capital ${value:,.0f}",
        value=value,
        threshold=0.0,
    )


def _debt_le_half_equity(rows, _price) -> WeightedResult:
    check = CHECKS_BY_ID["graham_dodd.balance_debt_le_half_equity"]
    latest = _latest(rows)
    if (
        latest is None
        or latest.total_debt is None
        or latest.stockholders_equity is None
    ):
        return _result(check, None, "debt or equity missing")
    if latest.stockholders_equity <= 0:
        return _result(check, False, "negative book equity")
    target = 0.5 * float(latest.stockholders_equity)
    return _result(
        check,
        float(latest.total_debt) <= target,
        f"total debt ${latest.total_debt:,.0f} vs 50% equity ${target:,.0f}",
        value=float(latest.total_debt),
        threshold=target,
    )


def _debt_le_working_capital(rows, _price) -> WeightedResult:
    """Total debt must fit inside working capital.

    ``total_debt`` is used as the debt side (>= long-term debt), so the test is
    stricter than the book's long-term-debt formulation; FDB does not expose a
    reliable long-term-debt split for every filer.
    """
    check = CHECKS_BY_ID["graham_dodd.balance_debt_le_working_capital"]
    latest = _latest(rows)
    if latest is None or latest.total_debt is None:
        return _result(check, None, "total debt missing")
    wc = _working_capital(latest)
    if wc is None:
        return _result(check, None, "working-capital split missing")
    return _result(
        check,
        float(latest.total_debt) <= wc,
        f"total debt ${latest.total_debt:,.0f} vs working capital ${wc:,.0f}",
        value=float(latest.total_debt),
        threshold=wc,
    )


# ---------------------------------------------------------------------------
# earnings power
# ---------------------------------------------------------------------------
def _positive_earnings_5y(rows, _price) -> WeightedResult:
    check = CHECKS_BY_ID["graham_dodd.earnings_positive_5y"]
    values = [row.net_income for row in rows[:5] if row.net_income is not None]
    if len(values) < 5:
        return _result(check, None, f"only {len(values)} years of earnings")
    positive = sum(1 for value in values if value > 0)
    return _result(
        check,
        positive == len(values),
        f"positive earnings in {positive}/{len(values)} years",
        value=float(positive),
        threshold=float(len(values)),
    )


def _positive_earnings_10y(rows, _price) -> WeightedResult:
    check = CHECKS_BY_ID["graham_dodd.earnings_positive_10y"]
    values = [row.net_income for row in rows[:10] if row.net_income is not None]
    # Five years is the minimum coverage that still says something about a
    # cycle; below that the decade test is N/A rather than a guess.
    if len(values) < 5:
        return _result(check, None, f"only {len(values)} years of earnings")
    positive = sum(1 for value in values if value > 0)
    return _result(
        check,
        positive == len(values),
        f"positive earnings in {positive}/{len(values)} years",
        value=float(positive),
        threshold=float(len(values)),
    )


def _earnings_stability(rows, _price) -> WeightedResult:
    check = CHECKS_BY_ID["graham_dodd.earnings_stability_20pct"]
    eps = [value for row in rows[:10] if (value := _eps(row)) is not None]
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
        deviation < 0.20,
        f"EPS growth stdev {deviation:.1%} vs < 20%",
        value=deviation,
        threshold=0.20,
    )


def _eps_growth_10y(rows, _price) -> WeightedResult:
    check = CHECKS_BY_ID["graham_dodd.earnings_eps_growth_10y"]
    series = [
        (row.fiscal_year, value)
        for row in rows[:10]
        if (value := _eps(row)) is not None
    ]
    if len(series) < 10:
        return _result(check, None, f"only {len(series)} years of EPS")
    newest_year, newest = series[0]
    oldest_year, oldest = series[-1]
    span = int(newest_year) - int(oldest_year)
    growth = _cagr(newest, oldest, span)
    if growth is None:
        return _result(check, None, "EPS not positive at both ends of the decade")
    return _result(
        check,
        growth >= 0.10,
        f"EPS CAGR {growth:.1%} over {span} years vs >= 10%",
        value=growth,
        threshold=0.10,
    )


def _epv_above_market_cap(rows, price) -> WeightedResult:
    check = CHECKS_BY_ID["graham_dodd.earnings_epv_above_market_cap"]
    latest = _latest(rows)
    if latest is None or price is None:
        return _result(check, None, "no fundamentals or live price")
    ebit = _ebit(latest)
    shares = _shares(latest)
    mcap = _market_cap(latest, price)
    if ebit is None or shares <= 0 or mcap is None:
        return _result(check, None, "EBIT, shares or price missing")
    epv = ebit * (1.0 - _tax_rate(latest)) / _EPV_DISCOUNT_RATE
    return _result(
        check,
        epv > mcap,
        f"EPV ${epv:,.0f} vs market cap ${mcap:,.0f} (9% discount)",
        value=epv,
        threshold=mcap,
    )


# ---------------------------------------------------------------------------
# asset value
# ---------------------------------------------------------------------------
def _pb_below_1(rows, price) -> WeightedResult:
    check = CHECKS_BY_ID["graham_dodd.asset_pb_below_1"]
    latest = _latest(rows)
    if latest is None or price is None:
        return _result(check, None, "no fundamentals or live price")
    bvps = _bvps(latest)
    if bvps is None or bvps <= 0:
        return _result(check, None, "book value per share not positive")
    pb = float(price) / bvps
    return _result(
        check,
        pb < 1.0,
        f"P/B {pb:.2f} vs < 1.0",
        value=pb,
        threshold=1.0,
    )


def _pb_below_067(rows, price) -> WeightedResult:
    check = CHECKS_BY_ID["graham_dodd.asset_pb_below_067"]
    latest = _latest(rows)
    if latest is None or price is None:
        return _result(check, None, "no fundamentals or live price")
    bvps = _bvps(latest)
    if bvps is None or bvps <= 0:
        return _result(check, None, "book value per share not positive")
    pb = float(price) / bvps
    return _result(
        check,
        pb < 2.0 / 3.0,
        f"P/B {pb:.2f} vs < 0.67",
        value=pb,
        threshold=2.0 / 3.0,
    )


def _tangible_book_positive(rows, _price) -> WeightedResult:
    """Net tangible assets > 0, approximated by book equity.

    ``NormalizedFinancials`` has no intangible-assets field, so the intangible
    deduction cannot be applied; the check is reported as an approximation.
    """
    check = CHECKS_BY_ID["graham_dodd.asset_tangible_book_positive"]
    latest = _latest(rows)
    if latest is None or latest.stockholders_equity is None:
        return _result(check, None, "book equity missing")
    equity = float(latest.stockholders_equity)
    return _result(
        check,
        equity > 0,
        f"book equity ${equity:,.0f} (intangibles not reported; approximation)",
        value=equity,
        threshold=0.0,
    )


def _asset_coverage_2x(rows, _price) -> WeightedResult:
    """Bond-style asset coverage: total assets / debt >= 2x.

    ``total_debt`` is used when present, else total liabilities as the debt
    proxy. Informational (weight 0): the book's bond standard, not an equity
    criterion.
    """
    check = CHECKS_BY_ID["graham_dodd.asset_coverage_2x"]
    latest = _latest(rows)
    if latest is None or latest.total_assets is None:
        return _result(check, None, "total assets missing")
    debt = (
        latest.total_debt if latest.total_debt is not None else latest.total_liabilities
    )
    if debt is None:
        return _result(check, None, "debt/liabilities missing")
    if debt <= 0:
        return _result(
            check, True, "no debt (infinite coverage)", value=0.0, threshold=2.0
        )
    coverage = float(latest.total_assets) / float(debt)
    return _result(
        check,
        coverage >= 2.0,
        f"asset coverage {coverage:.2f}x vs >= 2x",
        value=coverage,
        threshold=2.0,
    )


# ---------------------------------------------------------------------------
# margin of safety
# ---------------------------------------------------------------------------
def _price_below_graham_number(rows, price) -> WeightedResult:
    check = CHECKS_BY_ID["graham_dodd.margin_price_below_graham_number"]
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
        f"price ${price:,.2f} vs Graham Number ${number:,.2f}",
        value=float(price),
        threshold=number,
    )


def _price_below_ncav(rows, price) -> WeightedResult:
    check = CHECKS_BY_ID["graham_dodd.margin_price_below_ncav"]
    if price is None:
        return _result(check, None, "no live price")
    latest = _latest(rows)
    if latest is None:
        return _result(check, None, "no fundamentals")
    ncav = _ncav(latest)
    shares = _shares(latest)
    if ncav is None or shares <= 0:
        return _result(check, None, "NCAV inputs or share count missing")
    if ncav <= 0:
        return _result(check, False, "negative NCAV", value=ncav, threshold=0.0)
    ncav_per_share = ncav / shares
    return _result(
        check,
        float(price) < ncav_per_share,
        f"price ${price:,.2f} vs NCAV/share ${ncav_per_share:,.2f}",
        value=float(price),
        threshold=ncav_per_share,
    )


def _dividend_record_10y(rows, _price) -> WeightedResult:
    """Every available year of the last decade paid a dividend.

    The book's 10-year dividend record is a *bond* requirement (p. 230); using
    it for equities is an approximation, noted in the source caution.
    """
    check = CHECKS_BY_ID["graham_dodd.margin_dividend_record_10y"]
    values = [row.dividends_paid for row in rows[:10] if row.dividends_paid is not None]
    if len(values) < 5:
        return _result(check, None, f"only {len(values)} years of dividend data")
    paid = sum(1 for value in values if value > 0)
    return _result(
        check,
        paid == len(values),
        f"{paid}/{len(values)} years with a dividend",
        value=float(paid),
        threshold=float(len(values)),
    )


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
CHECKS: tuple[WeightedCheck, ...] = (
    WeightedCheck(
        "graham_dodd.net_net_ncav_positive",
        "NCAV positive",
        "net_net",
        0,
        "Informational gate: net current asset value must be positive.",
        _book_rule("p. 5", _NWC_CAUTION),
        _ncav_positive,
    ),
    WeightedCheck(
        "graham_dodd.net_net_ncav_above_market_cap",
        "NCAV above market cap",
        "net_net",
        2,
        "Net current asset value (current assets - total liabilities) exceeds "
        "the market capitalisation.",
        _book_rule("p. 5", _NWC_CAUTION),
        _ncav_above_market_cap,
    ),
    WeightedCheck(
        "graham_dodd.net_net_ncav_1_5x_market_cap",
        "NCAV at least 1.5x market cap",
        "net_net",
        2,
        "The classic net-net bargain: NCAV covers the market cap 1.5 times.",
        _book_rule("p. 5", _NWC_CAUTION),
        _ncav_1_5x_market_cap,
    ),
    WeightedCheck(
        "graham_dodd.net_net_price_le_two_thirds_ncav",
        "Price <= 2/3 NCAV per share",
        "net_net",
        2,
        "Price no higher than two thirds of net current asset value per share.",
        _book_rule("p. 5", _NWC_CAUTION),
        _price_le_two_thirds_ncav,
    ),
    WeightedCheck(
        "graham_dodd.balance_current_ratio_2",
        "Current ratio >= 2",
        "balance_sheet",
        2,
        "Current assets at least twice current liabilities.",
        _derived("Graham's defensive current-ratio bar, not printed in the 1934 notes"),
        _current_ratio_2,
    ),
    WeightedCheck(
        "graham_dodd.balance_debt_below_equity",
        "Debt below equity",
        "balance_sheet",
        2,
        "Total debt must not exceed book equity.",
        _derived("conservative leverage test on the 1934 balance-sheet principle"),
        _debt_below_equity,
    ),
    WeightedCheck(
        "graham_dodd.balance_positive_working_capital",
        "Positive working capital",
        "balance_sheet",
        1,
        "Current assets must exceed current liabilities.",
        _book_rule("p. 5", _NWC_CAUTION),
        _positive_working_capital,
    ),
    WeightedCheck(
        "graham_dodd.balance_debt_le_half_equity",
        "Debt <= 50% of equity",
        "balance_sheet",
        1,
        "A stricter leverage bar: total debt at most half of book equity.",
        _derived("conservative extension of the balance-sheet-strength test"),
        _debt_le_half_equity,
    ),
    WeightedCheck(
        "graham_dodd.balance_debt_le_working_capital",
        "Debt <= working capital",
        "balance_sheet",
        1,
        "Total debt (a proxy for long-term debt) must fit inside working capital.",
        _derived(
            "the book uses long-term debt; FDB exposes total debt, so the test "
            "is stricter"
        ),
        _debt_le_working_capital,
    ),
    WeightedCheck(
        "graham_dodd.earnings_positive_5y",
        "Positive earnings (5y)",
        "earnings_power",
        1,
        "Every available year of the last five must be profitable.",
        _book_rule("p. 101", "earnings stability; the 5-year window is a subset"),
        _positive_earnings_5y,
    ),
    WeightedCheck(
        "graham_dodd.earnings_positive_10y",
        "Positive earnings (10y)",
        "earnings_power",
        2,
        "Every available year of the last decade must be profitable.",
        _book_rule("p. 101"),
        _positive_earnings_10y,
    ),
    WeightedCheck(
        "graham_dodd.earnings_stability_20pct",
        "Stable EPS growth",
        "earnings_power",
        1,
        "Standard deviation of yearly EPS growth below 20%.",
        _book_rule(
            "p. 101",
            "the book's criterion is no deficit in 10 years; the dispersion "
            "threshold is an extension",
        ),
        _earnings_stability,
    ),
    WeightedCheck(
        "graham_dodd.earnings_eps_growth_10y",
        "EPS growth >= 10% (10y)",
        "earnings_power",
        1,
        "Ten-year EPS CAGR of at least 10%.",
        _derived("growth floor derived from the book's earnings-power discussion"),
        _eps_growth_10y,
    ),
    WeightedCheck(
        "graham_dodd.earnings_epv_above_market_cap",
        "EPV above market cap",
        "earnings_power",
        1,
        "Earnings power value (EBIT x (1 - tax) / 9%) exceeds the market cap.",
        _derived("EPV with a fixed 9% discount rate"),
        _epv_above_market_cap,
    ),
    WeightedCheck(
        "graham_dodd.asset_pb_below_1",
        "P/B below 1",
        "asset_value",
        2,
        "Price below book value per share.",
        _derived("asset-value test derived from the margin-of-safety principle"),
        _pb_below_1,
    ),
    WeightedCheck(
        "graham_dodd.asset_pb_below_067",
        "P/B below 0.67",
        "asset_value",
        1,
        "Price below two thirds of book value per share.",
        _derived("stricter asset-value bargain test"),
        _pb_below_067,
    ),
    WeightedCheck(
        "graham_dodd.asset_tangible_book_positive",
        "Tangible book value positive",
        "asset_value",
        1,
        "Net tangible assets positive (book equity proxy; intangibles are not "
        "reported by FDB).",
        _derived("FDB has no intangible-assets line, so book equity is used"),
        _tangible_book_positive,
    ),
    WeightedCheck(
        "graham_dodd.asset_coverage_2x",
        "Asset coverage >= 2x",
        "asset_value",
        0,
        "Informational bond standard: total assets cover debt at least twice.",
        _derived("bond-style asset coverage, not an equity criterion"),
        _asset_coverage_2x,
    ),
    WeightedCheck(
        "graham_dodd.margin_price_below_graham_number",
        "Price <= Graham Number",
        "margin_of_safety",
        2,
        "Price <= sqrt(22.5 x EPS x book value per share).",
        _derived("Graham Number derived from the 22.5 rule"),
        _price_below_graham_number,
    ),
    WeightedCheck(
        "graham_dodd.margin_price_below_ncav",
        "Price below NCAV per share",
        "margin_of_safety",
        1,
        "Price below net current asset value per share.",
        _book_rule("p. 5", _NWC_CAUTION),
        _price_below_ncav,
    ),
    WeightedCheck(
        "graham_dodd.margin_dividend_record_10y",
        "Dividend record (10y)",
        "margin_of_safety",
        1,
        "No interrupted dividend in the available decade.",
        _book_rule(
            "p. 230",
            "the 10-year dividend record is a bond requirement in the book; "
            "applying it to equities is an approximation",
        ),
        _dividend_record_10y,
    ),
)

CHECKS_BY_ID: dict[str, WeightedCheck] = {check.rule_id: check for check in CHECKS}


def run_checks(
    rows: list[NormalizedFinancials], price: float | None
) -> list[WeightedResult]:
    """Evaluate every deep check against the newest-first fundamentals."""
    return [check.evaluate(rows, price) for check in CHECKS]


__all__ = [
    "CATEGORIES",
    "CHECKS",
    "CHECKS_BY_ID",
    "run_checks",
]
