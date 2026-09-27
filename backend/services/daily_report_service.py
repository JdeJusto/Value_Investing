"""Daily report assembly: markdown builder and alert-state persistence.

Kept free of providers so it can be unit tested without network or a
database. The daily_workflow script feeds it the analysis outputs.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Optional

from backend.alerts.alert_engine import Alert

ALERT_LABELS = {
    "BUY_SIGNAL": "Buy signal",
    "SELL_WARNING": "Sell warning",
    "TRIGGER_EVENT": "Trigger event",
}


@dataclass
class DailyReport:
    report_date: date
    universe_size: int = 0
    screened_count: int = 0
    sec_update: str = "skipped"
    prices_mode: str = "real-time"
    rows: list[dict] = field(default_factory=list)
    alerts: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    price_notes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    network: dict = field(default_factory=dict)
    prices_stage: dict = field(default_factory=dict)
    yahoo_streak: dict = field(default_factory=dict)
    runtime_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "date": self.report_date.isoformat(),
            "universe_size": self.universe_size,
            "screened_count": self.screened_count,
            "sec_update": self.sec_update,
            "prices_mode": self.prices_mode,
            "rows": self.rows,
            "alerts": self.alerts,
            "missing": self.missing,
            "price_notes": self.price_notes,
            "notes": self.notes,
            "network": self.network,
            "prices_stage": self.prices_stage,
            "yahoo_streak": self.yahoo_streak,
            "runtime_seconds": self.runtime_seconds,
        }


def load_state(path: str) -> dict:
    """Load the previous-run state (empty when absent or corrupt)."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_state(path: str, state: dict) -> None:
    """Persist the current state for the next run's SELL_WARNING compare."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)


def trim_state(analyses: dict[str, dict]) -> dict:
    """Keep only the bare minimum needed for SELL_WARNING comparisons."""
    trimmed: dict[str, dict] = {}
    for ticker, item in analyses.items():
        if not item:
            continue
        composite = item.get("composite_score") or {}
        if composite.get("total_score") is None:
            continue
        trimmed[ticker] = {"composite_score": dict(composite)}
    return trimmed


def alert_to_dict(alert: Alert) -> dict:
    return {
        "ticker": alert.ticker,
        "alert_type": alert.alert_type,
        "reason": alert.reason,
        "confidence": alert.confidence,
    }


def _fmt(value: Any, kind: str) -> str:
    if value is None:
        return "N/A"
    if kind == "dollar":
        return f"${value:,.0f}"
    if kind == "ratio":
        return f"{value:.1f}"
    if kind == "pct":
        return f"{value:.1%}"
    if kind == "score":
        return f"{value:.1f}"
    return str(value)


def _coverage_pct(report: DailyReport) -> str:
    if report.universe_size <= 0:
        return "0%"
    return f"{report.screened_count / report.universe_size:.0%}"


def build_markdown(report: DailyReport) -> str:
    lines: list[str] = []
    lines.append(f"# Daily report — {report.report_date.isoformat()}")
    lines.append("")
    lines.append(report.sec_update)
    lines.append("")

    lines.append(f"Universe screened: **{report.universe_size}** companies "
                 f"| prices: **{report.prices_mode}**")
    lines.append("")
    lines.append(f"Screened results that passed: **{report.screened_count}**"
                 f" | coverage: **{_coverage_pct(report)}**")
    lines.append("")
    if report.runtime_seconds:
        lines.append(f"Runtime: **{report.runtime_seconds:.0f}s**")
        lines.append("")

    if report.prices_mode == "real-time":
        lines.append("> Real-time prices are fetched from Yahoo Finance into an "
                     "in-memory cache only at request time — **no price is ever "
                     "persisted** to any database (the Financial-DataBase `prices` "
                     "table is untouched by Value Investing).")
        lines.append("")

    if report.network:
        lines.append("## Network")
        lines.append("")
        net = report.network
        sec_throttled = int(net.get("sec_403_count", 0)) + int(net.get("sec_429_count", 0))
        lines.append(
            f"SEC company syncs: **{net.get('sec_requests', 0)}** "
            f"(retries {net.get('sec_retries', 0)}, "
            f"HTTP 403/429 {sec_throttled}, "
            f"avg {_fmt(net.get('avg_sec_latency_ms', 0), 'number')} ms) | "
            f"Yahoo requests: **{net.get('yahoo_requests', 0)}** "
            f"(retries {net.get('yahoo_retries', 0)}, "
            f"avg {_fmt(net.get('avg_yahoo_latency_ms', 0), 'number')} ms)"
        )
        lines.append("")
        lines.append("> SEC counters are per company sync (VI delegates the HTTP "
                     "requests to the Financial-DataBase subprocess); Yahoo "
                     "counters are per HTTP attempt.")
        lines.append("")

    stage = report.prices_stage or {}
    failures = (stage.get("failures") or {}) if isinstance(stage, dict) else {}
    if stage or failures:
        processed = int(stage.get("processed", 0) or 0)
        lines.append("## Price stage")
        lines.append("")
        lines.append(f"Tickers processed: **{processed}**")
        lines.append("")
        if failures:
            # Stable order: the categories the engine can produce, then any
            # extra one a future classifier might add.
            known = ("yahoo_glitch", "mapping", "delisted", "unknown", "no_yahoo")
            parts = [f"{name}: {int(failures.get(name, 0))}" for name in known if name in failures]
            parts += [
                f"{name}: {int(count)}"
                for name, count in sorted(failures.items())
                if name not in known
            ]
            lines.append("Failures by category — " + " · ".join(parts))
        else:
            lines.append("Failures by category — none")
        lines.append("")
        if int(failures.get("no_yahoo", 0) or 0) and not any(
            failures.get(name, 0) for name in ("yahoo_glitch", "mapping", "delisted", "unknown")
        ):
            lines.append("> Every price-derived field is N/A because the Yahoo "
                         "preflight found the provider unreachable "
                         "(`no_yahoo`); no per-ticker probe was attempted.")
            lines.append("")

    streak = report.yahoo_streak or {}
    if streak.get("alerted"):
        from backend.services.yahoo_streak import StreakUpdate

        lines_of_alert = StreakUpdate(state=streak).report_lines()
        if lines_of_alert:
            lines.append("## ⚠️ Yahoo Rate Limit Alert")
            lines.append("")
            for line in lines_of_alert:
                lines.append(line)
            lines.append("")

    if report.rows:
        lines.append("## Screened")
        header = (
            "| # | Ticker | Company | Rating | Score | Rank | Price | P/E | "
            "FCF yield | EV/EBIT | Signal |"
        )
        lines.append(header)
        lines.append("|" + "---|" * 11)
        for row in report.rows:
            lines.append(
                "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                    row.get("rank", ""),
                    row.get("ticker", ""),
                    (row.get("name") or "N/A")[:24],
                    row.get("rating") or "N/A",
                    _fmt(row.get("total_score"), "score"),
                    _fmt(row.get("rank_score"), "score"),
                    _fmt(row.get("price"), "ratio"),
                    _fmt(row.get("per"), "ratio"),
                    _fmt(row.get("fcf_yield"), "pct"),
                    _fmt(row.get("ev_ebit"), "ratio"),
                    row.get("signal") or "N/A",
                )
            )
        lines.append("")

    if report.alerts:
        lines.append("## Alerts")
        for alert in report.alerts:
            label = ALERT_LABELS.get(
                alert["alert_type"], alert["alert_type"]
            )
            reason = "; ".join(alert["reason"]) if alert["reason"] else "-"
            lines.append(
                f"- **{alert['ticker']}** — {label} "
                f"(*{alert['confidence']}*): {reason}"
            )
        lines.append("")

    if report.missing:
        lines.append("## Missing data")
        lines.append(",".join(report.missing))
        lines.append("")

    if report.price_notes:
        lines.append("## Price notes")
        for note in report.price_notes:
            lines.append(f"- {note}")
        lines.append("")

    if report.notes:
        lines.append("## Notes")
        for note in report.notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_alerts(alerts: list[Alert]) -> list[str]:
    """Human-readable one-liners for the console."""
    lines: list[str] = []
    for alert in alerts:
        label = ALERT_LABELS.get(alert.alert_type, alert.alert_type)
        reason = "; ".join(alert.reason) if alert.reason else "-"
        lines.append(
            f"  {alert.ticker:<10} [{label}] ({alert.confidence}) {reason}"
        )
    return lines