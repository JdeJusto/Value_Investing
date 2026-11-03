"""Scorecard endpoint — the six-dimension roll-up for one company.

The endpoint is a thin adapter: it builds the shared :class:`ScorecardService`
and returns ``Scorecard.to_dict()`` **verbatim** inside the standard
``{data, meta}`` envelope. No field is renamed, added, dropped or reordered
here — the CLI and the Streamlit tab read the exact same payload.

``?format=markdown`` returns the same payload rendered as a Markdown report
(``text/markdown``) for pasting into a document. JSON remains the default, so
existing clients are unaffected.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from backend.api.auth import require_api_key
from backend.api.deps import get_price_service, get_repository, load_company_rows
from backend.api.responses import ApiError, ok
from backend.services.scorecard_export import scorecard_to_markdown
from backend.services.scorecard_service import ScorecardService

router = APIRouter(prefix="/api/v1/company", tags=["company"])

#: Accepted values for the ``?format=`` query parameter.
EXPORT_FORMATS = ("json", "markdown")


@router.get("/{ticker}/scorecard", dependencies=[Depends(require_api_key)])
def company_scorecard(
    ticker: str,
    period: str = "FY",
    export_format: str = Query("json", alias="format"),
    repository: Any = Depends(get_repository),
    price_service: Any = Depends(get_price_service),
) -> Any:
    """The scorecard as JSON (default) or as a Markdown report.

    The scorecard never computes anything itself: every number comes from the
    services the CLI and the Streamlit UI already use. A missing input is
    reported as ``INSUFFICIENT`` per rule, never fabricated. Prices are read
    through ``PriceService`` and never persisted.
    """
    if export_format not in EXPORT_FORMATS:
        raise ApiError(
            400,
            "INVALID_FORMAT",
            f"Unknown format '{export_format}'. Use: {', '.join(EXPORT_FORMATS)}.",
        )

    normalized = ticker.strip().upper()
    # Canonical 404/503 for an unknown ticker or an unavailable database,
    # shared with the other company endpoints.
    load_company_rows(repository, normalized)

    card = ScorecardService(repository, price_service=price_service).build(
        normalized, period
    )
    if card is None:
        raise ApiError(404, "TICKER_NOT_FOUND", f"Unknown ticker: {normalized}")

    if export_format == "markdown":
        return Response(
            content=scorecard_to_markdown(card.to_dict()),
            media_type="text/markdown",
        )

    return ok(card.to_dict(), source="mixed", cache_ttl=3600)
