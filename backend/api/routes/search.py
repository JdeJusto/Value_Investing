"""Search endpoint — ticker/name autocomplete for the mobile app."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.api.auth import require_api_key
from backend.api.deps import get_repository
from backend.api.responses import ApiError, ok

router = APIRouter(prefix="/api/v1", tags=["search"])

CACHE_TTL_SECONDS = 3600
MAX_LIMIT = 50


@router.get("/search", dependencies=[Depends(require_api_key)])
def search(
    q: str = "",
    limit: int = 20,
    repository: Any = Depends(get_repository),
) -> dict[str, Any]:
    """Case-insensitive ticker search with a legal-name fallback.

    Ticker matches (exact, then prefix, then substring) come first; when
    fewer than ``limit`` rows match, legal-name substring matches fill the
    rest. A query with no matches returns an empty list, never a 404.
    ``limit`` is capped at :data:`MAX_LIMIT`.
    """
    query = (q or "").strip()
    if not query:
        raise ApiError(400, "INVALID_QUERY", "q must not be empty")
    if limit < 1:
        raise ApiError(400, "INVALID_FILTER", "limit must be >= 1")
    effective_limit = min(limit, MAX_LIMIT)

    searcher = getattr(repository, "search_companies", None)
    if searcher is None:
        raise ApiError(
            503,
            "SERVICE_UNAVAILABLE",
            "Search is unavailable: the active repository has no company lookup",
        )
    try:
        found = searcher(query, effective_limit)
    except Exception as exc:  # a DB failure is a 503, not a 500
        raise ApiError(
            503, "SERVICE_UNAVAILABLE", "Financial database is unavailable"
        ) from exc

    results = [
        {
            "ticker": row.get("ticker"),
            "name": row.get("name"),
            "sector": row.get("sector"),
        }
        for row in (found or [])
    ]
    data = {"query": query, "results": results, "count": len(results)}
    return ok(data, source="financial_database", cache_ttl=CACHE_TTL_SECONDS)
