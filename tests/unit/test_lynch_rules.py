"""Focused tests for the Lynch deep checks and the weighted aggregation.

One pass/fail fixture per deep rule, plus the weighted threshold and the
category-specific N/A filtering.
"""

from __future__ import annotations

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.common.weighted import (
    WeightedResult,
    weighted_verdict,
)
from backend.methodologies.lynch_garp.deep_checks import run_checks, scored_results


def _row(year: int, **overrides):
    data = {
        "ticker": "TEST",
        "fiscal_year": year,
        "period": "FY",
        "revenue": 1_000.0,
        "net_income": 100.0,
        "shares_outstanding": 100,
        "stockholders_equity": 500.0,
        "total_debt": 200.0,
        "long_term_debt": 200.0,
        "cash_and_equivalents": 300.0,
        "current_assets": 600.0,
        "current_liabilities": 300.0,
        "operating_cash_flow": 150.0,
        "capital_expenditure": 50.0,
        "dividends_paid": 30.0,
        "inventory": 80.0,
        "net_ppe": 400.0,
    }
    data.update(overrides)
    return NormalizedFinancials.from_dict(data)


def _history(count: int = 5, **overrides):
    """Newest-first rows; ``overrides`` may contain per-index callables."""
    rows = []
    for index in range(count):
        values = {}
        for key, value in overrides.items():
            values[key] = value(index) if callable(value) else value
        rows.append(_row(2025 - index, **values))
    return rows


def _growth_history(rate: float = 0.12, count: int = 5, **overrides):
    return _history(
        count,
        revenue=lambda index: 1_000.0 * (1.0 + rate) ** (count - 1 - index),
        net_income=lambda index: 100.0 * (1.0 + rate) ** (count - 1 - index),
        **overrides,
    )


def _check(rule_id, rows, price=None, market_cap=None, category=None):
    return next(
        item
        for item in run_checks(rows, price, market_cap, category)
        if item.rule_id == rule_id
    )


# ---------------------------------------------------------------------------
# core GARP
# ---------------------------------------------------------------------------
def test_peg_below_1():
    rows = _growth_history()
    # P/E 11 at 12% growth -> PEG 0.92
    assert _check("lynch.deep_peg_below_1", rows, price=11.0).passed is True
    assert _check("lynch.deep_peg_below_1", rows, price=30.0).passed is False
    assert _check("lynch.deep_peg_below_1", rows).passed is None


def test_pe_below_30():
    rows = _growth_history()
    assert _check("lynch.deep_pe_below_30", rows, price=20.0).passed is True
    assert _check("lynch.deep_pe_below_30", rows, price=60.0).passed is False


def test_earnings_growth_above_10():
    growing = _growth_history(0.12)
    flat = _history(net_income=100.0)
    assert _check("lynch.deep_earnings_growth_above_10", growing).passed is True
    assert _check("lynch.deep_earnings_growth_above_10", flat).passed is False


def test_positive_earnings_5y():
    healthy = _growth_history()
    loss = _history(net_income=lambda index: -5.0 if index == 2 else 100.0)
    assert _check("lynch.deep_positive_earnings_5y", healthy).passed is True
    assert _check("lynch.deep_positive_earnings_5y", loss).passed is False


def test_revenue_growth_positive_5y():
    growing = _growth_history()
    shrinking = _history(
        revenue=lambda index: 800.0 + index * 50.0,
        net_income=100.0,
    )
    assert _check("lynch.deep_revenue_growth_positive_5y", growing).passed is True
    assert _check("lynch.deep_revenue_growth_positive_5y", shrinking).passed is False


# ---------------------------------------------------------------------------
# financial health
# ---------------------------------------------------------------------------
def test_debt_equity_below_0_8():
    rows = _history()
    assert (
        _check("lynch.deep_debt_equity_below_0_8", rows).passed is True
    )  # 200 / 500 = 0.4
    heavy = _history(total_debt=500.0)
    assert _check("lynch.deep_debt_equity_below_0_8", heavy).passed is False


def test_current_ratio_1_5():
    rows = _history()
    assert _check("lynch.deep_current_ratio_1_5", rows).passed is True
    tight = _history(current_assets=360.0, current_liabilities=300.0)
    assert _check("lynch.deep_current_ratio_1_5", tight).passed is False


def test_fcf_positive():
    rows = _history()
    assert _check("lynch.deep_fcf_positive", rows).passed is True
    burning = _history(operating_cash_flow=40.0, capital_expenditure=100.0)
    assert _check("lynch.deep_fcf_positive", burning).passed is False


def test_inventory_vs_revenue():
    calm = _history()
    building = _history(inventory=lambda index: 120.0 if index == 0 else 80.0)
    assert _check("lynch.deep_inventory_vs_revenue", calm).passed is True
    assert _check("lynch.deep_inventory_vs_revenue", building).passed is False


def test_cash_vs_debt():
    rows = _history()
    assert _check("lynch.deep_cash_vs_debt", rows).passed is True  # 300 / 200
    thin = _history(cash_and_equivalents=50.0)
    assert _check("lynch.deep_cash_vs_debt", thin).passed is False


# ---------------------------------------------------------------------------
# valuation
# ---------------------------------------------------------------------------
def test_pb_below_3():
    rows = _history()
    assert (
        _check("lynch.deep_pb_below_3", rows, market_cap=1_000.0).passed is True
    )  # 2x book
    assert (
        _check("lynch.deep_pb_below_3", rows, market_cap=2_000.0).passed is False
    )  # 4x book


def test_pe_below_own_5y_average():
    growing = _growth_history()
    flat = _history(net_income=100.0)
    assert (
        _check("lynch.deep_pe_below_own_5y_average", growing, price=20.0).passed is True
    )
    assert (
        _check("lynch.deep_pe_below_own_5y_average", flat, price=20.0).passed is False
    )  # current == average


def test_slow_grower_dividend_requirement():
    paying = _history()
    suspended = _history(dividends_paid=lambda index: 30.0 if index == 0 else 0.0)
    assert (
        _check(
            "lynch.deep_slow_grower_dividend",
            paying,
            category="SLOW_GROWER",
        ).passed
        is True
    )
    assert (
        _check(
            "lynch.deep_slow_grower_dividend",
            suspended,
            category="SLOW_GROWER",
        ).passed
        is False
    )
    # N/A for every other category.
    assert (
        _check("lynch.deep_slow_grower_dividend", paying, category="STALWART").passed
        is None
    )


# ---------------------------------------------------------------------------
# category-specific
# ---------------------------------------------------------------------------
def test_fast_grower_profile():
    rows = _growth_history(0.22)
    # P/E 8 at 22% growth -> PEG 0.36 (inside the 20-25% band).
    assert (
        _check(
            "lynch.deep_fast_grower_profile",
            rows,
            price=8.0,
            category="FAST_GROWER",
        ).passed
        is True
    )
    # P/E 30 -> PEG 1.36, above the 0.5 demand.
    assert (
        _check(
            "lynch.deep_fast_grower_profile",
            rows,
            price=30.0,
            category="FAST_GROWER",
        ).passed
        is False
    )


def test_stalwart_profile():
    rows = _growth_history(0.11)
    assert (
        _check(
            "lynch.deep_stalwart_profile",
            rows,
            price=12.0,
            category="STALWART",
        ).passed
        is True
    )
    assert (
        _check(
            "lynch.deep_stalwart_profile",
            rows,
            price=30.0,
            category="STALWART",
        ).passed
        is False
    )


def test_slow_grower_income():
    rows = _history()  # DPS 0.3, payout 30%
    assert (
        _check(
            "lynch.deep_slow_grower_income",
            rows,
            price=5.0,
            category="SLOW_GROWER",
        ).passed
        is True
    )  # 6% yield, 30% payout
    assert (
        _check(
            "lynch.deep_slow_grower_income",
            rows,
            price=20.0,
            category="SLOW_GROWER",
        ).passed
        is False
    )  # 1.5% yield


def test_cyclical_position():
    calm = _history()
    assert (
        _check(
            "lynch.deep_cyclical_position",
            calm,
            price=12.0,
            category="CYCLICAL",
        ).passed
        is True
    )
    building = _history(inventory=lambda index: 120.0 if index == 0 else 80.0)
    assert (
        _check(
            "lynch.deep_cyclical_position",
            building,
            price=12.0,
            category="CYCLICAL",
        ).passed
        is False
    )


def test_turnaround_progress():
    deleveraging = _history(total_debt=lambda index: 150.0 if index == 0 else 200.0)
    stable_debt = _history()
    burning = _history(
        operating_cash_flow=10.0,
        capital_expenditure=50.0,
        total_debt=lambda index: 150.0 if index == 0 else 200.0,
    )
    assert (
        _check(
            "lynch.deep_turnaround_progress",
            deleveraging,
            category="TURNAROUND",
        ).passed
        is True
    )
    assert (
        _check(
            "lynch.deep_turnaround_progress", stable_debt, category="TURNAROUND"
        ).passed
        is False
    )
    assert (
        _check("lynch.deep_turnaround_progress", burning, category="TURNAROUND").passed
        is False
    )


def test_asset_play_discount():
    rows = _history()  # book 500, tangible 780
    assert (
        _check(
            "lynch.deep_asset_play_discount",
            rows,
            market_cap=400.0,
            category="ASSET_PLAY",
        ).passed
        is True
    )  # P/B 0.8, tangible cover 195%
    assert (
        _check(
            "lynch.deep_asset_play_discount",
            rows,
            market_cap=600.0,
            category="ASSET_PLAY",
        ).passed
        is False
    )  # P/B 1.2


def test_category_rules_are_na_for_other_categories():
    rows = _history()
    for rule_id in (
        "lynch.deep_fast_grower_profile",
        "lynch.deep_stalwart_profile",
        "lynch.deep_slow_grower_income",
        "lynch.deep_cyclical_position",
        "lynch.deep_turnaround_progress",
        "lynch.deep_asset_play_discount",
    ):
        assert _check(rule_id, rows, price=10.0, category="UNKNOWN").passed is None


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------
def test_scored_results_drops_inapplicable_category_rules():
    rows = _history()
    results = run_checks(rows, price=10.0, market_cap=1_000.0, category="FAST_GROWER")
    scored = scored_results(results, "FAST_GROWER")
    ids = {item.rule_id for item in scored}
    assert "lynch.deep_fast_grower_profile" in ids
    assert "lynch.deep_stalwart_profile" not in ids
    assert "lynch.deep_asset_play_discount" not in ids


def _result(passed, weight):
    return WeightedResult(
        rule_id="test",
        name="test",
        category="test",
        weight=weight,
        passed=passed,
        detail="",
    )


def test_weighted_thresholds():
    assert weighted_verdict([_result(True, 17), _result(False, 3)])[0].value == "BUY"
    assert weighted_verdict([_result(True, 15), _result(False, 5)])[0].value == "WATCH"
    assert weighted_verdict([_result(True, 10), _result(False, 10)])[0].value == "HOLD"
    assert weighted_verdict([_result(True, 9), _result(False, 11)])[0].value == "AVOID"


def test_weighted_insufficient_data_when_missing_weight_exceeds_30pct():
    verdict, score, confidence = weighted_verdict([_result(True, 6), _result(None, 4)])
    assert verdict.value == "INSUFFICIENT_DATA"
    assert score is None
    assert confidence.value == "LOW"
