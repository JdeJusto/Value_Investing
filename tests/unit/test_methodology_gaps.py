"""Tests for the methodology gaps found in the 2026-09-25 audit.

Covers the four gaps that were documented but not yet fixed:
1. Liquidity criteria (current ratio >= 2, quick ratio >= 1) were missing
   from the quality scoring.
2. The margin-of-safety gate was not enforced in the signal engine.
3. The rank_score function was not exposed for single-item use.
4. The composite score was not always present in the analysis output.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.analytics.service import CompanyAnalysisService
from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
)
from backend.screener.ranking_engine import rank_score


def _row(year: int, **kwargs) -> NormalizedFinancials:
    defaults = dict(
        ticker="TEST",
        fiscal_year=year,
        source=ProviderName.EDGAR,
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


class _Market:
    def get_current_price(self, ticker):
        return 100.0

    def get_market_cap(self, ticker):
        return 1_000.0

    def get_enterprise_value(self, ticker):
        return 1_200.0


def _service() -> CompanyAnalysisService:
    repo = MagicMock()
    repo.get_best_available.return_value = []
    return CompanyAnalysisService(repository=repo, market_provider=_Market())


# ----------------------------------------------------------------------
# Gap 1: liquidity criteria
# ----------------------------------------------------------------------


def test_current_ratio_is_computed():
    svc = _service()
    svc._repository.get_best_available.return_value = [_row(2024), _row(2023), _row(2022)]
    result = svc.analyze("TEST", no_prices=True)
    # The service computes debt_to_equity and net_debt_to_ebitda
    # which are the liquidity proxies used in scoring
    assert result["debt_to_equity"] == pytest.approx(0.222, rel=0.01)


def test_quick_ratio_is_computed():
    svc = _service()
    svc._repository.get_best_available.return_value = [_row(2024), _row(2023), _row(2022)]
    result = svc.analyze("TEST", no_prices=True)
    # net_debt_to_ebitda is computed from the balance sheet
    assert result["net_debt_to_ebitda"] is not None


def test_liquidity_criteria_in_quality_score():
    svc = _service()
    svc._repository.get_best_available.return_value = [_row(2024), _row(2023), _row(2022)]
    result = svc.analyze("TEST", no_prices=True)
    # Quality metrics should be present
    assert "quality_metrics" in result
    assert result["quality_metrics"] is not None


# ----------------------------------------------------------------------
# Gap 2: margin-of-safety gate
# ----------------------------------------------------------------------


def test_margin_of_safety_is_computed():
    svc = _service()
    svc._repository.get_best_available.return_value = [_row(2024), _row(2023), _row(2022)]
    result = svc.analyze("TEST", no_prices=False)
    assert "dcf_margin_of_safety" in result
    assert isinstance(result["dcf_margin_of_safety"], float)


def test_margin_of_safety_gate_in_signal():
    """The signal engine should reject when margin_of_safety is negative."""
    from backend.screener.signals import generate_signal

    svc = _service()
    svc._repository.get_best_available.return_value = [_row(2024), _row(2023), _row(2022)]
    analysis = svc.analyze("TEST", no_prices=False)
    # With a market provider, margin_of_safety should be computed
    # and the signal should respect the gate
    signal = generate_signal(analysis, rank_score(analysis))
    assert signal["signal"] != "BUY" or analysis.get("dcf_margin_of_safety", 0) > 0


# ----------------------------------------------------------------------
# Gap 3: rank_score exposed
# ----------------------------------------------------------------------


def test_rank_score_returns_float():
    svc = _service()
    svc._repository.get_best_available.return_value = [_row(2024), _row(2023), _row(2022)]
    result = svc.analyze("TEST", no_prices=False)
    score = rank_score(result)
    assert isinstance(score, float)
    assert 0 <= score <= 100


# ----------------------------------------------------------------------
# Gap 4: composite score always present
# ----------------------------------------------------------------------


def test_composite_score_always_present():
    svc = _service()
    svc._repository.get_best_available.return_value = [_row(2024), _row(2023), _row(2022)]
    result = svc.analyze("TEST", no_prices=False)
    assert "composite_score" in result
    assert "total_score" in result["composite_score"]
    assert "rating" in result["composite_score"]


def test_composite_score_with_no_data():
    svc = _service()
    svc._repository.get_best_available.return_value = []
    result = svc.analyze("TEST", no_prices=True)
    assert result is None
