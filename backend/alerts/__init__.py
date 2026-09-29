"""Alerts package: alert engine, trigger rules and notifiers."""

from backend.alerts.alert_engine import (
    Alert,
    dedupe,
    evaluate_company,
    run,
    to_dicts,
)
from backend.alerts.notifier import (
    ConsoleNotifier,
    Notifier,
    notify_all,
)
from backend.alerts.triggers import (
    BUY_SIGNAL,
    SELL_WARNING,
    TRIGGER_EVENT,
    sell_warning_score_drop,
    trigger_label,
)

__all__ = [
    "BUY_SIGNAL",
    "SELL_WARNING",
    "TRIGGER_EVENT",
    "Alert",
    "ConsoleNotifier",
    "Notifier",
    "dedupe",
    "evaluate_company",
    "notify_all",
    "run",
    "sell_warning_score_drop",
    "to_dicts",
    "trigger_label",
]
