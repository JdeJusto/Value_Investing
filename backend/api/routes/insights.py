"""Insights endpoint — derived growth/stability metrics for one company."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.api.auth import require_api_key
from backend.api.deps import get_repository, load_company_rows
from backend.api.responses import ok
from backend.services.financial_insights_service import FinancialInsightsService
from backend.services.financials_view_service import FinancialsViewService
from backend.services.ui_format import DASH

router = APIRouter(prefix="/api/v1/company", tags=["company"])


@router.get("/{ticker}/insights", dependencies=[Depends(require_api_key)])
def company_insights(
    ticker: str,
    period: str = "FY",
    repository: Any = Depends(get_repository),
) -> dict[str, Any]:
    """Derived metrics (growth, stability, trends) from the stored facts.

    Same facts pipeline as ``/financials``; the values are the CLI's display
    strings, with the no-data placeholder ("—") serialized as ``null``.
    """
    normalized = ticker.strip().upper()
    load_company_rows(repository, normalized)  # 404 when the ticker is unknown

    facts = FinancialsViewService(repository).fetch_facts(normalized, period)
    try:
        name = repository.get_company_name(normalized)
    except Exception:  # noqa: BLE001 — metadata is best-effort
        name = None
    report = FinancialInsightsService(facts, normalized, name or normalized).build()

    data = {
        "ticker": normalized,
        "metrics": [_metric_payload(metric) for metric in report.metrics],
        "warnings": list(report.warnings),
    }
    return ok(data, source="financial_database", cache_ttl=3600)


def _metric_payload(metric: Any) -> dict[str, Any]:
    """One MetricInsight as JSON-safe primitives (dash placeholder -> null)."""
    return {
        "metric": metric.metric,
        "label": metric.label,
        "latest_value": _value(metric.latest_value),
        "latest_year": metric.latest_year,
        "yoy_change_pct": metric.yoy_change_pct,
        "cagr_5y": metric.cagr_5y,
        "cagr_10y": metric.cagr_10y,
        "average_5y": _value(metric.average_5y),
        "trend": metric.trend,
        "stability": metric.stability,
        "direction_changed": metric.direction_changed,
        "notes": list(metric.notes),
    }


def _value(value: str | None) -> str | None:
    """The formatter's no-data placeholder becomes JSON null."""
    return None if value in (None, DASH) else value
