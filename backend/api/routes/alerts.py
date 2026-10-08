"""Alerts endpoint — deterministic financial alerts for one company."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.api.auth import require_api_key
from backend.api.deps import get_repository, load_company_rows
from backend.api.responses import ok
from backend.services.alert_service import AlertService
from backend.services.financials_view_service import FinancialsViewService

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("/{ticker}", dependencies=[Depends(require_api_key)])
def ticker_alerts(
    ticker: str,
    period: str = "FY",
    repository: Any = Depends(get_repository),
) -> dict[str, Any]:
    """Run the deterministic alert rules over the company's stored facts.

    Same pipeline as the ``financial-alerts`` command (facts -> insights ->
    rules). Alerts arrive sorted by severity and then rule id; a company with
    no firing rules returns an empty list, never an error.
    """
    normalized = ticker.strip().upper()
    fiscal_period = (period or "FY").upper()
    load_company_rows(repository, normalized)  # 404 when the ticker is unknown

    service = FinancialsViewService(repository)
    facts = service.fetch_facts(normalized, fiscal_period)

    try:
        name = repository.get_company_name(normalized)
    except Exception:  # noqa: BLE001 — metadata is best-effort
        name = None

    report = AlertService(facts).build(normalized, name or normalized, fiscal_period)

    data = {
        "ticker": normalized,
        "alerts": [_alert_payload(alert) for alert in report.alerts],
        "rules_evaluated": report.rules_evaluated,
        "rules_skipped": report.rules_skipped,
        "summary": _severity_summary(report.alerts),
    }
    return ok(data, source="mixed", cache_ttl=300)


def _alert_payload(alert: Any) -> dict[str, Any]:
    """One Alert as JSON-safe primitives."""
    return {
        "rule_id": alert.rule_id,
        "severity": alert.severity,
        "title": alert.title,
        "message": alert.message,
        "evidence": dict(alert.evidence),
        "metric_hint": alert.metric_hint,
        "period": alert.period,
    }


def _severity_summary(alerts: list[Any]) -> dict[str, int]:
    """Counts per severity bucket (keys match the mobile summary)."""
    summary = {"critical": 0, "warning": 0, "info": 0}
    for alert in alerts:
        key = str(alert.severity).lower()
        if key in summary:
            summary[key] += 1
    return summary
