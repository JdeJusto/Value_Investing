"""Scorecard endpoint — the six-dimension roll-up for one company.

The endpoint is a thin adapter: it builds the shared :class:`ScorecardService`
and returns ``Scorecard.to_dict()`` **verbatim** inside the standard
``{data, meta}`` envelope. No field is renamed, added, dropped or reordered
here — the CLI and the Streamlit tab read the exact same payload.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.api.auth import require_api_key
from backend.api.deps import get_price_service, get_repository, load_company_rows
from backend.api.responses import ApiError, ok
from backend.services.scorecard_service import ScorecardService

router = APIRouter(prefix="/api/v1/company", tags=["company"])


@router.get("/{ticker}/scorecard", dependencies=[Depends(require_api_key)])
def company_scorecard(
    ticker: str,
    period: str = "FY",
    repository: Any = Depends(get_repository),
    price_service: Any = Depends(get_price_service),
) -> dict[str, Any]:
    """Six-dimension scorecard (Growth, Profitability, …) for one company.

    The scorecard never computes anything itself: every number comes from the
    services the CLI and the Streamlit UI already use. A missing input is
    reported as ``INSUFFICIENT`` per rule, never fabricated. Prices are read
    through ``PriceService`` and never persisted.
    """
    normalized = ticker.strip().upper()
    # Canonical 404 (unknown ticker) / 503 (DB down), shared with the other
    # company endpoints.
    load_company_rows(repository, normalized)

    card = ScorecardService(repository, price_service=price_service).build(
        normalized, period
    )
    if card is None:
        raise ApiError(404, "TICKER_NOT_FOUND", f"Unknown ticker: {normalized}")

    return ok(card.to_dict(), source="mixed", cache_ttl=3600)
