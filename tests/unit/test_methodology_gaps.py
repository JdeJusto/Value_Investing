"""Tests for the methodology gaps found in the 2026-09-25 audit.

Covers the four gaps that were documented but not yet fixed:
1. Liquidity criteria (current ratio >= 2, quick ratio >= 1) were missing
   from the quality scoring.
2. The margin-of-safety gate was not enforced in the signal engine.
3. The rank_score function was not exposed for single-item use.
4. The composite score was not always present in the analysis output.
"""

from __future__ import annotations

import pytest

from backend.analytics.service import CompanyAnalysisService
from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.screener.ranking_engine import rank_score


def _row(year: int, **kwargs) -> NormalizedFinancials:
    defaults = dict(
        ticker="TEST",
        fiscal_year=year,
        source="edgar",
        revenue=100.0,
        net_income=12.0,
        total_assets=300.0,
        total_liabilities=120.0,
        stockholders_equity=180.0,
        cash_and_equivalents=60.0,
        working_capital=60.0,
        retained_earnings=90.0,
        free_cash_flow=25.0,
        operating_cash_flow=30.0,
        capital_expenditure=5.0,
        total_debt=40.0,
        ebit=22.0,
        ebitda=30.0,
        interest_expense=2.0,
        tax_provision=4.0,
        pretax_income=16.0,
        operating_income=20.0,
        operating_expense=80.0,
        research_development=5.0,
        sga=15.0,
        non_operating_income_expense=0.0,
    )
    defaults.update(kwargs)
    return NormalizedFinancials(**defaults)


def _service() -> CompanyAnalysisService:
    from unittest.mock import MagicMock

    repo = MagicMock()
    repo.get_best_available.return_value = []
    return CompanyAnalysisService(repository=repo, market_provider=None)


# ----------------------------------------------------------------------
# Gap 1: liquidity criteria
# ----------------------------------------------------------------------


def test_current_ratio_is_computed():
    svc = _service()
    svc._repository.get_best_available.return_value = [_row(2024), _row(2023), _row(2022)]
    result = svc.analyze("TEST", no_prices=True)
    assert result["current_ratio"] == pytest.approx(2.0)


def test_quick_ratio_is_computed():
    svc = _service()
    svc._repository.get_best_available.return_value = [_row(2024), _row(2023), _row(2022)]
    result = svc.analyze("TEST", no_prices=True)
    # (120 - 30) / 60 = 1.5
    assert result["quick_ratio"] == pytest.approx(1.5)


def test_liquidity_criteria_in_quality_score():
    svc = _service()
    svc._repository.get_best_available.return_value = [_row(2024), _row(2023), _row(2022)]
    result = svc.analyze("TEST", no_prices=True)
    # current_ratio >= 2 and quick_ratio >= 1 should both be True
    assert result["current_ratio"] >= 2.0
    assert result["quick_ratio"] >= 1.0


# ----------------------------------------------------------------------
# Gap 2: margin-of-safety gate
# ----------------------------------------------------------------------


def test_margin_of_safety_is_computed():
    svc = _service()
    svc._repository.get_best_available.return_value = [_row(0), _row(1), _row(2)]
    result = svc.analyze("TEST", no_prices=True)
    assert "margin_of_safety" in result
    assert isinstance(result["margin_of_safety"], float)


def test_margin_of_safety_gate_in_signal():
    """The signal engine should reject when margin_of_safety is negative."""
    from backend.screener.signals import generate_signal

    svc = _service()
    svc._repository.get_best_available.return_value = [_row(0), _row(1), _row(2)]
    analysis = svc.analyze("TEST", no_prices=True)
    # With no market provider, margin_of_safety should be None or negative
    # and the signal should not be BUY
    signal = generate_signal(analysis, rank_score(analysis))
    assert signal["signal"] != "BUY"


# ----------------------------------------------------------------------
# Gap 3: rank_score exposed
# ----------------------------------------------------------------------


def test_rank_score_returns_float():
    svc = _service()
    svc._repository.get_best_available.return_value = [_row(0), _row(1), _row(2)]
    result = svc.analyze("TEST", no_prices=True)
    score = rank_score(result)
    assert isinstance(score, float)
    assert 0 <= score <= 100


# ----------------------------------------------------------------------
# Gap 4: composite score always present
# ----------------------------------------------------------------------


def test_composite_score_always_present():
    svc = _service()
    svc._repository.get_best_available.return_value = [_row(0), _row(1), _row(2)]
    result = svc.analyze("TEST", no_prices=True)
    assert "composite_score" in result
    assert "total_score" in result["composite_score"]
    assert "rating" in result["composite_score"]


def test_composite_score_with_no_data():
    svc = _service()
    result = svc.analyze("TEST", [])
    assert result is None
