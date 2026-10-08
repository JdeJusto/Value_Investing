"""DCF endpoint — the not-from-canon valuation for one company."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.api.auth import require_api_key
from backend.api.deps import get_price_service, get_repository, load_company_rows
from backend.api.responses import ok
from backend.valuation.dcf import DCFValuation

router = APIRouter(prefix="/api/v1/company", tags=["company"])


@router.get("/{ticker}/dcf", dependencies=[Depends(require_api_key)])
def company_dcf(
    ticker: str,
    repository: Any = Depends(get_repository),
    price_service: Any = Depends(get_price_service),
) -> dict[str, Any]:
    """Two-stage DCF valuation (``not-from-canon``).

    INSUFFICIENT_DATA is a normal 200 outcome: the payload carries the verdict
    and the reasons, never a fabricated number. Prices are read through
    ``PriceService`` and never persisted.
    """
    normalized = ticker.strip().upper()
    rows = load_company_rows(repository, normalized)

    result = DCFValuation().evaluate(normalized, rows, price_service)
    return ok(_dcf_payload(result), source="mixed", cache_ttl=300)


def _dcf_payload(result: Any) -> dict[str, Any]:
    """A DCFResult as JSON-safe primitives.

    The sensitivity grid is keyed by ``(wacc, growth)`` tuples; it is
    serialized as a sorted list of rows so clients can render a table.
    """
    sensitivity = [
        {"wacc": wacc, "growth": growth, "value": value}
        for (wacc, growth), value in sorted(result.sensitivity.items())
    ]
    return {
        "ticker": result.ticker,
        "variant": result.variant,
        "intrinsic_value": result.intrinsic_value_per_share,
        "current_price": result.current_price,
        "margin_of_safety": result.margin_of_safety,
        "verdict": result.verdict,
        "wacc": result.wacc,
        "assumptions": {
            "fcf_base": result.fcf_base,
            "growth_1_5": result.growth_1_5,
            "growth_6_10": result.growth_6_10,
            "terminal_growth": result.terminal_growth,
        },
        "sensitivity": sensitivity,
        "reasons": list(result.reasons),
        "missing_inputs": list(result.missing_inputs),
        "source": result.source,
    }
