"""Alert rules: human triggers, sell warnings and score helpers."""

from typing import Optional

from backend.screener.signals import detect_trigger

# SELL_WARNING: score drop thresholds, in points of total_score (0-100)
SELL_WARNING_MIN_DROP = 10.0
SELL_WARNING_HIGH_DROP = 15.0

TRIGGER_LABELS = {
    "MARGIN_EXPANSION": "expansion de margen bruto",
    "MARGIN_COMPRESSION": "compresion de margen bruto",
    "REVENUE_ACCELERATION": "aceleracion de ingresos",
    "REVENUE_DECELERATION": "desaceleracion de ingresos",
    "ROIC_IMPROVEMENT": "mejora de ROIC",
    "ROIC_DETERIORATION": "deterioro de ROIC",
    "FCF_SURGE": "salto de free cash flow",
    "FCF_DECLINE": "caida de free cash flow",
}

BUY_SIGNAL = "BUY_SIGNAL"
SELL_WARNING = "SELL_WARNING"
TRIGGER_EVENT = "TRIGGER_EVENT"


def composite_score(item: Optional[dict]) -> Optional[float]:
    """The overall 0-100 score, or None when absent."""
    if not item:
        return None
    return (item.get("composite_score") or {}).get("total_score")


def confidence_of(item: Optional[dict]) -> str:
    if not item:
        return "LOW"
    return (item.get("composite_score") or {}).get("confidence", "LOW")


def trigger_label(trigger: Optional[str]) -> Optional[str]:
    if trigger is None:
        return None
    return TRIGGER_LABELS.get(trigger, trigger.replace("_", " ").lower())


def sell_warning_score_drop(previous: float, current: float) -> Optional[float]:
    """Drop in total score; None when the score did not fall enough."""
    drop = previous - current
    if drop < SELL_WARNING_MIN_DROP:
        return None
    return drop


def sell_warning_confidence(drop: float) -> str:
    if drop >= SELL_WARNING_HIGH_DROP:
        return "HIGH"
    return "MEDIUM"
