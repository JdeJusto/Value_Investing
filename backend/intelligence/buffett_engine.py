"""Buffett-style deterministic filter over normalized financials.

Four pillars are scored 0-100 from explicit, published thresholds and
combined with fixed weights. Every pillar answer can be traced back to a
single rule, so the filter stays transparent and explainable.
"""

from typing import Optional

# Pillar weights, summing to 1.0
PROFITABILITY_WEIGHT = 0.35
FINANCIAL_STRENGTH_WEIGHT = 0.25
CASH_GENERATION_WEIGHT = 0.25
STABILITY_WEIGHT = 0.15

# Profitability thresholds
ROE_TARGET = 0.15
ROE_FLOOR = 0.05
ROIC_TARGET = 0.12
ROIC_FLOOR = 0.04
GROSS_CV_STABLE = 0.10
GROSS_CV_UNSTABLE = 0.30
ROE_PILLAR_WEIGHT = 0.40
ROIC_PILLAR_WEIGHT = 0.35
MARGIN_PILLAR_WEIGHT = 0.25

# Financial strength thresholds
DEBT_EQUITY_MAX = 1.0
DEBT_EQUITY_EXTREME = 2.5
COVERAGE_MIN = 1.0
COVERAGE_TARGET = 5.0
DEBT_PILLAR_WEIGHT = 0.40
COVERAGE_PILLAR_WEIGHT = 0.40
RETAINED_PILLAR_WEIGHT = 0.20

# Cash generation
FCF_POSITIVE_WEIGHT = 0.60
FCF_GROWTH_WEIGHT = 0.40

# Stability
EARNINGS_CV_STABLE = 0.20
EARNINGS_CV_UNSTABLE = 1.00
DRAWDOWN_MAX = -0.20
CV_PILLAR_WEIGHT = 0.60
DRAWDOWN_PILLAR_WEIGHT = 0.40


def _scale(
    value: Optional[float], good: float, bad: float, invert: bool = False
) -> float:
    """Linear score in [0, 100] between ``good`` (100) and ``bad`` (0)."""
    if value is None or value != value:  # NaN guard
        return 0.0
    if good == bad:
        return 100.0 if value >= good else 0.0
    low, high = min(good, bad), max(good, bad)
    clamped = min(max(value, low), high)
    if invert:
        return 100.0 * (high - clamped) / (high - low)
    return 100.0 * (clamped - low) / (high - low)


# ----------------------------------------------------------------------
def _profitability(metrics: dict) -> float:
    roe_score = _scale(metrics["roe_mean"], ROE_TARGET, ROE_FLOOR)
    roic_score = _scale(metrics["roic_mean"], ROIC_TARGET, ROIC_FLOOR)
    margin_score = _scale(
        metrics["gross_margin_cv"], GROSS_CV_STABLE, GROSS_CV_UNSTABLE, invert=True
    )
    return (
        ROE_PILLAR_WEIGHT * roe_score
        + ROIC_PILLAR_WEIGHT * roic_score
        + MARGIN_PILLAR_WEIGHT * margin_score
    )


def _financial_strength(metrics: dict) -> float:
    debt_score = _scale(
        metrics["debt_to_equity"], DEBT_EQUITY_MAX, DEBT_EQUITY_EXTREME, invert=True
    )
    coverage_score = _scale(metrics["interest_coverage"], COVERAGE_TARGET, COVERAGE_MIN)
    retained_score = 100.0 if metrics["retained_earnings_positive"] else 0.0
    return (
        DEBT_PILLAR_WEIGHT * debt_score
        + COVERAGE_PILLAR_WEIGHT * coverage_score
        + RETAINED_PILLAR_WEIGHT * retained_score
    )


def _cash_generation(metrics: dict) -> float:
    positive = metrics["positive_fcf_ratio"]
    positive_score = positive * 100.0 if positive is not None else 0.0
    growth = metrics["fcf_growth"]
    if growth is None:
        growth_score = 0.0
    elif growth > 0:
        growth_score = 100.0
    elif growth == 0:
        growth_score = 50.0
    else:
        growth_score = 0.0
    return FCF_POSITIVE_WEIGHT * positive_score + FCF_GROWTH_WEIGHT * growth_score


def _stability(metrics: dict) -> float:
    cv_score = _scale(
        metrics["earnings_cv"], EARNINGS_CV_STABLE, EARNINGS_CV_UNSTABLE, invert=True
    )
    decline = metrics["max_yoy_decline"]
    drawdown_score = (
        _scale(decline, 0.0, DRAWDOWN_MAX, invert=False) if decline is not None else 0.0
    )
    return CV_PILLAR_WEIGHT * cv_score + DRAWDOWN_PILLAR_WEIGHT * drawdown_score


# ----------------------------------------------------------------------
def buffett_filter(metrics: dict) -> dict:
    """Score 0-100 with a per-pillar breakdown."""
    pillars = {
        "profitability": round(_profitability(metrics), 2),
        "financial_strength": round(_financial_strength(metrics), 2),
        "cash_generation": round(_cash_generation(metrics), 2),
        "stability": round(_stability(metrics), 2),
    }
    score = round(
        PROFITABILITY_WEIGHT * pillars["profitability"]
        + FINANCIAL_STRENGTH_WEIGHT * pillars["financial_strength"]
        + CASH_GENERATION_WEIGHT * pillars["cash_generation"]
        + STABILITY_WEIGHT * pillars["stability"],
        2,
    )
    return {"score": score, "breakdown": pillars}
