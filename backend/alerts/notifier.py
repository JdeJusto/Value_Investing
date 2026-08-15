"""Alert notifiers: delivery adapters for generated alerts.

The engine is delivery-agnostic; new channels (email, telegram,
webhooks) only need a Notifier implementation.
"""

from abc import ABC, abstractmethod

from backend.alerts.alert_engine import Alert


class Notifier(ABC):
    @abstractmethod
    def notify(self, alert: Alert) -> None:
        """Deliver one alert through this channel."""


class ConsoleNotifier(Notifier):
    def __init__(self, echo=None):
        self._echo = echo or print

    def notify(self, alert: Alert) -> None:
        label = {
            "BUY_SIGNAL": "COMPRA",
            "SELL_WARNING": "VENTA",
            "TRIGGER_EVENT": "EVENTO",
        }.get(alert.alert_type, alert.alert_type)
        reason = "; ".join(alert.reason) if alert.reason else "-"
        self._echo(
            f"[{lab(alert.alert_type)} {label}] {alert.ticker} "
            f"(confianza {alert.confidence}): {reason}"
        )


def lab(alert_type: str) -> str:
    colors = {
        "BUY_SIGNAL": "\033[92m",
        "SELL_WARNING": "\033[91m",
        "TRIGGER_EVENT": "\033[93m",
    }
    reset = "\033[0m"
    return f"{colors.get(alert_type, '')}{alert_type}{reset}"


def notify_all(alerts: list[Alert], notifiers: list[Notifier]) -> None:
    """Dispatch every alert through every notifier."""
    for alert in alerts:
        for notifier in notifiers:
            notifier.notify(alert)


def console_only(alerts: list[Alert]) -> None:
    notify_all(alerts, [ConsoleNotifier()])
