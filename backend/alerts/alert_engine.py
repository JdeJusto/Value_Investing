"""Alert engine: deterministic alert evaluation over analyses.

Each company can emit at most one alert per type per evaluation:

- BUY_SIGNAL     — the screener signal is BUY on data of enough quality
- SELL_WARNING   — the total score dropped enough vs the previous state
- TRIGGER_EVENT  — a fundamental trigger fired (margin expansion, etc.)
"""

from dataclasses import asdict, dataclass

from backend.alerts.triggers import (
    BUY_SIGNAL,
    SELL_WARNING,
    TRIGGER_EVENT,
    composite_score,
    sell_warning_confidence,
    sell_warning_score_drop,
    trigger_label,
)
from backend.screener.ranking_engine import rank_score
from backend.screener.signals import (
    calibrate_trigger_thresholds,
    detect_trigger,
    generate_signal,
)


@dataclass
class Alert:
    ticker: str
    alert_type: str
    reason: list[str]
    confidence: str

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "alert_type": self.alert_type,
            "reason": self.reason,
            "confidence": self.confidence,
        }


def _buy_alert(
    ticker: str, analysis: dict, thresholds: dict | None = None
) -> Alert | None:
    rank = rank_score(analysis)
    signal = generate_signal(analysis, rank, thresholds=thresholds)
    if signal["signal"] != "BUY":
        return None
    confidence = signal["confidence"]
    reasons = [f"senal BUY: {signal['reason'][0]}"] if signal["reason"] else []
    trigger = trigger_label(signal["trigger"])
    if trigger:
        reasons.append(f"trigger {trigger}")
    return Alert(
        ticker=ticker, alert_type=BUY_SIGNAL, reason=reasons, confidence=confidence
    )


def _sell_alert(
    ticker: str,
    current: dict,
    previous: dict,
    thresholds: dict | None = None,
) -> Alert | None:
    prev_score = composite_score(previous)
    current_score = composite_score(current)
    if prev_score is None or current_score is None:
        return None
    drop = sell_warning_score_drop(prev_score, current_score)
    if drop is None:
        return None
    reasons = [
        f"score total {prev_score:.1f} -> {current_score:.1f} " f"(-{drop:.0f} puntos)"
    ]
    trigger = trigger_label(detect_trigger(current, thresholds=thresholds))
    if trigger:
        reasons.append(f"trigger {trigger}")
    return Alert(
        ticker=ticker,
        alert_type=SELL_WARNING,
        reason=reasons,
        confidence=sell_warning_confidence(drop),
    )


def _trigger_alert(
    ticker: str, analysis: dict, thresholds: dict | None = None
) -> Alert | None:
    trigger = trigger_label(
        detect_trigger(analysis, thresholds=thresholds)
    )
    if trigger is None:
        return None
    rank = rank_score(analysis)
    confidence = "HIGH" if rank >= 75.0 else "MEDIUM"
    return Alert(
        ticker=ticker,
        alert_type=TRIGGER_EVENT,
        reason=[f"trigger {trigger}"],
        confidence=confidence,
    )


def evaluate_company(
    ticker: str,
    current: dict,
    previous: dict | None = None,
    thresholds: dict | None = None,
) -> list[Alert]:
    """All alerts for one company given its current (and past) state.

    ``thresholds`` carries the universe-calibrated trigger floors (see
    ``calibrate_trigger_thresholds``); when None the absolute floors apply.
    """
    alerts: list[Alert] = []

    trigger = _trigger_alert(ticker, current, thresholds=thresholds)
    if trigger is not None:
        alerts.append(trigger)

    buy = _buy_alert(ticker, current, thresholds=thresholds)
    if buy is not None:
        alerts.append(buy)

    if previous is not None:
        sell = _sell_alert(
            ticker, current, previous, thresholds=thresholds
        )
        if sell is not None:
            alerts.append(sell)

    return alerts


def run(
    analyses: dict[str, dict],
    previous: dict[str, dict] | None = None,
) -> list[Alert]:
    """Evaluate every company and return the deduplicated alert list.

    Trigger thresholds are calibrated across the whole analyzed universe so
    only cross-sectionally standout improvements fire a TRIGGER_EVENT.
    Companies whose current analysis is None (insufficient data, failed
    analysis) are skipped: an alert cannot be derived from no analysis.
    """
    thresholds = calibrate_trigger_thresholds(analyses.values())
    alerts: list[Alert] = []
    for ticker, current in analyses.items():
        if current is None:
            continue
        alerts.extend(
            evaluate_company(
                ticker,
                current,
                previous.get(ticker) if previous else None,
                thresholds=thresholds,
            )
        )
    return dedupe(alerts)


def dedupe(alerts: list[Alert]) -> list[Alert]:
    """One alert per (ticker, alert_type); the first match wins."""
    seen = set()
    unique: list[Alert] = []
    for alert in alerts:
        key = (alert.ticker, alert.alert_type)
        if key in seen:
            continue
        seen.add(key)
        unique.append(alert)
    return unique


def to_dicts(alerts: list[Alert]) -> list[dict]:
    return [asdict(alert) for alert in alerts]
