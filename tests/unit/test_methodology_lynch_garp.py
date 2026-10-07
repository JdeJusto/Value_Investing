"""Tests for the Lynch GARP methodology (backend/methodologies/lynch_garp).

Covers every rule outcome (PASS/WATCH/FAIL/INSUFFICIENT_DATA), the verdict
logic, the score formula, confidence, red flags, determinism, isolation
(no network / no DB / no price persistence) and the book sources.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import Confidence, Verdict
from backend.methodologies.common.company_type import is_financial
from backend.methodologies.lynch_garp.methodology import LynchGARPMethodology

SHARES = 100_000_000
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

R1 = "lynch_garp.rule_1_peg"
R2 = "lynch_garp.rule_2_growth_consistency"
R3 = "lynch_garp.rule_3_debt_conservatism"
R4 = "lynch_garp.rule_4_inventory_vs_sales"
R5 = "lynch_garp.rule_5_dividend_adjusted_peg"


class _Price:
    def __init__(self, price):
        self._price = price

    def get_current_price(self, ticker):
        return self._price


class _CountingPrice:
    def __init__(self, price):
        self._price = price
        self.calls = 0

    def get_current_price(self, ticker):
        self.calls += 1
        return self._price


def _row(year, net_income, revenue=None, shares=SHARES, debt=None, dividends=None):
    return NormalizedFinancials(
        ticker="T",
        fiscal_year=year,
        period="FY",
        revenue=revenue
        if revenue is not None
        else (net_income * 5.0 if net_income else None),
        net_income=net_income,
        shares_outstanding=shares,
        total_debt=debt,
        dividends_paid=dividends,
    )


def _series(ni_values, debt=None, dividends=None, revenue_factor=5.0):
    years = list(range(2015, 2015 + len(ni_values)))
    return [
        _row(
            y,
            ni,
            revenue=(ni * revenue_factor) if ni is not None else None,
            debt=debt,
            dividends=dividends,
        )
        for y, ni in zip(years, ni_values)
    ]


def _backbone(growth=0.25, n=10, debt=400_000_000.0, dividends=20_000_000.0):
    return _series(
        [100_000_000.0 * (1 + growth) ** i for i in range(n)],
        debt=debt,
        dividends=dividends,
    )


def _price_for(rows, pe):
    latest = max(rows, key=lambda r: r.fiscal_year)
    eps = latest.net_income / latest.shares_outstanding
    return pe * eps


def _evaluate(rows, price):
    return LynchGARPMethodology().evaluate("T", rows, _Price(price))


def _outcome(rows, price, rule_id):
    return _evaluate(rows, price).metrics["rule_outcomes"][rule_id]


def _load(name):
    data = json.loads((FIXTURES / f"{name}.json").read_text())
    return [
        NormalizedFinancials(
            ticker=d.get("ticker", "T"),
            fiscal_year=d["fiscal_year"],
            period=d.get("period", "FY"),
            revenue=d.get("revenue"),
            net_income=d.get("net_income"),
            shares_outstanding=d.get("shares_outstanding", SHARES),
            total_debt=d.get("total_debt"),
            dividends_paid=d.get("dividends_paid"),
        )
        for d in data
    ]


def _bank_like(
    rows,
    latest_debt=10_000_000_000.0,
    assets=11_000_000_000.0,
    liabilities=10_000_000_000.0,
):
    """Rebuild rows so the latest year looks like a bank: no inventory,
    leverage > 5x net income, liabilities/assets ~0.91."""
    ordered = sorted(rows, key=lambda r: r.fiscal_year, reverse=True)
    bank = replace(
        ordered[0],
        inventory=None,
        long_term_debt=latest_debt,
        total_assets=assets,
        total_liabilities=liabilities,
    )
    return [bank] + ordered[1:]


# ---------------------------------------------------------------------------
# Financial-company detection (banks/insurers are out of scope for GARP)
# ---------------------------------------------------------------------------
def test_financial_company_detected_bank_like_balance_sheet():
    rows = _bank_like(_backbone())
    assert is_financial(rows[0]) is True


def test_financial_company_evaluate_returns_na_with_reason():
    mgmt = LynchGARPMethodology()
    rows = _bank_like(_backbone())
    res = mgmt.evaluate("T", rows, _Price(None))
    assert res.verdict == Verdict.NOT_APPLICABLE
    assert res.score is None
    assert res.confidence == Confidence.HIGH
    assert res.failed_rules == []
    assert res.metrics["financial_company"] is True
    assert any("financial" in r.lower() for r in res.reasons)


def test_non_financial_company_not_detected():
    rows = _backbone()  # no inventory, but debt/NI ~0.54 and no balance sheet
    assert is_financial(rows[0]) is False


def test_no_inventory_low_debt_not_financial():
    ordered = sorted(_backbone(), key=lambda r: r.fiscal_year, reverse=True)
    rows = [
        replace(ordered[0], inventory=None, long_term_debt=100_000_000.0)
    ] + ordered[1:]
    assert is_financial(rows[0]) is False
    res = LynchGARPMethodology().evaluate("T", rows, _Price(None))
    assert res.verdict not in (Verdict.INSUFFICIENT_DATA, Verdict.NOT_APPLICABLE)


# ---------------------------------------------------------------------------
# Rule 1 — PEG
# ---------------------------------------------------------------------------
def test_rule1_pass():
    rows = _backbone()
    res = _evaluate(rows, _price_for(rows, 20.0))
    assert res.metrics["rule_outcomes"][R1] == "PASS"
    assert res.metrics["rule_1_peg"] == pytest.approx(0.8, rel=1e-6)


def test_rule1_watch():
    rows = _backbone()
    res = _evaluate(rows, _price_for(rows, 30.0))
    assert res.metrics["rule_outcomes"][R1] == "WATCH"
    assert res.metrics["rule_1_peg"] == pytest.approx(1.2, rel=1e-6)


def test_rule1_fail():
    rows = _backbone()
    res = _evaluate(rows, _price_for(rows, 62.5))
    assert res.metrics["rule_outcomes"][R1] == "FAIL"
    assert res.metrics["rule_1_peg"] == pytest.approx(2.5, rel=1e-6)


def test_rule1_insufficient_no_price():
    assert _outcome(_backbone(), None, R1) == "INSUFFICIENT_DATA"


def test_rule1_insufficient_no_growth_series():
    rows = _load("lynch_garp_incomplete")
    assert _outcome(rows, 100.0, R1) == "INSUFFICIENT_DATA"


def test_rule1_negative_growth_fails():
    rows = _series([1000, 900, 800, 700, 600, 550, 500, 480, 460, 440])
    res = _evaluate(rows, _price_for(rows, 15.0))
    assert res.metrics["rule_outcomes"][R1] == "FAIL"


def test_rule1_extreme_pe_fails_as_not_meaningful():
    # P/E 1583 passes through the raw rule as a huge PEG; the guard makes the
    # failure explicit instead of relying on the PEG threshold.
    rows = _backbone()
    outcome = LynchGARPMethodology()._rule_1_peg(rows, _price_for(rows, 1583.74))
    assert outcome.outcome == "FAIL"
    assert "not meaningful" in outcome.detail


def test_rule1_peg_scales_with_growth_rate():
    low = _backbone(growth=0.10)
    res_low = _evaluate(low, _price_for(low, 20.0))
    # P/E 20 with 10% growth -> PEG 2.0
    assert res_low.metrics["rule_1_peg"] == pytest.approx(2.0, rel=1e-4)
    assert res_low.metrics["rule_outcomes"][R1] == "FAIL"

    high = _backbone(growth=0.50)
    res_high = _evaluate(high, _price_for(high, 20.0))
    # P/E 20 with 50% growth -> PEG 0.4
    assert res_high.metrics["rule_1_peg"] == pytest.approx(0.4, rel=1e-4)
    assert res_high.metrics["rule_outcomes"][R1] == "PASS"


# ---------------------------------------------------------------------------
# Rule 2 — earnings growth consistency
# ---------------------------------------------------------------------------
def test_rule2_pass():
    assert _outcome(_backbone(), _price_for(_backbone(), 20.0), R2) == "PASS"


def test_rule2_watch_five_of_nine():
    rows = _series([100, 105, 98, 96, 104, 110, 106, 118, 112, 125])
    assert _outcome(rows, None, R2) == "WATCH"


def test_rule2_fail_four_of_nine():
    rows = _series([100, 102, 95, 90, 92, 80, 84, 75, 78, 70])
    assert _outcome(rows, None, R2) == "FAIL"


def test_rule2_insufficient_under_10_years():
    rows = _series([100, 110, 120])
    assert _outcome(rows, None, R2) == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Rule 3 — debt conservatism
# ---------------------------------------------------------------------------
def test_rule3_pass():
    rows = _backbone(debt=1_400_000_000.0)  # ratio ~1.9
    assert _outcome(rows, None, R3) == "PASS"


def test_rule3_watch():
    rows = _backbone(debt=2_300_000_000.0)  # ratio ~3.1
    assert _outcome(rows, None, R3) == "WATCH"


def test_rule3_fail():
    # A product company (inventory reported) so the financial-company
    # detector does not short-circuit; ratio ~5.4 still fails rule 3.
    rows = _with_inventory(_backbone(debt=4_000_000_000.0), 120.0, 100.0)
    assert _outcome(rows, None, R3) == "FAIL"


def test_rule3_insufficient_negative_net_income():
    rows = _series([100, 200, -50])
    assert _outcome(rows, None, R3) == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Rule 4 — inventory watch
# ---------------------------------------------------------------------------
def _with_inventory(rows, latest_inv, prev_inv):
    ordered = sorted(rows, key=lambda r: r.fiscal_year, reverse=True)
    return [
        replace(
            row,
            inventory=latest_inv if i == 0 else (prev_inv if i == 1 else None),
        )
        for i, row in enumerate(ordered)
    ]


def test_rule4_pass_inventory_in_line():
    rows = _with_inventory(_backbone(), 120.0, 100.0)  # 20% vs sales 25%
    assert _outcome(rows, None, R4) == "PASS"


def test_rule4_watch_inventory_within_50_percent():
    rows = _with_inventory(_backbone(), 130.0, 100.0)  # 30% vs 1.5x25%
    assert _outcome(rows, None, R4) == "WATCH"


def test_rule4_fail_inventory_50_percent_faster():
    rows = _with_inventory(_backbone(), 140.0, 100.0)  # 40% > 37.5%
    assert _outcome(rows, None, R4) == "FAIL"


def test_rule4_watch_no_inventory_service_company():
    assert _outcome(_backbone(), None, R4) == "WATCH"


def test_rule4_insufficient_partial_inventory():
    ordered = sorted(_backbone(), key=lambda r: r.fiscal_year, reverse=True)
    ordered[0] = replace(ordered[0], inventory=120.0)
    assert _outcome(ordered, None, R4) == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Rule 5 — dividend-adjusted PEG
# ---------------------------------------------------------------------------
def test_rule5_pass():
    rows = _backbone()
    res = _evaluate(rows, _price_for(rows, 20.0))
    assert res.metrics["rule_outcomes"][R5] == "PASS"
    assert res.metrics["rule_5_dividend_adjusted_peg"] == pytest.approx(
        0.8 / (1 + 0.2 / 149.01), rel=1e-3
    )


def test_rule5_watch():
    res = _evaluate(_load("lynch_garp_borderline"), 223.515)
    assert res.metrics["rule_outcomes"][R5] == "WATCH"


def test_rule5_fail():
    res = _evaluate(_load("lynch_garp_expensive"), 465.65625)
    assert res.metrics["rule_outcomes"][R5] == "FAIL"


def test_rule5_insufficient_no_dividends():
    rows = _backbone(dividends=None)
    assert _outcome(rows, _price_for(rows, 20.0), R5) == "INSUFFICIENT_DATA"


def test_rule5_only_evaluated_when_dividends_exist():
    no_div = _backbone(dividends=None)
    assert _outcome(no_div, _price_for(no_div, 20.0), R5) == "INSUFFICIENT_DATA"
    with_div = _backbone()
    assert _outcome(with_div, _price_for(with_div, 20.0), R5) == "PASS"


# ---------------------------------------------------------------------------
# Verdict logic
# ---------------------------------------------------------------------------
def test_verdict_buy_all_core_pass():
    res = _evaluate(_load("lynch_garp_ideal"), 149.01)
    assert res.verdict == Verdict.BUY


def test_verdict_watch_two_pass():
    res = _evaluate(_load("lynch_garp_borderline"), 223.515)
    assert res.verdict == Verdict.WATCH


def test_verdict_hold_one_pass():
    # PEG ~1.34 WATCH, 5/9 years up WATCH, debt ratio ~1.54 PASS -> 1 core PASS.
    rows = _series([100, 150, 100, 160, 110, 170, 120, 180, 130, 260], debt=400.0)
    res = _evaluate(rows, _price_for(rows, 15.0))
    assert res.metrics["rule_outcomes"][R1] == "WATCH"
    assert res.metrics["rule_outcomes"][R2] == "WATCH"
    assert res.metrics["rule_outcomes"][R3] == "PASS"
    assert res.verdict == Verdict.HOLD


def test_verdict_avoid_any_fail():
    res = _evaluate(_load("lynch_garp_expensive"), 465.65625)
    assert res.verdict == Verdict.AVOID


def test_verdict_insufficient_more_than_two_core_rules():
    res = _evaluate(_load("lynch_garp_incomplete"), 100.0)
    assert res.verdict == Verdict.INSUFFICIENT_DATA


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------
def test_score_formula():
    # ideal: 4 PASS / 5 evaluable (rule 4 is a WATCH note) -> 80.0
    res = _evaluate(_load("lynch_garp_ideal"), 149.01)
    assert res.score == pytest.approx(80.0)


def test_score_none_when_less_than_two_evaluable():
    res = _evaluate(_load("lynch_garp_incomplete"), 100.0)
    assert res.score is None


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------
def test_confidence_high_all_five_evaluated():
    res = _evaluate(_load("lynch_garp_ideal"), 149.01)
    assert res.confidence == Confidence.HIGH


def test_confidence_medium_one_insufficient():
    rows = _backbone(dividends=None)
    res = _evaluate(rows, _price_for(rows, 20.0))
    assert res.confidence == Confidence.MEDIUM


def test_confidence_low_three_plus_insufficient():
    res = _evaluate(_load("lynch_garp_incomplete"), 100.0)
    assert res.confidence == Confidence.LOW


# ---------------------------------------------------------------------------
# Red flags (verbatim)
# ---------------------------------------------------------------------------
def test_red_flag_peg_above_1_5():
    flags = _evaluate(_load("lynch_garp_expensive"), 465.65625).red_flags
    assert any("PEG above 1.5 (paying too much for growth)" in f for f in flags)


def test_red_flag_earnings_declined_4plus():
    rows = _series([100, 102, 95, 90, 92, 80, 84, 75, 78, 70])
    flags = _evaluate(rows, None).red_flags
    assert any("Earnings declined in 4+ of the last 10 years" in f for f in flags)


def test_red_flag_debt_above_4x():
    rows = _with_inventory(_backbone(debt=4_000_000_000.0), 120.0, 100.0)
    flags = _evaluate(rows, _price_for(rows, 20.0)).red_flags
    assert any("Long-term debt above 4x net income" in f for f in flags)


def test_red_flag_inventory_50_percent_faster():
    rows = _with_inventory(_backbone(), 140.0, 100.0)
    flags = _evaluate(rows, None).red_flags
    assert any("Inventory growing 50% faster than sales" in f for f in flags)


# ---------------------------------------------------------------------------
# Determinism and isolation
# ---------------------------------------------------------------------------
def test_deterministic_same_input_same_output():
    r1 = _evaluate(_load("lynch_garp_ideal"), 149.01)
    r2 = _evaluate(_load("lynch_garp_ideal"), 149.01)
    assert r1.verdict == r2.verdict
    assert r1.score == r2.score
    assert r1.metrics == r2.metrics
    assert r1.red_flags == r2.red_flags


def test_no_network_no_db_no_price_persistence():
    counting = _CountingPrice(_price_for(_backbone(), 20.0))
    res = LynchGARPMethodology().evaluate("T", _backbone(), counting)
    assert counting.calls == 1
    assert res.verdict == Verdict.BUY


# ---------------------------------------------------------------------------
# Registry, rules, sources
# ---------------------------------------------------------------------------
def test_all_rules_count_five():
    from backend.methodologies.lynch_garp.rules import ALL_RULES, VERDICT_RULES

    assert len(ALL_RULES) == 5
    assert len(VERDICT_RULES) == 3
    assert len(LynchGARPMethodology().rules()) == 5


def test_sources_cite_correct_books():
    refs = [r.source for r in LynchGARPMethodology().rules()]
    one_up = [s for s in refs if s.book == "One Up on Wall Street"]
    beating = [s for s in refs if s.book == "Beating the Street"]
    assert len(one_up) == 4
    assert len(beating) == 1
    assert all(s.year == 1989 for s in one_up)
    assert beating[0].year == 1993
    assert refs[4].book == "Beating the Street"


def test_metadata_documents_limitations():
    meta = LynchGARPMethodology().metadata()
    text = " ".join(meta["known_limitations"]).lower()
    assert "financials" in text
    assert "growth-rate" in text
    assert "categoriz" in text


def test_registry_discovers_lynch_garp():
    from backend.methodologies.registry import discover, registry

    discover()
    assert registry.get("lynch_garp") is not None
    assert "lynch_garp" in registry.list()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name,price",
    [
        ("lynch_garp_ideal", 149.01),
        ("lynch_garp_borderline", 223.515),
        ("lynch_garp_expensive", 465.65625),
        ("lynch_garp_incomplete", 100.0),
    ],
)
def test_fixtures_load_and_evaluate(name, price):
    res = _evaluate(_load(name), price)
    assert isinstance(res.verdict, Verdict)
    assert len(res.sources) == 5
    assert len(res.metrics["rule_outcomes"]) == 5


# ---------------------------------------------------------------------------
# Lynch categories (One Up on Wall Street, ch. 6)
# ---------------------------------------------------------------------------
class _CapPrice:
    """Price stub that also exposes a market cap (categorization input)."""

    def __init__(self, price, market_cap):
        self._price = price
        self._market_cap = market_cap

    def get_current_price(self, ticker):
        return self._price

    def get_market_cap(self, ticker):
        return self._market_cap


def _cat_row(
    year,
    net_income,
    revenue,
    shares=SHARES,
    dividends=None,
    sector=None,
    equity=None,
    debt=None,
):
    return NormalizedFinancials(
        ticker="T",
        fiscal_year=year,
        period="FY",
        revenue=revenue,
        net_income=net_income,
        shares_outstanding=shares,
        total_debt=debt,
        dividends_paid=dividends,
        sector=sector,
        stockholders_equity=equity,
    )


def _growth_rows(
    cagr,
    years=10,
    dividends=None,
    sector=None,
    equity=None,
    debt=None,
    margin=0.2,
):
    """Oldest-first rows whose revenue compounds at ``cagr``."""
    rows = []
    for i in range(years):
        year = 2015 + i
        revenue = 1_000_000_000.0 * (1.0 + cagr) ** i
        rows.append(
            _cat_row(
                year,
                net_income=revenue * margin,
                revenue=revenue,
                dividends=dividends,
                sector=sector,
                equity=equity,
                debt=debt,
            )
        )
    return rows


def _category(rows, price=None, market_cap=None):
    res = LynchGARPMethodology().evaluate("T", rows, _CapPrice(price, market_cap))
    return res.metrics["lynch_category"]


def _evaluate_cap(rows, price, market_cap):
    return LynchGARPMethodology().evaluate("T", rows, _CapPrice(price, market_cap))


def test_categorize_fast_grower():
    rows = _growth_rows(0.25)
    assert _category(rows, market_cap=5_000_000_000.0) == "FAST_GROWER"


def test_categorize_stalwart():
    rows = _growth_rows(0.12)
    assert _category(rows, market_cap=50_000_000_000.0) == "STALWART"


def test_categorize_slow_grower():
    rows = _growth_rows(0.03, dividends=20_000_000.0)
    assert _category(rows, market_cap=50_000_000_000.0) == "SLOW_GROWER"


def test_categorize_cyclical_energy_volatility():
    values = [100, 50, 150, 30, 120, 40, 90, 20, 80, 60]
    rows = [
        _cat_row(
            2015 + i,
            net_income=float(v) * 1e6,
            revenue=float(v) * 5e6,
            sector="Energy",
        )
        for i, v in enumerate(values)
    ]
    assert _category(rows, market_cap=20_000_000_000.0) == "CYCLICAL"


@pytest.mark.parametrize(
    "sector",
    [
        "Energy",
        "energy",  # case-insensitive: the old exact match missed this
        "Basic Materials",
        "Materials",  # provider variant
        "Industrials",
        "Industrials - Diversified",
        "Consumer Cyclical",
        "Consumer Discretionary",
        "Oil & Gas",
    ],
)
def test_categorize_cyclical_matches_sector_variants(sector):
    values = [100, 50, 150, 30, 120, 40, 90, 20, 80, 60]
    rows = [
        _cat_row(
            2015 + i,
            net_income=float(v) * 1e6,
            revenue=float(v) * 5e6,
            sector=sector,
        )
        for i, v in enumerate(values)
    ]
    assert _category(rows, market_cap=20_000_000_000.0) == "CYCLICAL"


def test_categorize_volatile_technology_is_not_cyclical():
    values = [100, 50, 150, 30, 120, 40, 90, 20, 80, 60]
    rows = [
        _cat_row(
            2015 + i,
            net_income=float(v) * 1e6,
            revenue=float(v) * 5e6,
            sector="Technology",
        )
        for i, v in enumerate(values)
    ]
    assert _category(rows, market_cap=20_000_000_000.0) != "CYCLICAL"


def test_categorize_volatile_without_sector_is_not_cyclical():
    values = [100, 50, 150, 30, 120, 40, 90, 20, 80, 60]
    rows = [
        _cat_row(
            2015 + i,
            net_income=float(v) * 1e6,
            revenue=float(v) * 5e6,
            sector=None,
        )
        for i, v in enumerate(values)
    ]
    assert _category(rows, market_cap=20_000_000_000.0) != "CYCLICAL"


def test_categorize_turnaround():
    values = [-10, -20, -5, 10, 15]  # oldest -> newest, 3 of 5 negative
    rows = [
        _cat_row(
            2020 + i,
            net_income=float(v) * 1e6,
            revenue=abs(float(v)) * 5e6,
        )
        for i, v in enumerate(values)
    ]
    assert _category(rows) == "TURNAROUND"


def test_categorize_asset_play():
    rows = _growth_rows(0.0, equity=1_000_000_000.0)
    assert _category(rows, market_cap=500_000_000.0) == "ASSET_PLAY"


def test_categorize_unknown():
    rows = _growth_rows(0.0, years=5)
    assert _category(rows, market_cap=1_000_000_000.0) == "UNKNOWN"


# ---------------------------------------------------------------------------
# Verdict logic per category
# ---------------------------------------------------------------------------
def test_slow_grower_stable_dividends_not_avoid():
    rows = _growth_rows(0.03, dividends=20_000_000.0, debt=100_000_000.0)
    res = _evaluate_cap(rows, price=20.0, market_cap=50_000_000_000.0)
    assert res.metrics["lynch_category"] == "SLOW_GROWER"
    assert res.verdict in (Verdict.BUY, Verdict.WATCH)


def test_stalwart_reasonable_peg_buys():
    rows = _growth_rows(0.12, debt=100_000_000.0)
    latest = max(rows, key=lambda r: r.fiscal_year)
    eps = latest.net_income / latest.shares_outstanding
    res = _evaluate_cap(rows, price=12.0 * eps, market_cap=50_000_000_000.0)
    assert res.metrics["lynch_category"] == "STALWART"
    assert res.verdict == Verdict.BUY


def test_fast_grower_thirty_percent_still_buys():
    rows = _growth_rows(0.30, debt=100_000_000.0)
    latest = max(rows, key=lambda r: r.fiscal_year)
    eps = latest.net_income / latest.shares_outstanding
    res = _evaluate_cap(rows, price=30.0 * eps, market_cap=5_000_000_000.0)
    assert res.metrics["lynch_category"] == "FAST_GROWER"
    assert res.verdict == Verdict.BUY


def test_cyclical_adds_cycle_warning():
    values = [100, 50, 150, 30, 120, 40, 90, 20, 80, 60]
    rows = [
        _cat_row(
            2015 + i,
            net_income=float(v) * 1e6,
            revenue=float(v) * 5e6,
            sector="Energy",
        )
        for i, v in enumerate(values)
    ]
    res = _evaluate_cap(rows, price=None, market_cap=20_000_000_000.0)
    assert res.metrics["lynch_category"] == "CYCLICAL"
    assert any("check position in the cycle" in r for r in res.reasons)


# ---------------------------------------------------------------------------
# Rule 1 substitution
# ---------------------------------------------------------------------------
def test_slow_grower_uses_dividend_stability_rule():
    rows = _growth_rows(0.03, dividends=20_000_000.0)
    res = _evaluate_cap(rows, price=20.0, market_cap=50_000_000_000.0)
    assert res.metrics["rule_1_criterion"] == "dividend_stability"
    assert res.metrics["rule_outcomes"][R1] == "PASS"
    assert any("dividend paid in 10 of 10 years" in r for r in res.reasons)


def test_asset_play_uses_price_to_book_rule():
    rows = _growth_rows(0.0, equity=1_000_000_000.0)
    res = _evaluate_cap(rows, price=5.0, market_cap=500_000_000.0)
    assert res.metrics["rule_1_criterion"] == "price_to_book"
    assert res.metrics["rule_outcomes"][R1] == "PASS"
    assert any("P/BV" in r for r in res.reasons)


def test_other_categories_keep_peg_rule():
    rows = _growth_rows(0.12, debt=100_000_000.0)
    res = _evaluate_cap(rows, price=20.0, market_cap=50_000_000_000.0)
    assert res.metrics["lynch_category"] == "STALWART"
    assert res.metrics["rule_1_criterion"] == "peg"


def test_fast_grower_hyper_growth_premium_applies():
    rows = _growth_rows(0.35, debt=100_000_000.0)
    latest = max(rows, key=lambda r: r.fiscal_year)
    eps = latest.net_income / latest.shares_outstanding
    # PEG ~1.09: PASS only because the >30% grower gets the +0.2 premium.
    res = _evaluate_cap(rows, price=38.0 * eps, market_cap=5_000_000_000.0)
    assert res.metrics["lynch_category"] == "FAST_GROWER"
    assert res.metrics["rule_outcomes"][R1] == "PASS"
    assert any("fast-grower premium" in r for r in res.reasons)


def test_turnaround_peg_failure_is_insufficient_not_fail():
    values = [-10, -20, -5, 10, 15]
    rows = [
        _cat_row(2020 + i, net_income=float(v) * 1e6, revenue=abs(float(v)) * 5e6)
        for i, v in enumerate(values)
    ]
    res = _evaluate_cap(rows, price=10.0, market_cap=1_000_000_000.0)
    assert res.metrics["lynch_category"] == "TURNAROUND"
    assert res.metrics["rule_1_criterion"] == "turnaround_peg"


# ---------------------------------------------------------------------------
# Category precedence: Fast Grower over Cyclical for high-CAGR companies
# ---------------------------------------------------------------------------
def test_categorize_fast_grower_large_cap():
    rows = _growth_rows(0.25)
    assert _category(rows, market_cap=50_000_000_000.0) == "FAST_GROWER"


def test_categorize_fast_grower_small_cap_22pct():
    # Lynch's classic criterion: a small aggressive company growing 20-25%.
    # No size gate: a < $10B company at 22% CAGR is a Fast Grower.
    rows = _growth_rows(0.22)
    assert _category(rows, market_cap=5_000_000_000.0) == "FAST_GROWER"


def test_categorize_fast_grower_beats_cyclical_sector():
    # A 30% grower in a cyclical sector is still a Fast Grower: the high CAGR
    # wins over the sector volatility.
    rows = _growth_rows(0.30, sector="Consumer Cyclical")
    assert _category(rows, market_cap=5_000_000_000.0) == "FAST_GROWER"


def test_categorize_cyclical_with_stable_revenue():
    # Flat revenue, volatile earnings: the classic cyclical shape.
    values = [100, 50, 150, 30, 120, 40, 90, 20, 80, 60]
    rows = [
        _cat_row(
            2015 + i,
            net_income=float(v) * 1e6,
            revenue=1_000_000_000.0,
            sector="Energy",
        )
        for i, v in enumerate(values)
    ]
    assert _category(rows, market_cap=20_000_000_000.0) == "CYCLICAL"


def test_categorize_slow_grower_high_cap_low_growth():
    rows = _growth_rows(0.03, dividends=20_000_000.0)
    assert _category(rows, market_cap=200_000_000_000.0) == "SLOW_GROWER"


def test_fast_grower_with_negative_margin_not_fast_grower():
    # 25% revenue CAGR and 4 of 5 profitable years, but the latest year loses
    # money: the positive-margin requirement keeps it out of Fast Grower.
    revenues = [1.0e9 * (1.25**i) for i in range(5)]
    incomes = [r * 0.1 for r in revenues]
    incomes[-1] = -50e6
    rows = [
        _cat_row(2020 + i, net_income=incomes[i], revenue=revenues[i]) for i in range(5)
    ]
    assert _category(rows, market_cap=5_000_000_000.0) != "FAST_GROWER"


# ---------------------------------------------------------------------------
# Score consistency: hidden for categories whose Rule 1 is not the PEG
# ---------------------------------------------------------------------------
def test_slow_grower_score_hidden():
    rows = _growth_rows(0.03, dividends=20_000_000.0, debt=100_000_000.0)
    res = _evaluate_cap(rows, price=20.0, market_cap=50_000_000_000.0)
    assert res.metrics["lynch_category"] == "SLOW_GROWER"
    assert res.score is None
    assert "Slow Grower" in res.metrics["score_note"]
    assert "dividend stability" in res.metrics["score_note"]


def test_asset_play_score_hidden():
    rows = _growth_rows(0.0, equity=1_000_000_000.0)
    res = _evaluate_cap(rows, price=5.0, market_cap=500_000_000.0)
    assert res.metrics["lynch_category"] == "ASSET_PLAY"
    assert res.score is None
    assert "Asset Play" in res.metrics["score_note"]
    assert "price-to-book" in res.metrics["score_note"]


def test_stalwart_score_numeric():
    rows = _growth_rows(0.12, debt=100_000_000.0)
    res = _evaluate_cap(rows, price=20.0, market_cap=50_000_000_000.0)
    assert res.metrics["lynch_category"] == "STALWART"
    assert res.score is not None


def test_fast_grower_score_numeric():
    rows = _growth_rows(0.30, debt=100_000_000.0)
    res = _evaluate_cap(rows, price=20.0, market_cap=5_000_000_000.0)
    assert res.metrics["lynch_category"] == "FAST_GROWER"
    assert res.score is not None


def test_cyclical_score_numeric():
    values = [100, 50, 150, 30, 120, 40, 90, 20, 80, 60]
    rows = [
        _cat_row(
            2015 + i,
            net_income=float(v) * 1e6,
            revenue=float(v) * 5e6,
            sector="Energy",
        )
        for i, v in enumerate(values)
    ]
    res = _evaluate_cap(rows, price=10.0, market_cap=20_000_000_000.0)
    assert res.metrics["lynch_category"] == "CYCLICAL"
    assert res.score is not None


def test_turnaround_score_numeric():
    # Ten years: four good years, then a deep dip and a recovery in progress.
    values = [100, 110, 120, 130, 140, -20, -10, -5, 10, 15]
    rows = [
        _cat_row(
            2015 + i,
            net_income=float(v) * 1e6,
            revenue=abs(float(v)) * 5e6,
            debt=30_000_000.0,
            dividends=5_000_000.0,
        )
        for i, v in enumerate(values)
    ]
    res = _evaluate_cap(rows, price=10.0, market_cap=1_000_000_000.0)
    assert res.metrics["lynch_category"] == "TURNAROUND"
    assert res.score is not None
