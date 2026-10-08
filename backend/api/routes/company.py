"""Company endpoints — the first real API surface (Phase 1)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.api.auth import require_api_key
from backend.api.deps import get_price_service, get_repository, load_company_rows
from backend.api.responses import ok

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
    rows = load_company_rows(repository, normalized)

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
