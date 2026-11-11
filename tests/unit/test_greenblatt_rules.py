"""Greenblatt overlay checks: one focused test per rule plus the weights."""

from __future__ import annotations

import pytest

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.common.weighted import WeightedResult, weighted_verdict
from backend.methodologies.greenblatt.deep_checks import CHECKS, run_checks


def _row(**overrides):
    base = {
        "ticker": "TEST",
        "fiscal_year": 2024,
        "period": "FY",
        "ebit": 200e6,
        "revenue": 1_000e6,
        "current_assets": 500e6,
        "current_liabilities": 200e6,
        "net_ppe": 300e6,
        "total_debt": 100e6,
        "cash_and_equivalents": 50e6,
        "sector": None,
    }
    base.update(overrides)
    return NormalizedFinancials(**base)


def _entry(**overrides):
    base = {
        "rank_roc": 5,
        "rank_ey": 5,
        "combined_rank": 10,
        "percentile": 0.05,
        "roc": 0.5,
        "earnings_yield": 0.2,
        "fiscal_year": 2024,
    }
    base.update(overrides)
    return base


def _check(rule_id: str, rows, entry):
    return next(
        result for result in run_checks(rows, entry) if result.rule_id == rule_id
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
# ranking
# ----------------------------------------------------------------------
def test_rank_in_file():
    assert _check("greenblatt.rank_in_file", [_row()], _entry()).passed is True
    assert _check("greenblatt.rank_in_file", [_row()], None).passed is None


def test_rank_top_50():
    assert (
        _check("greenblatt.rank_top_50", [_row()], _entry(combined_rank=50)).passed
        is True
    )
    assert (
        _check("greenblatt.rank_top_50", [_row()], _entry(combined_rank=51)).passed
        is False
    )
    assert (
        _check("greenblatt.rank_top_50", [_row()], _entry(combined_rank=None)).passed
        is None
    )


def test_rank_top_100():
    assert (
        _check("greenblatt.rank_top_100", [_row()], _entry(combined_rank=100)).passed
        is True
    )
    assert (
        _check("greenblatt.rank_top_100", [_row()], _entry(combined_rank=101)).passed
        is False
    )


# ----------------------------------------------------------------------
# ROC decomposition
# ----------------------------------------------------------------------
def test_ebit_positive():
    assert (
        _check("greenblatt.roc_ebit_positive", [_row(ebit=1)], _entry()).passed is True
    )
    assert (
        _check("greenblatt.roc_ebit_positive", [_row(ebit=0)], _entry()).passed is False
    )
    assert (
        _check("greenblatt.roc_ebit_positive", [_row(ebit=None)], _entry()).passed
        is None
    )


def test_roc_above_20():
    assert _check("greenblatt.roc_above_20", [_row()], _entry(roc=0.25)).passed is True
    assert _check("greenblatt.roc_above_20", [_row()], _entry(roc=0.15)).passed is False
    assert _check("greenblatt.roc_above_20", [_row()], _entry(roc=None)).passed is None


def test_capital_turnover_computable_is_informational():
    check = next(
        check
        for check in CHECKS
        if check.rule_id == "greenblatt.roc_capital_turnover_computable"
    )
    assert check.weight == 0
    # revenue 1,000m / (working capital 300m + net PPE 300m)
    assert (
        _check("greenblatt.roc_capital_turnover_computable", [_row()], _entry()).passed
        is True
    )
    assert (
        _check(
            "greenblatt.roc_capital_turnover_computable",
            [_row(net_ppe=None)],
            _entry(),
        ).passed
        is None
    )


# ----------------------------------------------------------------------
# earnings-yield decomposition
# ----------------------------------------------------------------------
def test_ey_above_8():
    assert (
        _check("greenblatt.ey_above_8", [_row()], _entry(earnings_yield=0.09)).passed
        is True
    )
    assert (
        _check("greenblatt.ey_above_8", [_row()], _entry(earnings_yield=0.05)).passed
        is False
    )


def test_ey_above_12():
    assert (
        _check("greenblatt.ey_above_12", [_row()], _entry(earnings_yield=0.13)).passed
        is True
    )
    assert (
        _check("greenblatt.ey_above_12", [_row()], _entry(earnings_yield=0.10)).passed
        is False
    )


def test_ev_positive():
    assert (
        _check("greenblatt.ey_ev_positive", [_row()], _entry(earnings_yield=0.2)).passed
        is True
    )
    assert (
        _check(
            "greenblatt.ey_ev_positive", [_row()], _entry(earnings_yield=-0.1)
        ).passed
        is False
    )


# ----------------------------------------------------------------------
# quality overlay
# ----------------------------------------------------------------------
def test_market_cap_above_100m():
    assert (
        _check(
            "greenblatt.quality_market_cap_above_100m",
            [_row()],
            _entry(market_cap=200e6),
        ).passed
        is True
    )
    assert (
        _check(
            "greenblatt.quality_market_cap_above_100m",
            [_row()],
            _entry(market_cap=50e6),
        ).passed
        is False
    )
    # Derived from EBIT / EY: 200m / 0.2 = 1,000m EV, - 100m debt + 50m cash.
    assert (
        _check("greenblatt.quality_market_cap_above_100m", [_row()], _entry()).passed
        is True
    )


def test_revenue_positive():
    assert (
        _check("greenblatt.quality_revenue_positive", [_row()], _entry()).passed is True
    )
    assert (
        _check(
            "greenblatt.quality_revenue_positive", [_row(revenue=0)], _entry()
        ).passed
        is False
    )
    assert (
        _check(
            "greenblatt.quality_revenue_positive", [_row(revenue=None)], _entry()
        ).passed
        is None
    )


def test_not_a_bank_is_informational():
    check = next(
        check for check in CHECKS if check.rule_id == "greenblatt.quality_not_a_bank"
    )
    assert check.weight == 0
    result = _check("greenblatt.quality_not_a_bank", [_row()], _entry())
    assert result.passed is None


# ----------------------------------------------------------------------
# registry, ranking primacy and weighted thresholds
# ----------------------------------------------------------------------
def test_all_checks_are_registered():
    assert len(CHECKS) == 12
    assert len({check.rule_id for check in CHECKS}) == 12


def test_ranking_entry_is_used_not_recomputed():
    """The ROC check reads the ranking, not a fresh ROC from the row."""
    row = _row(ebit=1e6)
    entry = _entry(roc=0.5)
    assert _check("greenblatt.roc_above_20", [row], entry).passed is True
    assert _check("greenblatt.roc_ebit_positive", [row], entry).passed is True


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
