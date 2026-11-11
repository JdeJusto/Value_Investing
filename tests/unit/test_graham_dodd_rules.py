"""Deep Graham & Dodd checks: one focused test per rule plus the weights."""

from __future__ import annotations

import pytest

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.common.weighted import WeightedResult, weighted_verdict
from backend.methodologies.graham_dodd.deep_checks import CHECKS, run_checks


def _row(year: int, **overrides):
    data = {
        "ticker": "TEST",
        "fiscal_year": year,
        "period": "FY",
        "currency": "USD",
        "source": "sec_edgar",
        "shares_outstanding": 100,
        "split_adjustment_factor": 1.0,
    }
    data.update(overrides)
    return NormalizedFinancials.from_dict(data)


def _history(values, **overrides):
    """Newest-first rows from a list of values (one per fiscal year)."""
    return [
        _row(2025 - index, **{**overrides, "net_income": value})
        for index, value in enumerate(values)
    ]


def _check(rule_id: str, rows, price: float | None = None):
    return next(
        result for result in run_checks(rows, price) if result.rule_id == rule_id
    )


def _weighted(passed: int, failed: int, missing: int = 0):
    results = []
    for index in range(passed):
        results.append(_result(f"p{index}", True))
    for index in range(failed):
        results.append(_result(f"f{index}", False))
    for index in range(missing):
        results.append(_result(f"m{index}", None))
    return results


def _result(rule_id: str, passed: bool | None) -> WeightedResult:
    return WeightedResult(
        rule_id=rule_id,
        name=rule_id,
        category="test",
        weight=1,
        passed=passed,
        detail="",
    )


# ----------------------------------------------------------------------
# net-net / NCAV
# ----------------------------------------------------------------------
def test_ncav_positive():
    assert (
        _check(
            "graham_dodd.net_net_ncav_positive",
            [_row(2025, current_assets=200, total_liabilities=100)],
        ).passed
        is True
    )
    assert (
        _check(
            "graham_dodd.net_net_ncav_positive",
            [_row(2025, current_assets=100, total_liabilities=200)],
        ).passed
        is False
    )
    assert (
        _check(
            "graham_dodd.net_net_ncav_positive",
            [_row(2025, total_liabilities=200)],
        ).passed
        is None
    )


def test_ncav_above_market_cap():
    # NCAV 800, market cap 5 x 100 = 500.
    rows = [_row(2025, current_assets=1000, total_liabilities=200)]
    assert (
        _check("graham_dodd.net_net_ncav_above_market_cap", rows, price=5.0).passed
        is True
    )
    assert (
        _check("graham_dodd.net_net_ncav_above_market_cap", rows, price=10.0).passed
        is False
    )
    assert (
        _check("graham_dodd.net_net_ncav_above_market_cap", rows, price=None).passed
        is None
    )


def test_ncav_1_5x_market_cap():
    # NCAV 800 must cover 1.5 x market cap: 500 -> 750 passes, 600 -> 900 fails.
    rows = [_row(2025, current_assets=1000, total_liabilities=200)]
    assert (
        _check("graham_dodd.net_net_ncav_1_5x_market_cap", rows, price=5.0).passed
        is True
    )
    assert (
        _check("graham_dodd.net_net_ncav_1_5x_market_cap", rows, price=6.0).passed
        is False
    )


def test_price_le_two_thirds_ncav():
    # NCAV/share = 800 / 100 = 8; 2/3 = 5.333.
    rows = [_row(2025, current_assets=1000, total_liabilities=200)]
    assert (
        _check("graham_dodd.net_net_price_le_two_thirds_ncav", rows, price=5.0).passed
        is True
    )
    assert (
        _check("graham_dodd.net_net_price_le_two_thirds_ncav", rows, price=6.0).passed
        is False
    )


# ----------------------------------------------------------------------
# balance sheet
# ----------------------------------------------------------------------
def test_current_ratio_2():
    assert (
        _check(
            "graham_dodd.balance_current_ratio_2",
            [_row(2025, current_assets=200, current_liabilities=100)],
        ).passed
        is True
    )
    assert (
        _check(
            "graham_dodd.balance_current_ratio_2",
            [_row(2025, current_assets=150, current_liabilities=100)],
        ).passed
        is False
    )
    assert (
        _check(
            "graham_dodd.balance_current_ratio_2",
            [_row(2025, current_assets=200)],
        ).passed
        is None
    )


def test_debt_below_equity():
    assert (
        _check(
            "graham_dodd.balance_debt_below_equity",
            [_row(2025, total_debt=50, stockholders_equity=100)],
        ).passed
        is True
    )
    assert (
        _check(
            "graham_dodd.balance_debt_below_equity",
            [_row(2025, total_debt=150, stockholders_equity=100)],
        ).passed
        is False
    )
    assert (
        _check(
            "graham_dodd.balance_debt_below_equity",
            [_row(2025, total_debt=50, stockholders_equity=-10)],
        ).passed
        is False
    )


def test_positive_working_capital():
    assert (
        _check(
            "graham_dodd.balance_positive_working_capital",
            [_row(2025, current_assets=200, current_liabilities=100)],
        ).passed
        is True
    )
    assert (
        _check(
            "graham_dodd.balance_positive_working_capital",
            [_row(2025, current_assets=100, current_liabilities=200)],
        ).passed
        is False
    )


def test_debt_le_half_equity():
    assert (
        _check(
            "graham_dodd.balance_debt_le_half_equity",
            [_row(2025, total_debt=50, stockholders_equity=100)],
        ).passed
        is True
    )
    assert (
        _check(
            "graham_dodd.balance_debt_le_half_equity",
            [_row(2025, total_debt=60, stockholders_equity=100)],
        ).passed
        is False
    )


def test_debt_le_working_capital():
    assert (
        _check(
            "graham_dodd.balance_debt_le_working_capital",
            [
                _row(
                    2025,
                    total_debt=50,
                    current_assets=200,
                    current_liabilities=100,
                )
            ],
        ).passed
        is True
    )
    assert (
        _check(
            "graham_dodd.balance_debt_le_working_capital",
            [
                _row(
                    2025,
                    total_debt=150,
                    current_assets=200,
                    current_liabilities=100,
                )
            ],
        ).passed
        is False
    )
    assert (
        _check(
            "graham_dodd.balance_debt_le_working_capital",
            [_row(2025, total_debt=50)],
        ).passed
        is None
    )


# ----------------------------------------------------------------------
# earnings power
# ----------------------------------------------------------------------
def test_positive_earnings_5y():
    assert _check("graham_dodd.earnings_positive_5y", _history([10] * 5)).passed is True
    assert (
        _check(
            "graham_dodd.earnings_positive_5y", _history([10, -1, 10, 10, 10])
        ).passed
        is False
    )
    assert _check("graham_dodd.earnings_positive_5y", _history([10] * 4)).passed is None


def test_positive_earnings_10y():
    assert (
        _check("graham_dodd.earnings_positive_10y", _history([10] * 10)).passed is True
    )
    assert (
        _check(
            "graham_dodd.earnings_positive_10y", _history([10, -1] + [10] * 8)
        ).passed
        is False
    )
    assert (
        _check("graham_dodd.earnings_positive_10y", _history([10] * 4)).passed is None
    )


def test_earnings_stability():
    stable = [100 * (1.05**index) for index in range(10)]
    volatile = [100, 300, 80, 400, 50, 350, 90, 500, 70, 600]
    assert (
        _check("graham_dodd.earnings_stability_20pct", _history(stable)).passed is True
    )
    assert (
        _check("graham_dodd.earnings_stability_20pct", _history(volatile)).passed
        is False
    )


def test_eps_growth_10y():
    oldest_first = [100 * (1.12**index) for index in range(10)]
    rows = _history(list(reversed(oldest_first)))
    assert _check("graham_dodd.earnings_eps_growth_10y", rows).passed is True

    slow = list(reversed([100 * (1.05**index) for index in range(10)]))
    assert _check("graham_dodd.earnings_eps_growth_10y", _history(slow)).passed is False
    assert (
        _check("graham_dodd.earnings_eps_growth_10y", _history([10] * 9)).passed is None
    )


def test_epv_above_market_cap():
    rows = [_row(2025, ebit=100)]
    # EPV = 100 x 0.79 / 0.09 = 877.8; market cap = price x 100 shares.
    assert (
        _check("graham_dodd.earnings_epv_above_market_cap", rows, price=1.0).passed
        is True
    )
    assert (
        _check("graham_dodd.earnings_epv_above_market_cap", rows, price=20.0).passed
        is False
    )
    assert (
        _check(
            "graham_dodd.earnings_epv_above_market_cap",
            [_row(2025)],
            price=1.0,
        ).passed
        is None
    )


# ----------------------------------------------------------------------
# asset value
# ----------------------------------------------------------------------
def test_pb_below_1():
    rows = [_row(2025, stockholders_equity=1000)]
    # BVPS = 10.
    assert _check("graham_dodd.asset_pb_below_1", rows, price=9.0).passed is True
    assert _check("graham_dodd.asset_pb_below_1", rows, price=11.0).passed is False


def test_pb_below_067():
    rows = [_row(2025, stockholders_equity=1000)]
    assert _check("graham_dodd.asset_pb_below_067", rows, price=6.0).passed is True
    assert _check("graham_dodd.asset_pb_below_067", rows, price=7.0).passed is False


def test_tangible_book_positive():
    assert (
        _check(
            "graham_dodd.asset_tangible_book_positive",
            [_row(2025, stockholders_equity=100)],
        ).passed
        is True
    )
    assert (
        _check(
            "graham_dodd.asset_tangible_book_positive",
            [_row(2025, stockholders_equity=-5)],
        ).passed
        is False
    )
    assert (
        _check("graham_dodd.asset_tangible_book_positive", [_row(2025)]).passed is None
    )


def test_asset_coverage_2x_is_informational():
    check = next(
        check for check in CHECKS if check.rule_id == "graham_dodd.asset_coverage_2x"
    )
    assert check.weight == 0
    passing = [_row(2025, total_assets=1000, total_debt=400)]
    failing = [_row(2025, total_assets=1000, total_debt=600)]
    assert _check("graham_dodd.asset_coverage_2x", passing).passed is True
    assert _check("graham_dodd.asset_coverage_2x", failing).passed is False


# ----------------------------------------------------------------------
# margin of safety
# ----------------------------------------------------------------------
def test_price_below_graham_number():
    rows = [_row(2025, net_income=200, stockholders_equity=1000)]
    # EPS 2, BVPS 10 -> sqrt(22.5 x 2 x 10) = 21.21.
    assert (
        _check("graham_dodd.margin_price_below_graham_number", rows, price=20.0).passed
        is True
    )
    assert (
        _check("graham_dodd.margin_price_below_graham_number", rows, price=25.0).passed
        is False
    )


def test_price_below_ncav():
    rows = [_row(2025, current_assets=1000, total_liabilities=200)]
    # NCAV/share = 8.
    assert _check("graham_dodd.margin_price_below_ncav", rows, price=7.0).passed is True
    assert (
        _check("graham_dodd.margin_price_below_ncav", rows, price=9.0).passed is False
    )


def test_dividend_record_10y():
    assert (
        _check(
            "graham_dodd.margin_dividend_record_10y",
            [_row(2025 - index, dividends_paid=1) for index in range(10)],
        ).passed
        is True
    )
    interrupted = [_row(2025 - index, dividends_paid=1) for index in range(10)]
    interrupted[4] = _row(2021, dividends_paid=0)
    assert _check("graham_dodd.margin_dividend_record_10y", interrupted).passed is False
    assert (
        _check(
            "graham_dodd.margin_dividend_record_10y",
            [_row(2025 - index, dividends_paid=1) for index in range(4)],
        ).passed
        is None
    )


# ----------------------------------------------------------------------
# registry and weighted thresholds
# ----------------------------------------------------------------------
def test_all_checks_are_registered():
    assert len(CHECKS) == 21
    assert len({check.rule_id for check in CHECKS}) == 21


def test_categories_cover_the_five_groups():
    categories = {check.category for check in CHECKS}
    assert categories == {
        "net_net",
        "balance_sheet",
        "earnings_power",
        "asset_value",
        "margin_of_safety",
    }


@pytest.mark.parametrize(
    "passed, failed, expected",
    [
        (17, 3, "BUY"),  # 0.85
        (14, 6, "WATCH"),  # 0.70
        (10, 10, "HOLD"),  # 0.50
        (9, 11, "AVOID"),  # 0.45
    ],
)
def test_weighted_thresholds(passed, failed, expected):
    verdict, score, confidence = weighted_verdict(_weighted(passed, failed))
    assert verdict.value == expected
    assert score == pytest.approx(passed / 20 * 100)
    assert confidence.value == "HIGH"


def test_missing_weight_above_30pct_is_insufficient():
    verdict, score, confidence = weighted_verdict(_weighted(10, 3, missing=7))
    assert verdict.value == "INSUFFICIENT_DATA"
    assert score is None
    assert confidence.value == "LOW"


def test_informational_rules_do_not_enter_the_score():
    results = _weighted(3, 0) + [
        WeightedResult(
            rule_id="info",
            name="info",
            category="test",
            weight=0,
            passed=False,
            detail="",
        )
    ]
    verdict, score, _ = weighted_verdict(results)
    assert verdict.value == "BUY"
    assert score == pytest.approx(100.0)
