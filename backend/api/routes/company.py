"""Company endpoints — the first real API surface (Phase 1)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.api.auth import require_api_key
from backend.api.deps import get_price_service, get_repository
from backend.api.responses import ApiError, ok

router = APIRouter(prefix="/api/v1/company", tags=["company"])


@router.get("/{ticker}", dependencies=[Depends(require_api_key)])
def company(
    ticker: str,
    repository: Any = Depends(get_repository),
    price_service: Any = Depends(get_price_service),
) -> dict[str, Any]:
    """Company profile plus the latest snapshot (FDB fundamentals + Yahoo price).

    Prices are fetched on demand and never persisted; a Yahoo failure degrades
    to ``null`` fields instead of failing the request.
    """
    normalized = ticker.strip().upper()
    try:
        rows = [
            row
            for row in (repository.get_best_available(normalized) or [])
            if row is not None
        ]
    except Exception as exc:
        raise ApiError(
            503, "SERVICE_UNAVAILABLE", "Financial database is unavailable"
        ) from exc

    if not rows:
        raise ApiError(404, "TICKER_NOT_FOUND", f"Unknown ticker: {normalized}")

    latest = rows[0]
    try:
        name = repository.get_company_name(normalized)
    except Exception:  # noqa: BLE001 — metadata is best-effort
        name = None
    try:
        cik = repository.get_cik(normalized)
    except Exception:  # noqa: BLE001 — metadata is best-effort
        cik = None
    try:
        price = price_service.get_current_price(normalized)
    except Exception:  # noqa: BLE001 — a Yahoo failure degrades to null
        price = None
    try:
        market_cap = price_service.get_market_cap(normalized)
    except Exception:  # noqa: BLE001 — a Yahoo failure degrades to null
        market_cap = None

    data = {
        "ticker": normalized,
        "name": name,
        "sector": getattr(latest, "sector", None),
        "cik": cik,
        "price": price,
        "market_cap": market_cap,
        "currency": getattr(latest, "currency", None),
        "fiscal_year": getattr(latest, "fiscal_year", None),
    }
    return ok(data, source="mixed", cache_ttl=300)
