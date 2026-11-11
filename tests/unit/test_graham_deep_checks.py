"""Deep Graham checks: one focused test per rule plus the weighted verdict."""

from __future__ import annotations

import pytest

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.graham.deep_checks import run_checks
from backend.methodologies.graham.methodology import GrahamMethodology


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


def test_debt_to_equity():
    rows = [_row(2025, total_debt=50, stockholders_equity=100)]
    assert _check("graham.deep_debt_to_equity", rows).passed is True
    rows = [_row(2025, total_debt=150, stockholders_equity=100)]
    assert _check("graham.deep_debt_to_equity", rows).passed is False


def test_interest_coverage():
    rows = [_row(2025, ebit=50, interest_expense=10)]
    assert _check("graham.deep_interest_coverage", rows).passed is True
    rows = [_row(2025, ebit=50, interest_expense=20)]
    assert _check("graham.deep_interest_coverage", rows).passed is False
    rows = [_row(2025, ebit=50, total_debt=0)]
    assert _check("graham.deep_interest_coverage", rows).passed is True


def test_positive_working_capital():
    rows = [_row(2025, current_assets=100, current_liabilities=80)]
    assert _check("graham.deep_positive_working_capital", rows).passed is True
    rows = [_row(2025, current_assets=70, current_liabilities=80)]
    assert _check("graham.deep_positive_working_capital", rows).passed is False


def test_positive_earnings_10y():
    assert (
        _check("graham.deep_positive_earnings_10y", _history([10] * 10)).passed is True
    )
    assert (
        _check(
            "graham.deep_positive_earnings_10y", _history([10, -1] + [10] * 8)
        ).passed
        is False
    )
    assert (
        _check("graham.deep_positive_earnings_10y", _history([10, 10])).passed is None
    )


def test_earnings_stability():
    stable = [100 * (1.05**index) for index in range(10)]
    volatile = [100, 300, 80, 400, 50, 350, 90, 500, 70, 600]
    assert _check("graham.deep_earnings_stability", _history(stable)).passed is True
    assert _check("graham.deep_earnings_stability", _history(volatile)).passed is False


def test_net_income_growing_3y():
    assert (
        _check("graham.deep_net_income_growing_3y", _history([120, 100, 80])).passed
        is True
    )
    assert (
        _check("graham.deep_net_income_growing_3y", _history([80, 100, 120])).passed
        is False
    )


def test_positive_latest_eps():
    assert _check("graham.deep_positive_eps", _history([10])).passed is True
    assert _check("graham.deep_positive_eps", _history([-10])).passed is False


def test_graham_number():
    rows = [_row(2025, net_income=200, stockholders_equity=1000)]
    # EPS 2, BVPS 10 -> sqrt(22.5*2*10) = 21.21
    assert _check("graham.deep_graham_number", rows, price=20.0).passed is True
    assert _check("graham.deep_graham_number", rows, price=25.0).passed is False


def test_pe_below_10_is_informational():
    rows = _history([100, 100, 100], net_income=100, shares_outstanding=100)
    result = _check("graham.deep_pe_below_10", rows, price=5.0)
    assert result.passed is True
    assert result.weight == 0


def test_revenue_growth_inflation():
    rows = [
        _row(2025 - index, revenue=100 * (1.03 ** (5 - index))) for index in range(6)
    ]
    assert _check("graham.deep_revenue_growth", rows).passed is True
    flat = [_row(2025 - index, revenue=100) for index in range(6)]
    assert _check("graham.deep_revenue_growth", flat).passed is False


def test_payout_ratio():
    rows = [_row(2025, net_income=100, dividends_paid=30)]
    assert _check("graham.deep_payout_ratio", rows).passed is True
    rows = [_row(2025, net_income=100, dividends_paid=90)]
    assert _check("graham.deep_payout_ratio", rows).passed is False
    rows = [_row(2025, net_income=100, dividends_paid=0)]
    assert _check("graham.deep_payout_ratio", rows).passed is None


def test_no_dividend_suspension():
    rows = [_row(2025 - index, dividends_paid=10) for index in range(5)]
    assert _check("graham.deep_no_dividend_suspension", rows).passed is True
    rows[2] = _row(2023, dividends_paid=0)
    assert _check("graham.deep_no_dividend_suspension", rows).passed is False


def test_epv_margin_of_safety():
    rows = [
        _row(
            2025,
            ebit=100,
            tax_provision=21,
            pretax_income=100,
            shares_outstanding=100,
        )
    ]
    # EPV/share = 100*0.79/0.09/100 = 8.78 -> target 5.85
    assert _check("graham.deep_epv_margin", rows, price=5.0).passed is True
    assert _check("graham.deep_epv_margin", rows, price=10.0).passed is False


def test_ncav_margin_of_safety():
    rows = [
        _row(
            2025,
            current_assets=200,
            total_liabilities=100,
            shares_outstanding=100,
        )
    ]
    # NCAV/share = 1.0 -> requires price < 0.667
    assert _check("graham.deep_ncav_margin", rows, price=0.5).passed is True
    assert _check("graham.deep_ncav_margin", rows, price=1.0).passed is False


def test_all_checks_are_registered():
    results = run_checks([_row(2025)], None)
    assert len(results) == 14
    assert len({result.rule_id for result in results}) == 14


def test_weighted_score_uses_weights():
    outcomes = [
        ("critical", True, 2),
        ("normal", True, 1),
        ("normal_fail", False, 1),
    ]
    verdict, score, _confidence = GrahamMethodology._weighted_verdict(outcomes)
    assert score == pytest.approx(75.0)
    assert verdict.value == "WATCH"


def test_utility_debt_limit_uses_two_times_equity():
    """The Intelligent Investor ch. 14 p. 112: utilities may carry 2x equity."""
    from backend.methodologies.graham.methodology import GrahamMethodology

    method = GrahamMethodology()
    passing = _row(
        2025,
        sector="Utilities",
        total_debt=150,
        stockholders_equity=100,
        current_assets=10,
        current_liabilities=200,
    )
    failing = _row(
        2025,
        sector="Utilities",
        total_debt=250,
        stockholders_equity=100,
        current_assets=10,
        current_liabilities=200,
    )
    industrial = _row(
        2025,
        sector="Industrials",
        total_debt=150,
        stockholders_equity=100,
        current_assets=10,
        current_liabilities=200,
    )

    assert method._criterion_3_debt_vs_working_capital([passing]).passed is True
    assert method._criterion_3_debt_vs_working_capital([failing]).passed is False
    # The industrial branch still uses working capital, which is negative here.
    assert method._criterion_3_debt_vs_working_capital([industrial]).passed is False
