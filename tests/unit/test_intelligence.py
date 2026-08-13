"""Unit tests: Buffett filter, moat analysis and composite scoring.

Uses only mock normalized financials — no providers, no network.
"""

import pytest

from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
)
from backend.intelligence.buffett_engine import buffett_filter
from backend.intelligence.moat_analysis import analyze_moat, classify_moat
from backend.intelligence.quality_metrics import (
    compute_quality_metrics,
    earnings_cv,
    owner_earnings,
    revenue_cagr,
    roic,
)
from backend.intelligence.scoring_model import (
    assess_investment,
    composite_score,
    confidence_level,
    generate_insights,
)


def _make(year: int, **overrides) -> NormalizedFinancials:
    """Quality company profile: 20% ROE, 15%+ ROIC, stable margins, low debt."""
    revenue = 1_000_000 + (year - 2020) * 150_000
    base = dict(
        ticker="KO",
        fiscal_year=year,
        revenue=revenue,
        cogs=revenue * 0.58,
        gross_profit=revenue * 0.42,
        operating_income=revenue * 0.30,
        ebit=revenue * 0.30,
        ebitda=revenue * 0.36,
        net_income=revenue * 0.20,
        interest_expense=revenue * 0.02,
        tax_provision=revenue * 0.07,
        pretax_income=revenue * 0.28,
        total_assets=revenue * 2.0,
        total_liabilities=revenue * 0.75,
        total_debt=revenue * 0.40,
        cash_and_equivalents=revenue * 0.10,
        working_capital=revenue * 0.20,
        retained_earnings=revenue * 1.5,
        stockholders_equity=revenue * 1.0,
        operating_cash_flow=revenue * 0.26,
        capital_expenditure=revenue * 0.06,
        free_cash_flow=revenue * 0.20,
        depreciation_amortization=revenue * 0.06,
        dividends_paid=revenue * 0.05,
        repurchase_of_stock=revenue * 0.03,
        working_capital_change=revenue * 0.01,
        shares_outstanding=1_000_000,
        source=ProviderName.YAHOO,
        data_quality_score=0.9,
    )
    base.update(overrides)
    return NormalizedFinancials(**base)


def _history(years: range, **overrides) -> list[NormalizedFinancials]:
    return [_make(y, **overrides) for y in years]


@pytest.fixture
def strong_history():
    return _history(range(2020, 2025))


# ----------------------------------------------------------------------
# Core quality metrics
# ----------------------------------------------------------------------
def test_roic_uses_proper_nopat_over_invested_capital():
    row = _make(2024)
    nopat = row.ebit * (1 - 0.07 / 0.28)  # effective tax rate 25%
    invested = row.total_debt + row.stockholders_equity - row.cash_and_equivalents
    assert roic(row) == pytest.approx(nopat / invested)


def test_roic_returns_none_when_ebit_missing():
    row = _make(2024, ebit=None)
    assert roic(row) is None


def test_owner_earnings_formula():
    row = _make(2024)
    expected = row.net_income + row.depreciation_amortization - row.capital_expenditure
    assert owner_earnings(row) == pytest.approx(expected)


def test_revenue_cagr_computed_over_full_history(strong_history):
    first, last = strong_history[0].revenue, strong_history[-1].revenue
    assert revenue_cagr(strong_history) == pytest.approx(
        (last / first) ** (1 / (len(strong_history) - 1)) - 1
    )


def test_revenue_cagr_none_with_single_year():
    assert revenue_cagr([_make(2024)]) is None


def test_earnings_cv_reflects_volatility():
    stable = _history(range(2020, 2025))
    stable_cv = earnings_cv(stable)
    assert stable_cv is not None and stable_cv < 0.25
    rows = []
    for i, r in enumerate(_history(range(2020, 2025))):
        r.net_income = r.net_income * (10 if i % 2 == 0 else 0.1)
        rows.append(r)
    assert earnings_cv(rows) > stable_cv


# ----------------------------------------------------------------------
# Buffett filter
# ----------------------------------------------------------------------
def test_buffett_filter_scores_quality_company_high(strong_history):
    metrics = compute_quality_metrics(strong_history)
    result = buffett_filter(metrics)
    assert result["score"] >= 80
    for pillar in (
        "profitability",
        "financial_strength",
        "cash_generation",
        "stability",
    ):
        assert result["breakdown"][pillar] >= 70
        assert 0 <= result["breakdown"][pillar] <= 100


def test_buffett_filter_penalizes_leveraged_loss_maker():
    rows = _history(
        range(2020, 2025),
        net_income=-50_000,
        ebit=-30_000,
        total_debt=4_000_000,
        stockholders_equity=100_000,
        retained_earnings=-200_000,
        free_cash_flow=-80_000,
    )
    metrics = compute_quality_metrics(rows)
    result = buffett_filter(metrics)
    assert result["score"] < 40
    assert result["breakdown"]["financial_strength"] < 30
    assert result["breakdown"]["cash_generation"] < 30


def test_buffett_filter_breakdown_weights_sum_to_one():
    from backend.intelligence import buffett_engine as be

    weights = (
        be.PROFITABILITY_WEIGHT
        + be.FINANCIAL_STRENGTH_WEIGHT
        + be.CASH_GENERATION_WEIGHT
        + be.STABILITY_WEIGHT
    )
    assert weights == pytest.approx(1.0)


# ----------------------------------------------------------------------
# Moat analysis
# ----------------------------------------------------------------------
def test_moat_strong_for_quality_company(strong_history):
    result = analyze_moat(strong_history)
    assert result["moat_score"] >= 70
    assert result["moat_type"] == "STRONG"
    assert result["strengths"]
    assert not result["weaknesses"]


def test_moat_none_for_capital_heavy_volatile_business():
    rows = []
    for i, year in enumerate(range(2020, 2025)):
        revenue = 1_000_000 * (1.6 if i % 2 == 0 else 0.6)
        rows.append(
            _make(
                year,
                revenue=revenue,
                cogs=revenue * (0.75 if i % 2 == 0 else 0.55),
                ebit=revenue * 0.05,
                net_income=revenue * 0.03,
                total_debt=revenue * 1.2,
                stockholders_equity=revenue * 0.4,
                capital_expenditure=revenue * 0.35,
            )
        )
    result = analyze_moat(rows)
    assert result["moat_type"] == "NONE"
    assert result["moat_score"] < 30


def test_moat_classify_thresholds():
    assert classify_moat(80) == "STRONG"
    assert classify_moat(60) == "MODERATE"
    assert classify_moat(40) == "WEAK"
    assert classify_moat(10) == "NONE"


# ----------------------------------------------------------------------
# Composite scoring model
# ----------------------------------------------------------------------
def test_composite_score_rating_and_weights():
    quality = 0.9
    result = composite_score(90, 80, quality)
    expected = round(0.5 * 90 + 0.3 * 80 + 0.2 * quality * 100, 2)
    assert result["total_score"] == pytest.approx(expected)
    assert result["rating"] == "A"
    assert composite_score(10, 10, 0.2)["rating"] == "D"
    assert composite_score(70, 60, 0.6)["rating"] == "B"
    assert composite_score(55, 50, 0.5)["rating"] == "C"


def test_confidence_level_mapping():
    assert (
        confidence_level(
            {
                "data_source_used": "MIXED",
                "data_quality_score": 0.9,
                "data_coverage": 1.0,
            }
        )
        == "LOW"
    )
    assert (
        confidence_level(
            {
                "data_source_used": "YAHOO",
                "data_quality_score": 0.9,
                "data_coverage": 1.0,
            }
        )
        == "HIGH"
    )
    assert (
        confidence_level(
            {
                "data_source_used": "EDGAR",
                "data_quality_score": 0.5,
                "data_coverage": 0.9,
            }
        )
        == "MEDIUM"
    )


def test_insights_are_specific_and_interpretable(strong_history):
    metrics = compute_quality_metrics(strong_history)
    moat = analyze_moat(strong_history, metrics)
    insights = generate_insights(metrics, moat)
    text = " ".join(insights).lower()
    assert "roe" in text
    assert "roic" in text
    assert "free cash flow" in text
    assert len(insights) >= 3


def test_insights_flag_warning_for_weak_profile():
    rows = _history(
        range(2020, 2025),
        net_income=-50_000,
        total_debt=4_000_000,
        stockholders_equity=100_000,
        retained_earnings=-200_000,
    )
    metrics = compute_quality_metrics(rows)
    moat = analyze_moat(rows, metrics)
    insights = generate_insights(metrics, moat)
    assert any("leverage" in i.lower() for i in insights)


# ----------------------------------------------------------------------
# End-to-end facade
# ----------------------------------------------------------------------
def test_assess_investment_reports_full_suite(strong_history):
    reliability = {
        "data_source_used": "YAHOO",
        "data_quality_score": 0.92,
        "data_coverage": 1.0,
    }
    report = assess_investment(strong_history, reliability)
    assert set(report) == {
        "buffett_score",
        "buffett_breakdown",
        "moat_analysis",
        "composite_score",
        "quality_metrics",
        "insight",
    }
    assert report["buffett_score"] >= 80
    assert report["moat_analysis"]["moat_type"] == "STRONG"
    assert report["composite_score"]["rating"] in ("A", "B")
    assert report["composite_score"]["confidence"] == "HIGH"
    assert report["insight"]


def test_assess_investment_without_reliability_defaults():
    report = assess_investment([_make(2024)])
    assert report["composite_score"]["confidence"] == "MEDIUM"
