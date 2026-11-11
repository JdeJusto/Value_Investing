"""Focused tests for the Marks deep checks and the weighted aggregation.

One pass/fail fixture per deep rule, the weighted thresholds, and a full-pass
methodology fixture that still reaches BUY under the weighted framework.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.common.weighted import WeightedResult, weighted_verdict
from backend.methodologies.marks.deep_checks import run_checks
from backend.methodologies.marks.methodology import MarksMethodology


class _Prices:
    def __init__(self, market_cap=2_000.0, price=20.0):
        self._market_cap = market_cap
        self._price = price

    def get_market_cap(self, ticker):
        return self._market_cap

    def get_current_price(self, ticker):
        return self._price


def _row(year: int, **overrides):
    data = {
        "ticker": "TEST",
        "fiscal_year": year,
        "period": "FY",
        "revenue": 1_000.0,
        "operating_income": 200.0,
        "ebit": 200.0,
        "ebitda": 250.0,
        "net_income": 100.0,
        "interest_expense": 10.0,
        "total_debt": 200.0,
        "stockholders_equity": 1_000.0,
        "cash_and_equivalents": 200.0,
        "operating_cash_flow": 250.0,
        "capital_expenditure": 50.0,
        "shares_outstanding": 100,
    }
    data.update(overrides)
    return NormalizedFinancials.from_dict(data)


def _history(count: int = 5, **overrides):
    rows = []
    for index in range(count):
        values = {}
        for key, value in overrides.items():
            values[key] = value(index) if callable(value) else value
        rows.append(_row(2025 - index, **values))
    return rows


def _growth_history(rate: float = 0.05, count: int = 5, **overrides):
    scaler = lambda index: (1.0 + rate) ** (count - 1 - index)
    return _history(
        count,
        revenue=lambda index: 1_000.0 * scaler(index),
        operating_income=lambda index: 200.0 * scaler(index),
        ebit=lambda index: 200.0 * scaler(index),
        ebitda=lambda index: 250.0 * scaler(index),
        net_income=lambda index: 100.0 * scaler(index),
        operating_cash_flow=lambda index: 250.0 * scaler(index),
        capital_expenditure=lambda index: 50.0 * scaler(index),
        **overrides,
    )


def _check(rule_id, rows, price=20.0, market_cap=2_000.0, dcf=None):
    return next(
        item
        for item in run_checks(rows, price, market_cap, dcf)
        if item.rule_id == rule_id
    )


# ---------------------------------------------------------------------------
# valuation
# ---------------------------------------------------------------------------
def test_price_below_intrinsic_20():
    rows = _history()
    cheap = SimpleNamespace(margin_of_safety=0.25, intrinsic_value_per_share=25.0)
    rich = SimpleNamespace(margin_of_safety=0.10, intrinsic_value_per_share=22.0)
    assert _check("marks.deep_price_below_intrinsic_20", rows, dcf=cheap).passed is True
    assert _check("marks.deep_price_below_intrinsic_20", rows, dcf=rich).passed is False
    assert _check("marks.deep_price_below_intrinsic_20", rows, dcf=None).passed is None


def test_pe_below_own_5y_average():
    growing = _growth_history()
    flat = _history()
    assert _check("marks.deep_pe_below_own_5y_average", growing).passed is True
    assert _check("marks.deep_pe_below_own_5y_average", flat).passed is False


def test_pb_below_2():
    assert (
        _check("marks.deep_pb_below_2", _history(stockholders_equity=1_200.0)).passed
        is True
    )  # 1.67x
    assert (
        _check("marks.deep_pb_below_2", _history(stockholders_equity=800.0)).passed
        is False
    )  # 2.5x


def test_earnings_yield_5():
    rows = _history()
    assert _check("marks.deep_earnings_yield_5", rows, price=20.0).passed is True
    assert _check("marks.deep_earnings_yield_5", rows, price=40.0).passed is False


# ---------------------------------------------------------------------------
# quality
# ---------------------------------------------------------------------------
def test_roic_15():
    healthy = _history()  # 200 / (200 + 1000 - 200) = 25%
    weak = _history(stockholders_equity=2_000.0)  # 10%
    assert _check("marks.deep_roic_15", healthy).passed is True
    assert _check("marks.deep_roic_15", weak).passed is False


def test_fcf_positive_5y():
    healthy = _history()
    burning = _history(operating_cash_flow=lambda index: 10.0 if index == 2 else 250.0)
    assert _check("marks.deep_fcf_positive_5y", healthy).passed is True
    assert _check("marks.deep_fcf_positive_5y", burning).passed is False


def test_margin_stability():
    stable = _history()
    volatile = _history(
        operating_income=lambda index: 400.0 if index % 2 == 0 else 100.0
    )
    assert _check("marks.deep_margin_stability", stable).passed is True
    assert _check("marks.deep_margin_stability", volatile).passed is False


def test_revenue_growth_positive():
    growing = _growth_history()
    flat = _history()
    assert _check("marks.deep_revenue_growth_positive", growing).passed is True
    assert _check("marks.deep_revenue_growth_positive", flat).passed is False


# ---------------------------------------------------------------------------
# risk control
# ---------------------------------------------------------------------------
def test_low_debt():
    assert _check("marks.deep_low_debt", _history()).passed is True  # 0x
    assert (
        _check("marks.deep_low_debt", _history(total_debt=1_000.0)).passed is False
    )  # 3.2x


def test_interest_coverage_10():
    assert _check("marks.deep_interest_coverage_10", _history()).passed is True
    assert (
        _check(
            "marks.deep_interest_coverage_10", _history(interest_expense=30.0)
        ).passed
        is False
    )


def test_no_dilution_5y():
    flat = _history()
    diluted = _history(shares_outstanding=lambda index: 120 if index == 0 else 100)
    assert _check("marks.deep_no_dilution_5y", flat).passed is True
    assert _check("marks.deep_no_dilution_5y", diluted).passed is False


# ---------------------------------------------------------------------------
# cycle position
# ---------------------------------------------------------------------------
def test_pe_percentile_10y():
    growing = _growth_history(count=10)
    flat = _history(count=10)
    assert _check("marks.deep_pe_percentile_10y", growing).passed is True
    assert _check("marks.deep_pe_percentile_10y", flat).passed is False


def test_not_peak_margin():
    normal = _history()
    peak = _history(
        operating_income=lambda index: 300.0 if index == 0 else 200.0,
        ebit=lambda index: 300.0 if index == 0 else 200.0,
    )
    assert _check("marks.deep_not_peak_margin", normal).passed is True
    assert _check("marks.deep_not_peak_margin", peak).passed is False


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------
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


def test_full_pass_fixture_reaches_buy():
    rows = _growth_history(stockholders_equity=1_200.0)
    result = MarksMethodology().evaluate(
        "TEST", rows, _Prices(market_cap=2_000.0, price=20.0)
    )
    assert result.verdict.value == "BUY"
    assert result.score == 100.0
