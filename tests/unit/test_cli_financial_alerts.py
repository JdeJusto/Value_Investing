"""CLI `financial-alerts`: output format, filters and exit code."""

from __future__ import annotations

import re
import sys
from typing import ClassVar

import pytest

from backend.services.alert_service import Alert, AlertsReport
from cli.main import main


class _View:
    company_name = "Test Co."


class _ViewService:
    last: ClassVar[dict] = {}
    facts: ClassVar[list] = [{"concept": "Revenues"}]

    def fetch_facts(self, ticker, period="FY", max_years=15):
        type(self).last = {"ticker": ticker, "period": period}
        return list(type(self).facts)

    def build(self, ticker, period="FY", max_years=15, facts=None):
        return _View()


class _AlertService:
    report: ClassVar[AlertsReport | None] = None
    last: ClassVar[dict] = {}

    def __init__(self, facts):
        self._facts = facts

    def build(self, ticker, company_name, fiscal_period="FY"):
        type(self).last = {
            "ticker": ticker,
            "company_name": company_name,
            "period": fiscal_period,
        }
        return type(self).report


def _alert(
    rule_id: str,
    severity: str,
    title: str = "A title",
    message: str = "A message.",
    evidence: dict | None = None,
) -> Alert:
    return Alert(
        rule_id=rule_id,
        severity=severity,
        title=title,
        message=message,
        evidence=evidence or {"K": "V"},
        metric_hint=None,
        period="FY2025",
    )


def _report(alerts: list[Alert], skipped: int = 2) -> AlertsReport:
    return AlertsReport(
        ticker="AAPL",
        company_name="Test Co.",
        alerts=alerts,
        rules_evaluated=10,
        rules_skipped=skipped,
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    import backend.services.alert_service as alert_module
    import backend.services.financials_view_service as view_module

    _ViewService.last = {}
    _ViewService.facts = [{"concept": "Revenues"}]
    _AlertService.last = {}
    _AlertService.report = _report([])
    monkeypatch.setattr(view_module, "FinancialsViewService", _ViewService)
    monkeypatch.setattr(alert_module, "AlertService", _AlertService)
    monkeypatch.delenv("VI_DEMO", raising=False)


def _run(*argv):
    sys.argv = ["main.py", *argv]
    main()


def test_output_format_lists_severity_groups_and_evidence(capsys):
    _AlertService.report = _report(
        [
            _alert(
                "low_cash_runway",
                "CRITICAL",
                title="Low cash runway",
                message="Less than 6 months of operating expenses in cash.",
                evidence={"Cash": "$1,200,000,000", "Runway": "4.2 months"},
            ),
            _alert("margin_collapse", "WARNING", title="Gross Margin collapse"),
            _alert("revenue_decline", "INFO", title="Revenue decline"),
        ]
    )
    with pytest.raises(SystemExit):
        _run("financial-alerts", "AAPL")
    out = capsys.readouterr().out
    assert "Financial Alerts — AAPL (Test Co.)" in out
    assert "🔴 CRITICAL (1)" in out
    assert "🟠 WARNING (1)" in out
    assert "🔵 INFO (1)" in out
    assert "  • Low cash runway" in out
    assert "    Less than 6 months of operating expenses in cash." in out
    assert "    Cash: $1,200,000,000 · Runway: 4.2 months" in out
    assert "Rules evaluated: 10 · Skipped: 2 (insufficient data)" in out
    assert "Data source: Financial-DataBase (SEC EDGAR) · Fiscal period: FY" in out


def test_exit_code_is_zero_without_critical(capsys):
    _AlertService.report = _report([_alert("revenue_decline", "INFO")])
    _run("financial-alerts", "AAPL")
    out = capsys.readouterr().out
    assert "🔵 INFO (1)" in out


def test_exit_code_is_one_with_critical():
    _AlertService.report = _report([_alert("low_cash_runway", "CRITICAL")])
    with pytest.raises(SystemExit) as excinfo:
        _run("financial-alerts", "AAPL")
    assert excinfo.value.code == 1


def test_severity_filter_limits_the_display_but_not_the_exit_code(capsys):
    _AlertService.report = _report(
        [
            _alert("low_cash_runway", "CRITICAL"),
            _alert("revenue_decline", "INFO"),
        ]
    )
    with pytest.raises(SystemExit):
        _run("financial-alerts", "AAPL", "--severity", "INFO")
    out = capsys.readouterr().out
    assert "🔵 INFO (1)" in out
    assert "🔴 CRITICAL (0)" in out  # filtered out of the display
    assert "Low cash runway" not in out


def test_invalid_severity_is_reported_without_running(capsys):
    _run("financial-alerts", "AAPL", "--severity", "BOGUS")
    out = capsys.readouterr().out
    assert "Invalid severity: BOGUS" in out
    assert _ViewService.last == {}


def test_period_flag_reaches_the_services(capsys):
    _run("financial-alerts", "AAPL", "--period", "Q2")
    assert _ViewService.last["period"] == "Q2"
    assert _AlertService.last["period"] == "Q2"
    assert "Fiscal period: Q2" in capsys.readouterr().out


def test_missing_facts_prints_a_clear_message(capsys):
    _ViewService.facts = []
    _run("financial-alerts", "ZZZZ")
    out = capsys.readouterr().out
    assert "No stored financial facts for ZZZZ." in out


def test_demo_mode_reads_the_fixture(monkeypatch, capsys):
    import backend.services.alert_service as alert_module

    monkeypatch.setenv("VI_DEMO", "1")
    monkeypatch.setattr(
        alert_module,
        "load_demo_alerts",
        lambda ticker: _report([_alert("earnings_quality", "INFO")]),
    )
    _run("financial-alerts", "AAPL")
    out = capsys.readouterr().out
    assert "🔵 INFO (1)" in out
    assert _ViewService.last == {}  # the database path was not touched


def test_demo_flag_enables_the_demo_path(monkeypatch, capsys):
    import backend.services.alert_service as alert_module
    import backend.services.demo_mode as demo_module

    monkeypatch.setattr(
        demo_module, "enable_demo", lambda: monkeypatch.setenv("VI_DEMO", "1")
    )
    monkeypatch.setattr(
        alert_module,
        "load_demo_alerts",
        lambda ticker: _report([_alert("revenue_decline", "INFO")]),
    )
    _run("financial-alerts", "AAPL", "--demo")
    out = capsys.readouterr().out
    assert "🔵 INFO (1)" in out


def test_demo_mode_without_a_fixture(monkeypatch, capsys):
    import backend.services.alert_service as alert_module

    monkeypatch.setenv("VI_DEMO", "1")
    monkeypatch.setattr(alert_module, "load_demo_alerts", lambda ticker: None)
    _run("financial-alerts", "ZZZZ")
    assert "No alerts fixture for" in capsys.readouterr().out


def test_severity_group_and_bullets_are_colored_on_a_tty(monkeypatch):
    """On a terminal the group header and alert bullets carry the severity
    color; a redirected run keeps plain text (asserted by the tests above)."""
    import io

    class _TTY(io.StringIO):
        def isatty(self) -> bool:  # pragma: no cover - trivial
            return True

    _AlertService.report = _report(
        [
            _alert("low_cash_runway", "CRITICAL", title="Low cash runway"),
            _alert("revenue_decline", "INFO", title="Revenue decline"),
        ]
    )
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", _TTY())

    with pytest.raises(SystemExit):
        _run("financial-alerts", "AAPL")

    out = sys.stdout.getvalue()
    plain = re.sub(r"\x1b\[[0-9;]*m", "", out)
    assert "🔴 CRITICAL (1)" in plain
    assert "🔵 INFO (1)" in plain
    assert "  • Low cash runway" in plain
    assert "\x1b" in out  # severity colors are emitted on a terminal
