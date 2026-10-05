"""`financial-alerts` — deterministic financial alerts for one ticker.

Rules run over the same facts pipeline as the Financials tab (see
``backend/services/alert_service.py`` and ``docs/financial_alerts.md``): no
LLM, no external service. Exit code 1 when the company has at least one
CRITICAL alert (the ``--severity`` flag only filters the display), so shell
chains can react: ``financial-alerts AAPL || notify-send "Alert"``.
"""

from __future__ import annotations

from backend.app.cli import add_demo_argument
from cli.formatters import print_header, red

_SEVERITY_EMOJI = {"CRITICAL": "🔴", "WARNING": "🟠", "INFO": "🔵"}
_SEVERITY_ORDER = ("CRITICAL", "WARNING", "INFO")


def register(subparsers):
    p = subparsers.add_parser(
        "financial-alerts",
        help="Deterministic financial alerts (cash runway, margins, debt, FCF...)",
        description=(
            "Run the deterministic alert rules over the company's facts. "
            "Exit code 1 when at least one CRITICAL alert fires; --severity "
            "only filters what is displayed."
        ),
    )
    p.add_argument("ticker", help="Ticker (e.g. AAPL)")
    p.add_argument(
        "--period",
        default="FY",
        help="Fiscal period (default: FY; Q1-Q4 where stored)",
    )
    p.add_argument(
        "--severity",
        help="Severities to display, comma-separated (CRITICAL,WARNING,INFO)",
    )
    add_demo_argument(p)
    p.set_defaults(func=_run)
    return p


def _parse_severities(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    severities = {part.strip().upper() for part in raw.split(",") if part.strip()}
    invalid = severities - set(_SEVERITY_ORDER)
    if invalid:
        print(red(f"Severidad inválida: {', '.join(sorted(invalid))}"))
        return set()
    return severities


def _run(args):
    from backend.services.alert_service import AlertService, load_demo_alerts
    from backend.services.demo_mode import is_demo
    from backend.services.financials_view_service import FinancialsViewService

    ticker = args.ticker.upper().strip()
    period = (args.period or "FY").upper()
    severities = _parse_severities(args.severity)
    if severities == set():
        return

    if is_demo():
        report = load_demo_alerts(ticker)
        if report is None:
            print(red(f"No hay fixture de alerts para {ticker} en modo demo."))
            return
    else:
        service = FinancialsViewService()
        facts = service.fetch_facts(ticker, period)
        if not facts:
            print(red(f"No hay facts financieros almacenados para {ticker}."))
            return
        view = service.build(ticker, period, facts=facts)
        report = AlertService(facts).build(
            ticker, view.company_name if view else ticker, period
        )

    print_header(f"Financial Alerts — {ticker} ({report.company_name})")

    shown = [
        alert
        for alert in report.alerts
        if severities is None or alert.severity in severities
    ]
    for severity in _SEVERITY_ORDER:
        group = [alert for alert in shown if alert.severity == severity]
        print()
        print(f"{_SEVERITY_EMOJI[severity]} {severity} ({len(group)})")
        for alert in group:
            print()
            print(f"  • {alert.title}")
            print(f"    {alert.message}")
            evidence = " · ".join(
                f"{key}: {value}" for key, value in alert.evidence.items()
            )
            if evidence:
                print(f"    {evidence}")

    print()
    print(
        f"  Rules evaluated: {report.rules_evaluated} · "
        f"Skipped: {report.rules_skipped} (insufficient data)"
    )
    print()
    print(
        "  Data source: Financial-DataBase (SEC EDGAR) · "
        f"Fiscal period: {period}"
    )

    if any(alert.severity == "CRITICAL" for alert in report.alerts):
        raise SystemExit(1)
