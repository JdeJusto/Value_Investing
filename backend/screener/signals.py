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

    return {"signal": signal, "confidence": confidence, "reason": reasons}


def can_buy(rank: float, buffett: Optional[float], confidence: str) -> bool:
    """Compatibility helper: does this company pass the BUY bar?"""
    if buffett is None or buffett < 50:
        return False
    if confidence not in ("HIGH", "MEDIUM"):
        return False
    return rank >= CONFIDENCE_RANK_THRESHOLD.get(confidence, 75.0)
