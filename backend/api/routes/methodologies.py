"""Methodologies endpoint — all eight book screens for one company."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.api.auth import require_api_key
from backend.api.deps import get_price_service, get_repository, load_company_rows
from backend.api.responses import ApiError, ok
from backend.methodologies.registry import discover, registry
from backend.services.consensus_service import summarize_verdicts

router = APIRouter(prefix="/api/v1/company", tags=["company"])


@router.get("/{ticker}/methodologies", dependencies=[Depends(require_api_key)])
def company_methodologies(
    ticker: str,
    repository: Any = Depends(get_repository),
    price_service: Any = Depends(get_price_service),
) -> dict[str, Any]:
    """Run every registered book methodology and summarize the verdicts.

    Thin orchestration over the same registry the CLI uses (see
    ``cli/commands/compare_methodologies.py``); the summary counts come from
    the shared :func:`summarize_verdicts` helper.
    """
    normalized = ticker.strip().upper()
    rows = load_company_rows(repository, normalized)

    try:
        discover()
        results = []
        for name in registry.list():
            methodology = registry.get(name)
            if methodology is None:
                continue
            results.append(methodology.evaluate(normalized, rows, price_service))
    except Exception as exc:  # a failure here is a 503, not a 500
        raise ApiError(
            503, "SERVICE_UNAVAILABLE", "Methodology evaluation failed"
        ) from exc

    try:
        name = repository.get_company_name(normalized)
    except Exception:  # noqa: BLE001 — metadata is best-effort
        name = None

    verdicts = {result.methodology: result.verdict.value for result in results}
    data = {
        "ticker": normalized,
        "name": name,
        "methodologies": [_methodology_payload(result) for result in results],
        "summary": summarize_verdicts(verdicts),
    }
    return ok(data, source="mixed", cache_ttl=300)


def _methodology_payload(result: Any) -> dict[str, Any]:
    """One MethodologyResult as JSON-safe primitives (enums -> values)."""
    return {
        "name": result.methodology,
        "family": result.family,
        "verdict": result.verdict.value,
        "score": result.score,
        "confidence": result.confidence.value,
        "reasons": list(result.reasons),
        "red_flags": list(result.red_flags),
        "failed_rules": list(result.failed_rules),
        "passed_rules": list(result.passed_rules),
    }
