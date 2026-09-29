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
    base = dict(  # noqa: C408 — kwargs form mirrors the financial fields
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


def test_revenue_cagr_none_with_negative_latest_revenue():
    """A negative latest-year revenue must not produce a complex CAGR.

    Regression: ``(-ratio) ** (1 / years)`` yields a Python complex, which
    then breaks downstream comparisons (HBNC surfaced this in the daily
    universe run with a -26.9M latest-year revenue).
    """
    rows = _history(range(2020, 2024))
    rows[-1].revenue = -1_000_000
    assert revenue_cagr(rows) is None


def test_earnings_cv_reflects_volatility():
    stable = _history(range(2020, 2025))
    stable_cv = earnings_cv(stable)
    assert stable_cv is not None and stable_cv < 0.25
    rows = []
    for i, r in enumerate(_history(range(2020, 2025))):
        r.net_income = r.net_income * (10 if i % 2 == 0 else 0.1)
        rows.append(r)
    assert earnings_cv(rows) > stable_cv


def test_compute_quality_metrics_empty_history_never_crashes():
    """Regression: an empty history used to raise IndexError on
    ``ordered_asc(rows)[-1]`` (reachable when every row of a company is
    filtered out). Every metric must come back as None."""
    metrics = compute_quality_metrics([])
    assert metrics == {
        "roic_mean": None,
        "roic_strong_years": None,
        "roe_mean": None,
        "book_value_per_share": None,
        "owner_earnings": None,
        "earnings_cv": None,
        "max_yoy_decline": None,
        "revenue_cagr": None,
        "revenue_cv": None,
        "gross_margin_mean": None,
        "gross_margin_cv": None,
        "gross_margin_trend": None,
        "capital_intensity": None,
        "positive_fcf_ratio": None,
        "fcf_growth": None,
        "debt_to_equity": None,
        "interest_coverage": None,
        "debt_trend": None,
        "net_income_change": None,
        "retained_earnings_positive": None,
    }


def test_fcf_growth_requires_three_years():
    """With exactly two FCF years the first/last windows are the same pair,
    which used to return a trivial, misleading 0.0. "No trend" is None."""
    two = _history(range(2023, 2025))
    assert all(r.free_cash_flow is not None for r in two)
    metrics = compute_quality_metrics(two)
    assert metrics["fcf_growth"] is None


def test_analyze_moat_empty_history_returns_none_type():
    """An empty history must yield a NONE moat, not crash."""
    result = analyze_moat([])
    assert result["moat_type"] == "NONE"
    assert result["moat_score"] == 0.0


def test_analyze_moat_tolerates_partial_metrics_dict():
    """A caller-supplied partial metrics dict must not raise KeyError."""
    result = analyze_moat(_history(range(2020, 2025)), metrics={})
    assert result["moat_type"] == "NONE"
    assert result["moat_score"] == 0.0


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
        "delta_metrics",
        "anomalies",
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


# ----------------------------------------------------------------------
# Delta metrics (fundamental momentum)
# ----------------------------------------------------------------------
def _row(year, revenue, cogs_pct, ebit_pct, fcf, **overrides):
    row = NormalizedFinancials(
        ticker="TEST",
        fiscal_year=year,
        revenue=revenue,
        cogs=revenue * cogs_pct,
        gross_profit=revenue * (1 - cogs_pct),
        operating_income=revenue * ebit_pct,
        ebit=revenue * ebit_pct,
        ebitda=revenue * (ebit_pct + 0.05),
        net_income=revenue * 0.20,
        interest_expense=revenue * 0.02,
        tax_provision=revenue * 0.05,
        pretax_income=revenue * 0.25,
        total_assets=revenue * 2.0,
        total_liabilities=revenue * 0.75,
        total_debt=revenue * 0.40,
        cash_and_equivalents=revenue * 0.10,
        working_capital=revenue * 0.20,
        retained_earnings=revenue * 1.5,
        stockholders_equity=revenue * 1.0,
        operating_cash_flow=fcf + revenue * 0.05,
        capital_expenditure=revenue * 0.05,
        free_cash_flow=fcf,
        depreciation_amortization=revenue * 0.05,
        shares_outstanding=1_000_000,
        source=ProviderName.YAHOO,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def _accelerating_history():
    """Growth 10% -> 10% -> 20%, margin expansion and ROIC improvement."""
    return [
        _row(2021, 1_000_000, 0.60, 0.30, 120_000),
        _row(2022, 1_100_000, 0.60, 0.30, 145_000),
        _row(2023, 1_210_000, 0.60, 0.30, 165_000),
        _row(2024, 1_452_000, 0.55, 0.35, 220_000),
    ]


def test_delta_metrics_capture_acceleration():
    from backend.intelligence.delta_metrics import compute_delta_metrics

    deltas = compute_delta_metrics(_accelerating_history())
    assert deltas["revenue_growth_last"] == pytest.approx(0.20, abs=0.001)
    assert deltas["revenue_growth_prev"] == pytest.approx(0.10, abs=0.001)
    assert deltas["revenue_growth_delta"] == pytest.approx(0.10, abs=0.002)
    assert deltas["gross_margin_delta"] == pytest.approx(0.05, abs=0.001)
    assert deltas["roic_delta"] > 0.01
    assert deltas["fcf_delta"] == pytest.approx((220_000 - 165_000) / 165_000)


def test_delta_metrics_require_history():
    from backend.intelligence.delta_metrics import compute_delta_metrics

    deltas = compute_delta_metrics([_row(2024, 1_000_000, 0.6, 0.3, 100_000)])
    assert all(v is None for v in deltas.values())


def test_delta_metrics_capture_deterioration():
    from backend.intelligence.delta_metrics import compute_delta_metrics

    history = [
        _row(2021, 1_000_000, 0.55, 0.32, 150_000),
        _row(2022, 1_100_000, 0.58, 0.30, 140_000),
        _row(2023, 1_200_000, 0.62, 0.26, 110_000),
        _row(2024, 1_250_000, 0.66, 0.22, 80_000),
    ]
    deltas = compute_delta_metrics(history)
    assert deltas["gross_margin_delta"] < 0
    assert deltas["roic_delta"] < 0
    assert deltas["fcf_delta"] < 0
    assert deltas["revenue_growth_delta"] < 0


# ----------------------------------------------------------------------
# Anomaly detection
# ----------------------------------------------------------------------
def test_anomaly_detection_flags_last_year_spike():
    from backend.intelligence.anomaly_detection import detect_anomalies

    rows = [
        _row(2020 + i, r, 0.60, 0.30, 100_000)
        for i, r in enumerate((1_000_000, 1_050_000, 1_030_000, 990_000, 2_100_000))
    ]
    anomalies = detect_anomalies(rows)
    revenue_flags = [a for a in anomalies if a["metric"] == "revenue"]
    assert revenue_flags
    strongest = revenue_flags[0]
    assert strongest["direction"] == "UP"
    assert strongest["zscore"] > 5
    assert strongest["severity"] == "STRONG"


def test_anomaly_detection_clean_history_has_no_flags():
    from backend.intelligence.anomaly_detection import detect_anomalies

    rows = [
        _row(2020 + i, r, 0.60, 0.30, 100_000)
        for i, r in enumerate((1_000_000, 1_050_000, 1_030_000, 990_000, 1_040_000))
    ]
    assert detect_anomalies(rows) == []


def test_anomaly_detection_flags_abnormal_jump():
    from backend.intelligence.anomaly_detection import detect_anomalies

    rows = [
        _row(2020 + i, r, 0.60, 0.30, 100_000)
        for i, r in enumerate((1_000_000, 1_020_000, 1_040_000, 1_030_000, 1_650_000))
    ]
    anomalies = detect_anomalies(rows)
    jumps = [a for a in anomalies if a["type"] == "yoy_jump"]
    assert jumps
    assert jumps[0]["metric"] == "revenue"
    assert jumps[0]["direction"] == "UP"
    assert jumps[0]["change"] == pytest.approx(0.60, abs=0.01)


def test_anomaly_detection_zscore_requires_baseline():
    from backend.intelligence.anomaly_detection import detect_anomalies

    rows = [
        _row(2023, 1_000_000, 0.60, 0.30, 100_000),
        _row(2024, 2_000_000, 0.60, 0.30, 200_000),
    ]
    anomalies = detect_anomalies(rows)
    assert anomalies  # yoy_jump does not need a baseline
    assert all(a["type"] == "yoy_jump" for a in anomalies)
