"""Ranking engine: beyond the composite score.

The rank score blends the composite quality score with the valuation
gap (margin of safety), growth quality, earnings stability, fundamental
momentum and the confidence in the underlying data. Every factor is
documented and deterministic; the weights sum to 1.0.
"""

COMPOSITE_WEIGHT = 0.55
MARGIN_WEIGHT = 0.20
GROWTH_WEIGHT = 0.05
STABILITY_WEIGHT = 0.05
MOMENTUM_WEIGHT = 0.10
CONFIDENCE_WEIGHT = 0.05

MARGIN_SATURATION = 0.40  # margin of safety above this is fully rewarded
CONFIDENCE_VALUE = {"LOW": 0.25, "MEDIUM": 0.5, "HIGH": 1.0}

# Momentum deltas (raw fractions) that count as a full positive/negative signal
MOMENTUM_REV_DELTA_GOOD = 0.02
MOMENTUM_REV_DELTA_BAD = -0.02
MOMENTUM_MARGIN_DELTA_GOOD = 0.015
MOMENTUM_MARGIN_DELTA_BAD = -0.015
MOMENTUM_ROIC_DELTA_GOOD = 0.03
MOMENTUM_ROIC_DELTA_BAD = -0.03
MOMENTUM_FCF_DELTA_GOOD = 0.20
MOMENTUM_FCF_DELTA_BAD = -0.20


def _total_score(item: dict) -> float:
    return (item.get("composite_score") or {}).get("total_score") or 0.0


def margin_of_safety_score(item: dict) -> float:
    """Valuation gap normalized to [0, 1]."""
    margin = item.get("dcf_margin_of_safety")
    if margin is None or margin <= 0:
        return 0.0
    if margin >= MARGIN_SATURATION:
        return 1.0
    return margin / MARGIN_SATURATION


def growth_quality_score(item: dict) -> float:
    """Growth quality from the Buffett pillars (cash generation + profitability)."""
    breakdown = item.get("buffett_breakdown") or {}
    cash = breakdown.get("cash_generation") or 0.0
    profitability = breakdown.get("profitability") or 0.0
    return (0.5 * cash + 0.5 * profitability) / 100.0


def stability_bonus(item: dict) -> float:
    """Earnings stability pillar normalized to [0, 1]."""
    breakdown = item.get("buffett_breakdown") or {}
    return (breakdown.get("stability") or 0.0) / 100.0


def confidence_factor(item: dict) -> float:
    """Data confidence multiplier in [0.25, 1.0]."""
    confidence = (item.get("composite_score") or {}).get("confidence")
    return CONFIDENCE_VALUE.get(confidence, 0.25)


def _clip_signal(value, good: float, bad: float) -> float:
    """Linear signal in [0, 1]: fully positive at ``good``, negative at ``bad``."""
    if value is None:
        return 0.5  # neutral when there is no delta data
    if abs(good - bad) < 1e-12:
        return 1.0 if value >= good else 0.0
    low, high = min(good, bad), max(good, bad)
    clamped = min(max(value, low), high)
    return (clamped - low) / (high - low)


def fundamental_momentum(item: dict) -> float:
    """Momentum in [0, 1] from revenue, margin, ROIC and FCF deltas."""
    deltas = item.get("delta_metrics") or {}
    signals = [
        _clip_signal(
            deltas.get("revenue_growth_delta"),
            MOMENTUM_REV_DELTA_GOOD,
            MOMENTUM_REV_DELTA_BAD,
        ),
        _clip_signal(
            deltas.get("gross_margin_delta"),
            MOMENTUM_MARGIN_DELTA_GOOD,
            MOMENTUM_MARGIN_DELTA_BAD,
        ),
        _clip_signal(
            deltas.get("roic_delta"), MOMENTUM_ROIC_DELTA_GOOD, MOMENTUM_ROIC_DELTA_BAD
        ),
        _clip_signal(
            deltas.get("fcf_delta"), MOMENTUM_FCF_DELTA_GOOD, MOMENTUM_FCF_DELTA_BAD
        ),
    ]
    return sum(signals) / len(signals)


def momentum_reasons(item: dict) -> list[str]:
    """Explain the strongest momentum moves."""
    deltas = item.get("delta_metrics") or {}
    reasons: list[str] = []
    if (v := deltas.get("revenue_growth_delta")) is not None:
        if v >= 0.02:
            reasons.append(f"revenue growth accelerating by {v*100:.1f}pp")
        elif v <= -0.02:
            reasons.append(f"revenue growth slowing by {abs(v)*100:.1f}pp")
    if (v := deltas.get("gross_margin_delta")) is not None:
        if v >= 0.015:
            reasons.append(f"gross margin expanding by {v*100:.1f}pp")
        elif v <= -0.015:
            reasons.append(f"gross margin compressing by {abs(v)*100:.1f}pp")
    if (v := deltas.get("roic_delta")) is not None:
        if v >= 0.03:
            reasons.append(f"ROIC improving by {v*100:.1f}pp")
        elif v <= -0.03:
            reasons.append(f"ROIC deteriorating by {abs(v)*100:.1f}pp")
    if (v := deltas.get("fcf_delta")) is not None:
        if v >= 0.20:
            reasons.append(f"FCF surging {v*100:.0f}%")
        elif v <= -0.20:
            reasons.append(f"FCF declining {abs(v)*100:.0f}%")
    return reasons


def momentum_factor(item: dict) -> float:
    """Public alias: momentum score in [0, 100]."""
    return fundamental_momentum(item) * 100.0


def rank_score(item: dict) -> float:
    """Weighted blend producing the final ranking score (0-100)."""
    base = _total_score(item)
    composite_part = COMPOSITE_WEIGHT * base
    margin_part = MARGIN_WEIGHT * margin_of_safety_score(item) * 100.0
    growth_part = GROWTH_WEIGHT * growth_quality_score(item) * 100.0
    stability_part = STABILITY_WEIGHT * stability_bonus(item) * 100.0
    momentum_part = MOMENTUM_WEIGHT * fundamental_momentum(item) * 100.0
    confidence_part = CONFIDENCE_WEIGHT * confidence_factor(item) * 100.0
    return round(
        composite_part
        + margin_part
        + growth_part
        + stability_part
        + momentum_part
        + confidence_part,
        2,
    )


def ranking_reasons(item: dict) -> list[str]:
    """Explain why a company ranks where it does."""
    reasons: list[str] = []

    composite = item.get("composite_score") or {}
    total = composite.get("total_score")
    if total is not None:
        reasons.append(
            f"Composite score of {total:.0f} (rating {composite.get('rating')})"
        )

    margin = item.get("dcf_margin_of_safety")
    if margin is not None and margin > 0:
        reasons.append(f"{margin:.0%} margin of safety vs DCF value")
    elif item.get("dcf_value") is not None:
        reasons.append("trades at or above estimated DCF value")

    breakdown = item.get("buffett_breakdown") or {}
    pillars = sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True)
    if pillars:
        name, value = pillars[0]
        reasons.append(f"strongest pillar: {name.replace('_', ' ')} ({value:.0f}/100)")

    moat = (item.get("moat_analysis") or {}).get("moat_type", "NONE")
    if moat in ("STRONG", "MODERATE"):
        reasons.append(f"{moat.lower()} moat")

    metrics = item.get("quality_metrics") or {}
    roic = metrics.get("roic_mean")
    if roic is not None and roic >= 0.12:
        reasons.append(f"ROIC {roic:.0%} on invested capital")

    return reasons
