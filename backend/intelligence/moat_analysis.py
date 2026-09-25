"""Heuristic economic moat detection on normalized financials.

A moat is inferred from observable, persistent advantages: sustained
high ROIC, stable or improving gross margins, low capital intensity and
predictable revenue. All signals are deterministic and interpretable.
"""

from typing import Optional

from backend.domain.value_objects.financials_normalized import NormalizedFinancials

STRONG_THRESHOLD = 70.0
MODERATE_THRESHOLD = 50.0
WEAK_THRESHOLD = 30.0

ROIC_STRONG = 0.12
ROIC_FLOOR = 0.06
ROIC_STREAK = 0.10

GROSS_CV_STABLE = 0.08
GROSS_CV_UNSTABLE = 0.25
GROSS_TREND_BONUS = -0.005

CAPEX_LOW = 0.10
CAPEX_HIGH = 0.25

REVENUE_CV_STABLE = 0.15
REVENUE_CV_UNSTABLE = 0.40

# Weights of the moat score, summing to 1.0
ROIC_WEIGHT = 0.40
MARGIN_WEIGHT = 0.25
CAPEX_WEIGHT = 0.20
REVENUE_WEIGHT = 0.15


def _scale(value: Optional[float], good: float, bad: float) -> float:
    """Linear score in [0, 1]: 1.0 at ``good``, 0.0 at ``bad``."""
    if value is None:
        return 0.0
    if good == bad:
        return 1.0 if value >= good else 0.0
    clamped = min(max(value, min(good, bad)), max(good, bad))
    return (clamped - bad) / (good - bad)


def roic_persistence(metrics: dict) -> float:
    """Sustained high ROIC: strength of the average plus how often it stays high."""
    mean_score = _scale(metrics.get("roic_mean"), ROIC_STRONG, ROIC_FLOOR)
    streak = metrics.get("roic_strong_years") or 0.0
    return 0.7 * mean_score + 0.3 * streak


def margin_signal(metrics: dict) -> float:
    """Stable or increasing gross margins indicate pricing power."""
    cv_score = _scale(
        metrics.get("gross_margin_cv"), GROSS_CV_STABLE, GROSS_CV_UNSTABLE
    )
    trend = metrics.get("gross_margin_trend")
    bonus = 0.2 if trend is not None and trend >= GROSS_TREND_BONUS else 0.0
    return min(1.0, cv_score + bonus)


def capital_signal(metrics: dict) -> float:
    """Low capital intensity: a moat lets a business grow without heavy capex."""
    return _scale(metrics.get("capital_intensity"), CAPEX_LOW, CAPEX_HIGH)


def revenue_signal(metrics: dict) -> float:
    """Predictable revenue: low volatility supports durable returns."""
    return _scale(metrics.get("revenue_cv"), REVENUE_CV_STABLE, REVENUE_CV_UNSTABLE)


def classify_moat(moat_score: float) -> str:
    if moat_score >= STRONG_THRESHOLD:
        return "STRONG"
    if moat_score >= MODERATE_THRESHOLD:
        return "MODERATE"
    if moat_score >= WEAK_THRESHOLD:
        return "WEAK"
    return "NONE"


def analyze_moat(
    rows: list[NormalizedFinancials],
    metrics: Optional[dict] = None,
) -> dict:
    """Evaluate the moat for a company history.

    ``metrics`` may be precomputed via ``compute_quality_metrics`` to
    avoid duplicate work; it is recomputed otherwise.
    """
    if metrics is None:
        from backend.intelligence.quality_metrics import compute_quality_metrics

        metrics = compute_quality_metrics(rows)

    signals = {
        "roic_persistence": roic_persistence(metrics),
        "margin_stability": margin_signal(metrics),
        "low_capital_intensity": capital_signal(metrics),
        "revenue_predictability": revenue_signal(metrics),
    }

    moat_score = round(
        100.0
        * (
            ROIC_WEIGHT * signals["roic_persistence"]
            + MARGIN_WEIGHT * signals["margin_stability"]
            + CAPEX_WEIGHT * signals["low_capital_intensity"]
            + REVENUE_WEIGHT * signals["revenue_predictability"]
        ),
        2,
    )

    strengths: list[str] = []
    weaknesses: list[str] = []
    if metrics.get("roic_mean") is not None and metrics.get("roic_mean") >= ROIC_STRONG:
        strengths.append("ROIC persistently above 12%")
    if metrics.get("gross_margin_cv") is not None:
        if metrics["gross_margin_cv"] <= GROSS_CV_STABLE:
            strengths.append("Gross margins stable or improving")
        elif metrics["gross_margin_cv"] >= GROSS_CV_UNSTABLE:
            weaknesses.append("Gross margins volatile")
    if metrics.get("capital_intensity") is not None:
        if metrics["capital_intensity"] <= CAPEX_LOW:
            strengths.append("Low capital intensity")
        elif metrics["capital_intensity"] >= CAPEX_HIGH:
            weaknesses.append("High capital intensity")
    if (
        metrics.get("revenue_cv") is not None
        and metrics["revenue_cv"] >= REVENUE_CV_UNSTABLE
    ):
        weaknesses.append("Revenue predictability is low")

    return {
        "moat_score": moat_score,
        "moat_type": classify_moat(moat_score),
        "signals": signals,
        "strengths": strengths,
        "weaknesses": weaknesses,
    }
