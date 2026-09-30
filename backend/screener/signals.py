"""Actionable signals built from scores, opportunities and confidence.

Signals are deterministic decision labels: BUY, WATCHLIST, HOLD, AVOID.
Confidence always carries the data confidence so a signal is never
stronger than the data it rests on.
"""

BUY_MIN_RANK = 75.0
BUY_MIN_TOTAL = 70.0
# LOW-confidence data needs a materially stronger bar before it can justify
# a BUY: a signal is never stronger than the data it rests on.
BUY_MIN_RANK_LOW = 80.0
BUY_MIN_TOTAL_LOW = 75.0
WATCH_MIN_RANK = 60.0
AVOID_MAX_BUFFETT = 40.0

CONFIDENCE_RANK_THRESHOLD = {"LOW": 65.0, "MEDIUM": 75.0, "HIGH": 75.0}


def _confidence(item: dict) -> str:
    return (item.get("composite_score") or {}).get("confidence", "LOW")


def _opportunity_type(item: dict) -> str | None:
    opportunity = item.get("opportunity")
    if opportunity:
        return opportunity.get("type")
    return None


# ---------------------------------------------------------------------------
# Fundamental improvement triggers (TRIGGER_EVENT).
#
# A trigger fires when the *dominant positive* movement of the latest period
# clears BOTH:
#   1. the absolute floor below, and
#   2. a cross-sectional percentile floor computed over the analyzed
#      universe (see calibrate_trigger_thresholds), so only genuinely
#      standout improvements alert.
# Each improvement must also be persistent (positive in the last two
# consecutive periods where the data permits). Deterioration is deliberately
# NOT surfaced as a TRIGGER_EVENT — SELL_WARNING (score drops) and anomaly
# reporting cover it.
# ---------------------------------------------------------------------------

# Absolute floors: the raw delta must be at least this large to fire.
MARGIN_EXPANSION_FLOOR = 0.02  # gross margin +≥ 2 pp
REVENUE_ACCELERATION_FLOOR = 0.05  # revenue growth-rate acceleration +≥ 5 pp
ROIC_IMPROVEMENT_FLOOR = 0.03  # ROIC +≥ 3 pp
FCF_SURGE_FLOOR = 0.20  # FCF growth +≥ 20%

# Cross-sectional quantile of the (signed) delta across the analyzed
# universe. Effective threshold = max(floor, percentile). Calibrated on the
# 500-company S&P 500 + Nasdaq-100 universe (2026-09): 0.92 keeps roughly the
# top ~8% of standouts per metric and ~10% of the universe firing total,
# which is the advertised alert ceiling.
TRIGGER_QUANTILES = {
    "MARGIN_EXPANSION": 0.92,
    "REVENUE_ACCELERATION": 0.92,
    "ROIC_IMPROVEMENT": 0.92,
    "FCF_SURGE": 0.92,
}

# The delta-metric key behind each positive trigger.
TRIGGER_METRICS = {
    "MARGIN_EXPANSION": "gross_margin_delta",
    "REVENUE_ACCELERATION": "revenue_growth_delta",
    "ROIC_IMPROVEMENT": "roic_delta",
    "FCF_SURGE": "fcf_delta",
}

# An FCF surge only means something when the company actually generates
# positive free cash flow (a loss-to-loss "improvement" is noise).
FCF_SURGE_ITEMS_KEY = "fcf"

CALIBRATION_MIN_SAMPLES = 20  # below this the universe percentile is noise


def _positive_floors() -> dict[str, float]:
    return {
        "MARGIN_EXPANSION": MARGIN_EXPANSION_FLOOR,
        "REVENUE_ACCELERATION": REVENUE_ACCELERATION_FLOOR,
        "ROIC_IMPROVEMENT": ROIC_IMPROVEMENT_FLOOR,
        "FCF_SURGE": FCF_SURGE_FLOOR,
    }


def calibrate_trigger_thresholds(
    analyses,
    min_samples: int = CALIBRATION_MIN_SAMPLES,
) -> dict[str, float]:
    """Cross-sectional trigger floors over an analyzed universe.

    For each positive trigger the percentile of its raw delta across the
    universe clamps the threshold, which never goes below the absolute floor.
    With fewer than ``min_samples`` analyses the universe percentile is
    unreliable and the absolute floors apply on their own.
    Returns ``{TRIGGER: effective_min_delta}``.
    """
    values: dict[str, list[float]] = {trigger: [] for trigger in TRIGGER_METRICS}
    for item in analyses:
        if not item:
            continue
        deltas = item.get("delta_metrics") or {}
        for trigger, metric in TRIGGER_METRICS.items():
            value = deltas.get(metric)
            if value is not None:
                values[trigger].append(value)

    floors = _positive_floors()
    thresholds: dict[str, float] = {}
    for trigger, metric in TRIGGER_METRICS.items():
        vals = sorted(values[trigger])
        if len(vals) >= min_samples:
            quantile = TRIGGER_QUANTILES[trigger]
            index = (len(vals) - 1) * quantile
            lo = int(index)
            hi = min(lo + 1, len(vals) - 1)
            percentile_floor = vals[lo] + (vals[hi] - vals[lo]) * (index - lo)
            thresholds[trigger] = max(percentile_floor, floors[trigger])
        else:
            thresholds[trigger] = floors[trigger]
    return thresholds


def _persisted(deltas: dict, current_key: str, prev_key: str) -> bool:
    """True when the prior period also moved upwards (or we cannot tell).

    The check never blocks a trigger on missing history — if there are fewer
    than three periods the previous delta is None and the current-period
    evidence stands on its own.
    """
    prev = deltas.get(prev_key)
    if prev is None:
        return True
    return prev > 0


def _revenue_persisted(deltas: dict) -> bool:
    """Revenue acceleration needs two consecutive growth periods."""
    last = deltas.get("revenue_growth_last")
    prev = deltas.get("revenue_growth_prev")
    if prev is None:
        return True
    return last is not None and last > 0 and prev > 0


def detect_trigger(item: dict, thresholds: dict | None = None) -> str | None:
    """The dominant *improvement* of the latest period, or None.

    Returns the strongest positive trigger whose delta clears both the
    absolute floor and the (optional) calibrated cross-sectional threshold,
    provided the improvement is persistent. ``thresholds`` is the output of
    :func:`calibrate_trigger_thresholds`; when omitted the absolute floors
    alone apply. Deterioration returns None: it is not a trigger event.
    """
    deltas = item.get("delta_metrics") or {}
    effective = thresholds if thresholds else _positive_floors()
    candidates: list[tuple[float, str]] = []

    margin = deltas.get("gross_margin_delta")
    if (
        margin is not None
        and margin >= effective["MARGIN_EXPANSION"]
        and _persisted(deltas, "gross_margin_delta", "gross_margin_delta_prev")
    ):
        candidates.append((margin, "MARGIN_EXPANSION"))

    rev = deltas.get("revenue_growth_delta")
    if (
        rev is not None
        and rev >= effective["REVENUE_ACCELERATION"]
        and _revenue_persisted(deltas)
    ):
        candidates.append((rev, "REVENUE_ACCELERATION"))

    roic = deltas.get("roic_delta")
    if (
        roic is not None
        and roic >= effective["ROIC_IMPROVEMENT"]
        and _persisted(deltas, "roic_delta", "roic_delta_prev")
    ):
        candidates.append((roic, "ROIC_IMPROVEMENT"))

    fcf = deltas.get("fcf_delta")
    fcf_now = item.get(FCF_SURGE_ITEMS_KEY)
    if (
        fcf is not None
        and fcf >= effective["FCF_SURGE"]
        and fcf_now is not None
        and fcf_now > 0
    ):
        candidates.append((fcf, "FCF_SURGE"))

    if not candidates:
        return None
    return max(candidates, key=lambda pair: pair[0])[1]


def generate_signal(item: dict, rank: float, thresholds: dict | None = None) -> dict:
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
    elif (
        # Confianza LOW: solo se compra con una barra mucho más exigente.
        rank >= BUY_MIN_RANK_LOW
        and (item.get("composite_score") or {}).get("total_score", 0)
        >= BUY_MIN_TOTAL_LOW
        and confidence == "LOW"
        and buffett is not None
        and buffett >= 50
    ):
        signal = "BUY"
        reasons.append(
            f"rank {rank:.1f} and composite above {BUY_MIN_TOTAL_LOW:.0f} "
            "despite LOW-confidence data"
        )
    elif rank >= WATCH_MIN_RANK:
        signal = "WATCHLIST"
        reasons.append(f"rank {rank:.1f} above watch threshold {WATCH_MIN_RANK:.0f}")
    else:
        signal = "HOLD"
        reasons.append(f"rank {rank:.1f} below watch threshold {WATCH_MIN_RANK:.0f}")

    return {
        "signal": signal,
        "confidence": confidence,
        "trigger": detect_trigger(item, thresholds=thresholds),
        "reason": reasons,
    }


def can_buy(rank: float, buffett: float | None, confidence: str) -> bool:
    """Compatibility helper: does this company pass the BUY bar?"""
    if buffett is None or buffett < 50:
        return False
    if confidence == "LOW":
        # LOW-confidence data demands the stronger BUY bar.
        return rank >= BUY_MIN_RANK_LOW
    if confidence not in ("HIGH", "MEDIUM"):
        return False
    return rank >= CONFIDENCE_RANK_THRESHOLD.get(confidence, 75.0)
