"""Actionable signals built from scores, opportunities and confidence.

Signals are deterministic decision labels: BUY, WATCHLIST, HOLD, AVOID.
Confidence always carries the data confidence so a signal is never
stronger than the data it rests on.
"""

from typing import Optional

BUY_MIN_RANK = 75.0
BUY_MIN_TOTAL = 70.0
WATCH_MIN_RANK = 60.0
AVOID_MAX_BUFFETT = 40.0

CONFIDENCE_RANK_THRESHOLD = {"LOW": 65.0, "MEDIUM": 75.0, "HIGH": 75.0}


def _confidence(item: dict) -> str:
    return (item.get("composite_score") or {}).get("confidence", "LOW")


def _opportunity_type(item: dict) -> Optional[str]:
    opportunity = item.get("opportunity")
    if opportunity:
        return opportunity.get("type")
    return None


# Trigger thresholds (raw deltas); the strongest positive delta wins
MARGIN_EXPANSION_TRIGGER = 0.01
REVENUE_ACCELERATION_TRIGGER = 0.015
ROIC_IMPROVEMENT_TRIGGER = 0.02
FCF_SURGE_TRIGGER = 0.20


def detect_trigger(item: dict) -> Optional[str]:
    """The dominant fundamental movement of the latest period.

    Returns the strongest positive trigger, or the strongest negative
    one when every delta is deteriorating. None when there is no data.
    """
    deltas = item.get("delta_metrics") or {}
    positive: list[tuple[float, str]] = []
    negative: list[tuple[float, str]] = []

    margin = deltas.get("gross_margin_delta")
    if margin is not None:
        (positive if margin >= 0 else negative).append(
            (margin, "MARGIN_EXPANSION" if margin >= 0 else "MARGIN_COMPRESSION")
        )
    rev = deltas.get("revenue_growth_delta")
    if rev is not None:
        (positive if rev >= 0 else negative).append(
            (rev, "REVENUE_ACCELERATION" if rev >= 0 else "REVENUE_DECELERATION")
        )
    roic = deltas.get("roic_delta")
    if roic is not None:
        (positive if roic >= 0 else negative).append(
            (roic, "ROIC_IMPROVEMENT" if roic >= 0 else "ROIC_DETERIORATION")
        )
    fcf = deltas.get("fcf_delta")
    if fcf is not None:
        (positive if fcf >= 0 else negative).append(
            (fcf, "FCF_SURGE" if fcf >= 0 else "FCF_DECLINE")
        )

    qualifying_positive = [
        (value, trigger)
        for value, trigger in positive
        if value
        >= {
            "MARGIN_EXPANSION": MARGIN_EXPANSION_TRIGGER,
            "REVENUE_ACCELERATION": REVENUE_ACCELERATION_TRIGGER,
            "ROIC_IMPROVEMENT": ROIC_IMPROVEMENT_TRIGGER,
            "FCF_SURGE": FCF_SURGE_TRIGGER,
        }[trigger]
    ]
    if qualifying_positive:
        return max(qualifying_positive, key=lambda pair: pair[0])[1]
    qualifying_negative = [pair for pair in negative if pair[0] < 0]
    if qualifying_negative:
        return min(qualifying_negative, key=lambda pair: pair[0])[1]
    return None


def generate_signal(item: dict, rank: float) -> dict:
    """Assign a BUY / WATCHLIST / HOLD / AVOID label and its reasons."""
    buffett = item.get("buffett_score")
    confidence = _confidence(item)

    reasons: list[str] = []
    is_opportunity = _opportunity_type(item) is not None

    if buffett is not None and buffett < AVOID_MAX_BUFFETT:
        signal = "AVOID"
        reasons.append(f"Buffett score {buffett:.0f} below {AVOID_MAX_BUFFETT:.0f}")
    elif (
        is_opportunity
        and rank >= BUY_MIN_RANK
        and buffett is not None
        and buffett >= 50
        and confidence in ("HIGH", "MEDIUM")
    ):
        signal = "BUY"
        reasons.append(f"opportunity detected: {_opportunity_type(item)}")
        reasons.append(f"rank {rank:.1f} above BUY threshold {BUY_MIN_RANK:.0f}")
    elif (
        rank >= BUY_MIN_RANK
        and (item.get("composite_score") or {}).get("total_score", 0) >= BUY_MIN_TOTAL
        and confidence in ("HIGH", "MEDIUM")
    ):
        signal = "BUY"
        reasons.append(f"rank {rank:.1f} with composite above {BUY_MIN_TOTAL:.0f}")
    elif rank >= WATCH_MIN_RANK:
        signal = "WATCHLIST"
        reasons.append(f"rank {rank:.1f} above watch threshold {WATCH_MIN_RANK:.0f}")
    else:
        signal = "HOLD"
        reasons.append(f"rank {rank:.1f} below watch threshold {WATCH_MIN_RANK:.0f}")

    return {
        "signal": signal,
        "confidence": confidence,
        "trigger": detect_trigger(item),
        "reason": reasons,
    }


def can_buy(rank: float, buffett: Optional[float], confidence: str) -> bool:
    """Compatibility helper: does this company pass the BUY bar?"""
    if buffett is None or buffett < 50:
        return False
    if confidence not in ("HIGH", "MEDIUM"):
        return False
    return rank >= CONFIDENCE_RANK_THRESHOLD.get(confidence, 75.0)
