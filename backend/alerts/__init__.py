"""Alerts package: alert engine, trigger rules and notifiers."""

from backend.alerts.alert_engine import (  # noqa: F401
    Alert,
    dedupe,
    evaluate_company,
    run,
    to_dicts,
)
from backend.alerts.notifier import (  # noqa: F401
    ConsoleNotifier,
    Notifier,
    notify_all,
)
from backend.alerts.triggers import (  # noqa: F401
    BUY_SIGNAL,
    SELL_WARNING,
    TRIGGER_EVENT,
    sell_warning_score_drop,
    trigger_label,
)

__all__ = [
    "Alert",
    "BUY_SIGNAL",
    "ConsoleNotifier",
    "Notifier",
    "SELL_WARNING",
    "TRIGGER_EVENT",
    "dedupe",
    "evaluate_company",
    "notify_all",
    "run",
    "sell_warning_score_drop",
    "to_dicts",
    "trigger_label",
]
