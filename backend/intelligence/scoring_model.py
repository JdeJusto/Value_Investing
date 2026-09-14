"""Composite investment scoring: Buffett filter + moat + data quality.

Produces a 0-100 total score, a letter rating, a confidence level and a
list of human-readable insights so every result can be questioned and
understood.
"""

from typing import Optional

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.intelligence.anomaly_detection import detect_anomalies
from backend.intelligence.buffett_engine import buffett_filter
from backend.intelligence.delta_metrics import compute_delta_metrics
from backend.intelligence.moat_analysis import analyze_moat
from backend.intelligence.quality_metrics import compute_quality_metrics

BUFFETT_WEIGHT = 0.50
MOAT_WEIGHT = 0.30
QUALITY_WEIGHT = 0.20

RATING_A = 75.0
RATING_B = 60.0
RATING_C = 45.0

HIGH_QUALITY_THRESHOLD = 0.7
HIGH_COVERAGE_THRESHOLD = 0.8
MEDIUM_COVERAGE_THRESHOLD = 0.5
LOW_QUALITY_THRESHOLD = 0.3


def composite_score(
    buffett_score: float, moat_score: float, data_quality_score: Optional[float]
) -> dict:
    """Weighted total plus letter rating."""
    quality = data_quality_score or 0.0
    total = round(
        BUFFETT_WEIGHT * buffett_score
        + MOAT_WEIGHT * moat_score
        + QUALITY_WEIGHT * quality * 100.0,
        2,
    )
    if total >= RATING_A:
        rating = "A"
    elif total >= RATING_B:
        rating = "B"
    elif total >= RATING_C:
        rating = "C"
    else:
        rating = "D"
    return {"total_score": total, "rating": rating}


def confidence_level(reliability: dict) -> str:
    """Map the data reliability report to a composite confidence level."""
    if reliability.get("data_source_used") == "MIXED":
        return "LOW"
    quality = reliability.get("data_quality_score")
    coverage = reliability.get("data_coverage")
    if quality is None or coverage is None:
        return "MEDIUM"
    if quality >= HIGH_QUALITY_THRESHOLD and coverage >= HIGH_COVERAGE_THRESHOLD:
        return "HIGH"
    if quality < LOW_QUALITY_THRESHOLD or coverage < MEDIUM_COVERAGE_THRESHOLD:
        return "LOW"
    return "MEDIUM"


# ----------------------------------------------------------------------
def generate_insights(metrics: dict, moat: dict) -> list[str]:
    """Turn the underlying metrics into plain-language observations."""
    insights: list[str] = []

    roe = metrics["roe_mean"]
    if roe is not None:
        insights.append(
            f"High sustained ROE above 15% ({roe:.0%} average)"
            if roe >= 0.15
            else f"Return on equity below the 15% target ({roe:.0%} average)"
        )

    roic = metrics["roic_mean"]
    if roic is not None:
        insights.append(
            f"High ROIC sustained over multiple years ({roic:.0%} average)"
            if roic >= 0.12
            else f"ROIC below the 12% threshold ({roic:.0%} average)"
        )

    positive = metrics["positive_fcf_ratio"]
    if positive is not None:
        if positive >= 0.8:
            insights.append("Strong free cash flow generation in most years")
        elif positive <= 0.5:
            insights.append("Free cash flow is weak or inconsistent")

    growth = metrics["fcf_growth"]
    if growth is not None and growth > 0:
        insights.append("Free cash flow shows an upward trend")

    de = metrics["debt_to_equity"]
    coverage = metrics["interest_coverage"]
    if de is not None and coverage is not None:
        if de < 1.0 and coverage > 5.0:
            insights.append("Low debt and high interest coverage")
        elif de is not None and de >= 1.5:
            insights.append("Elevated leverage relative to equity")
    if coverage is not None and coverage < 3.0:
        insights.append("Interest coverage below the comfort zone")

    cv = metrics["gross_margin_cv"]
    if cv is not None and cv <= 0.10:
        insights.append("Stable margins indicate pricing power")

    earnings_cv = metrics["earnings_cv"]
    if earnings_cv is not None and earnings_cv <= 0.30:
        insights.append("Low earnings volatility across the history")

    cagr = metrics["revenue_cagr"]
    if cagr is not None:
        if cagr >= 0.10:
            insights.append(f"Strong revenue growth ({cagr:.0%} CAGR)")
        elif cagr < 0:
            insights.append("Revenue is declining")

    intensity = metrics["capital_intensity"]
    if intensity is not None and intensity >= 0.20:
        insights.append("High capital intensity limits the moat")

    if moat["moat_type"] == "STRONG":
        insights.append("Wide economic moat detected")
    elif moat["moat_type"] in ("WEAK", "NONE"):
        insights.append("Limited competitive moat — pricing power is not evident")

    return insights


# ----------------------------------------------------------------------
def assess_investment(
    rows: list[NormalizedFinancials], reliability: Optional[dict] = None
) -> dict:
    """Full intelligence report for one company history.

    ``reliability`` is the data quality report produced by the analytics
    layer (``data_source_used``, ``data_quality_score``, ``data_coverage``).
    """
    reliability = reliability or {}
    metrics = compute_quality_metrics(rows)
    moat = analyze_moat(rows, metrics)
    filter_result = buffett_filter(metrics)
    composite = composite_score(
        filter_result["score"],
        moat["moat_score"],
        reliability.get("data_quality_score"),
    )
    composite["confidence"] = confidence_level(reliability)

    return {
        "buffett_score": filter_result["score"],
        "buffett_breakdown": filter_result["breakdown"],
        "moat_analysis": moat,
        "composite_score": composite,
        "quality_metrics": metrics,
        "delta_metrics": compute_delta_metrics(rows),
        "anomalies": detect_anomalies(rows),
        "insight": generate_insights(metrics, moat),
    }
