"""Buffett rule tests: one focused test per rule plus the weighted verdict."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.buffett_classic.methodology import (
    BuffettClassicMethodology,
)
from backend.methodologies.buffett_classic.rules import run_checks


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


def _history(count: int = 5, **overrides):
    """Newest-first rows; ``overrides`` may contain per-year callables."""
    rows = []
    for index in range(count):
        values = {}
        for key, value in overrides.items():
            values[key] = value(index) if callable(value) else value
        rows.append(_row(2025 - index, **values))
    return rows


def _check(rule_id: str, rows, price=None, dcf=None):
    return next(
        result for result in run_checks(rows, price, dcf) if result.rule_id == rule_id
    )


def _flat(**overrides):
    return _history(1, **overrides)


# ---------------------------------------------------------------------------
# moat
# ---------------------------------------------------------------------------
def test_roic_current():
    strong = [
        _row(2025, ebit=50, stockholders_equity=100, tax_provision=0, pretax_income=100)
    ]
    weak = [
        _row(2025, ebit=10, stockholders_equity=100, tax_provision=0, pretax_income=100)
    ]
    assert _check("buffett.roic_current", strong).passed is True
    assert _check("buffett.roic_current", weak).passed is False
    assert _check("buffett.roic_current", [_row(2025)]).passed is None


def test_roic_persistence():
    strong = _history(
        5, ebit=50, stockholders_equity=100, tax_provision=0, pretax_income=100
    )
    weak = strong[:-1] + [
        _row(2021, ebit=5, stockholders_equity=100, tax_provision=0, pretax_income=100)
    ]
    assert _check("buffett.roic_10y_persistence", strong).passed is True
    assert _check("buffett.roic_10y_persistence", weak).passed is False
    assert _check("buffett.roic_10y_persistence", strong[:4]).passed is None


def test_gross_margin_stability():
    stable = _history(5, revenue=100, gross_profit=40)
    volatile = _history(5, revenue=100, gross_profit=lambda i: 20 if i % 2 else 60)
    assert _check("buffett.gross_margin_stability", stable).passed is True
    assert _check("buffett.gross_margin_stability", volatile).passed is False
    assert _check("buffett.gross_margin_stability", stable[:2]).passed is None


def test_operating_margin_trend():
    improving = _history(
        5, revenue=100, operating_income=lambda i: 30 if i == 0 else 25
    )
    eroding = _history(5, revenue=100, operating_income=lambda i: 10 if i == 0 else 30)
    assert _check("buffett.operating_margin_trend", improving).passed is True
    assert _check("buffett.operating_margin_trend", eroding).passed is False


def test_pricing_power():
    growth = _history(
        5,
        revenue=lambda i: 100 * (1.05 ** (4 - i)),
        gross_profit=lambda i: 40 * (1.05 ** (4 - i)),
    )
    flat = _history(5, revenue=100, gross_profit=40)
    assert _check("buffett.pricing_power", growth).passed is True
    assert _check("buffett.pricing_power", flat).passed is False


# ---------------------------------------------------------------------------
# financial strength
# ---------------------------------------------------------------------------
def test_debt_to_equity():
    assert (
        _check(
            "buffett.debt_equity_below_1", _flat(total_debt=50, stockholders_equity=100)
        ).passed
        is True
    )
    assert (
        _check(
            "buffett.debt_equity_below_1",
            _flat(total_debt=150, stockholders_equity=100),
        ).passed
        is False
    )
    assert (
        _check(
            "buffett.debt_equity_below_1",
            _flat(total_debt=150, stockholders_equity=-10),
        ).passed
        is False
    )


def test_interest_coverage():
    assert (
        _check(
            "buffett.interest_coverage_10", _flat(ebit=100, interest_expense=10)
        ).passed
        is True
    )
    assert (
        _check(
            "buffett.interest_coverage_10", _flat(ebit=100, interest_expense=20)
        ).passed
        is False
    )
    assert (
        _check("buffett.interest_coverage_10", _flat(ebit=100, total_debt=0)).passed
        is True
    )


def test_current_ratio():
    assert (
        _check(
            "buffett.current_ratio_1_5",
            _flat(current_assets=150, current_liabilities=100),
        ).passed
        is True
    )
    assert (
        _check(
            "buffett.current_ratio_1_5",
            _flat(current_assets=100, current_liabilities=100),
        ).passed
        is False
    )
    assert _check("buffett.current_ratio_1_5", _flat(current_assets=150)).passed is None


def test_fcf_positive_5y():
    positive = _history(5, free_cash_flow=10)
    one_negative = positive[:2] + [_row(2023, free_cash_flow=-5)] + positive[3:]
    assert _check("buffett.fcf_positive_5y", positive).passed is True
    assert _check("buffett.fcf_positive_5y", one_negative).passed is False
    assert _check("buffett.fcf_positive_5y", positive[:2]).passed is None


# ---------------------------------------------------------------------------
# earnings quality
# ---------------------------------------------------------------------------
def test_net_margin():
    assert (
        _check("buffett.net_margin_10", _flat(revenue=100, net_income=15)).passed
        is True
    )
    assert (
        _check("buffett.net_margin_10", _flat(revenue=100, net_income=5)).passed
        is False
    )


def test_fcf_conversion():
    assert (
        _check(
            "buffett.fcf_conversion_80", _flat(net_income=100, free_cash_flow=90)
        ).passed
        is True
    )
    assert (
        _check(
            "buffett.fcf_conversion_80", _flat(net_income=100, free_cash_flow=50)
        ).passed
        is False
    )
    assert (
        _check(
            "buffett.fcf_conversion_80", _flat(net_income=-10, free_cash_flow=10)
        ).passed
        is False
    )


def test_earnings_consistency():
    stable = _history(5, net_income=lambda i: 100 * (1.05 ** (4 - i)))
    volatile = _history(5, net_income=lambda i: [500, 100, 400, 80, 450][i])
    assert _check("buffett.earnings_consistency", stable).passed is True
    assert _check("buffett.earnings_consistency", volatile).passed is False


def test_owner_earnings():
    good = _flat(net_income=100, depreciation_amortization=20, capital_expenditure=30)
    bad = _flat(net_income=100, depreciation_amortization=20, capital_expenditure=200)
    assert _check("buffett.owner_earnings_positive", good).passed is True
    assert _check("buffett.owner_earnings_positive", bad).passed is False
    assert (
        _check("buffett.owner_earnings_positive", _flat(net_income=100)).passed is None
    )


# ---------------------------------------------------------------------------
# capital allocation
# ---------------------------------------------------------------------------
def test_no_dilution():
    shrinking = _history(5, shares_outstanding=100)
    buying = _history(5, shares_outstanding=lambda i: 100 - 2 * (4 - i))
    diluting = _history(5, shares_outstanding=lambda i: 100 + 10 * (4 - i))
    assert _check("buffett.no_dilution_5y", shrinking).passed is True
    assert _check("buffett.no_dilution_5y", buying).passed is True
    assert _check("buffett.no_dilution_5y", diluting).passed is False


def test_buybacks():
    buying = _history(6, shares_outstanding=lambda i: 100 - 2 * (5 - i))
    flat = _history(6, shares_outstanding=100)
    assert _check("buffett.buybacks_3_of_5y", buying).passed is True
    assert _check("buffett.buybacks_3_of_5y", flat).passed is False


# ---------------------------------------------------------------------------
# valuation
# ---------------------------------------------------------------------------
def test_dcf_margin_of_safety():
    dcf = SimpleNamespace(margin_of_safety=0.25, intrinsic_value_per_share=125.0)
    weak = SimpleNamespace(margin_of_safety=0.10, intrinsic_value_per_share=110.0)
    assert _check("buffett.dcf_margin_of_safety_20", _flat(), 100.0, dcf).passed is True
    assert (
        _check("buffett.dcf_margin_of_safety_20", _flat(), 100.0, weak).passed is False
    )
    assert (
        _check("buffett.dcf_margin_of_safety_20", _flat(), 100.0, None).passed is None
    )


def test_earnings_yield():
    rows = _history(3, net_income=100, shares_outstanding=100)
    assert _check("buffett.earnings_yield_5", rows, 10.0).passed is True
    assert _check("buffett.earnings_yield_5", rows, 50.0).passed is False


def test_pe_below_20():
    rows = _history(3, net_income=100, shares_outstanding=100)
    assert _check("buffett.pe_below_20", rows, 10.0).passed is True
    assert _check("buffett.pe_below_20", rows, 50.0).passed is False


# ---------------------------------------------------------------------------
# management (informational)
# ---------------------------------------------------------------------------
def test_insider_ownership_is_informational():
    result = _check("buffett.insider_ownership", _flat())
    assert result.passed is None
    assert result.weight == 0


def test_rd_ratio():
    assert (
        _check("buffett.rd_ratio_3", _flat(revenue=100, research_development=5)).passed
        is True
    )
    assert (
        _check("buffett.rd_ratio_3", _flat(revenue=100, research_development=1)).passed
        is False
    )
    assert _check("buffett.rd_ratio_3", _flat(revenue=100)).passed is None


# ---------------------------------------------------------------------------
# framework
# ---------------------------------------------------------------------------
def test_all_checks_are_registered():
    results = run_checks([_row(2025)], None)
    assert len(results) == 20
    assert len({result.rule_id for result in results}) == 20


def test_weighted_verdict_thresholds():
    cases = [
        (0.90, "BUY"),
        (0.85, "BUY"),
        (0.80, "WATCH"),
        (0.70, "WATCH"),
        (0.60, "HOLD"),
        (0.50, "HOLD"),
        (0.40, "AVOID"),
    ]
    for ratio, expected in cases:
        passed = round(ratio * 100)
        outcomes = [SimpleNamespace(passed=True, weight=1) for _ in range(passed)] + [
            SimpleNamespace(passed=False, weight=1) for _ in range(100 - passed)
        ]
        verdict, score, _confidence = BuffettClassicMethodology._weighted_verdict(
            outcomes
        )
        assert verdict.value == expected, ratio
        assert score == pytest.approx(ratio * 100, abs=0.01)


def test_missing_weight_above_30pct_is_insufficient():
    results = [
        SimpleNamespace(passed=True, weight=2),
        SimpleNamespace(passed=None, weight=2),
        SimpleNamespace(passed=None, weight=2),
    ]
    verdict, score, confidence = BuffettClassicMethodology._weighted_verdict(results)
    assert verdict.value == "INSUFFICIENT_DATA"
    assert score is None
    assert confidence.value == "LOW"


def test_informational_rules_do_not_enter_the_score():
    results = [
        SimpleNamespace(passed=True, weight=1),
        SimpleNamespace(passed=False, weight=1),
        SimpleNamespace(passed=False, weight=0),
    ]
    verdict, score, _confidence = BuffettClassicMethodology._weighted_verdict(results)
    assert verdict.value == "HOLD"
    assert score == pytest.approx(50.0)
