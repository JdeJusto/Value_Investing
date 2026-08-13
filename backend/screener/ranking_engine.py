"""Ranking engine: beyond the composite score.

The rank score blends the composite quality score with the valuation
gap (margin of safety), growth quality, earnings stability and the
confidence in the underlying data. Every factor is documented and
deterministic; the weights sum to 1.0.
"""

COMPOSITE_WEIGHT = 0.55
MARGIN_WEIGHT = 0.25
GROWTH_WEIGHT = 0.10
STABILITY_WEIGHT = 0.05
CONFIDENCE_WEIGHT = 0.05

MARGIN_SATURATION = 0.40  # margin of safety above this is fully rewarded
CONFIDENCE_VALUE = {"LOW": 0.25, "MEDIUM": 0.5, "HIGH": 1.0}


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


def rank_score(item: dict) -> float:
    """Weighted blend producing the final ranking score (0-100)."""
    base = _total_score(item)
    composite_part = COMPOSITE_WEIGHT * base
    margin_part = MARGIN_WEIGHT * margin_of_safety_score(item) * 100.0
    growth_part = GROWTH_WEIGHT * growth_quality_score(item) * 100.0
    stability_part = STABILITY_WEIGHT * stability_bonus(item) * 100.0
    confidence_part = CONFIDENCE_WEIGHT * confidence_factor(item) * 100.0
    return round(
        composite_part + margin_part + growth_part + stability_part + confidence_part,
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
