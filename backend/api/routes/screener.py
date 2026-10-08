"""Screener endpoint — filter, sort and paginate the enriched universe.

The expensive screening pass (one Yahoo snapshot prefetch + per-ticker
methodologies) is cached per universe for :data:`CACHE_TTL_SECONDS`; every
request filters and paginates the cached rows, so infinite-scroll pages
after the first are served from memory.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends

from backend.api.auth import require_api_key
from backend.api.deps import get_repository, get_screener_source
from backend.api.responses import ApiError, ok
from backend.api.screener_source import (
    DEFAULT_METHODOLOGY,
    canonical_universe,
    resolve_universe_tickers,
)
from backend.services.consensus_service import (
    LYNCH_CATEGORIES,
    normalize_lynch_category,
)
from backend.services.ui_adapter import apply_numeric_filters

router = APIRouter(prefix="/api/v1", tags=["screener"])

CACHE_TTL_SECONDS = 300
MAX_PAGE_SIZE = 200

#: Verdicts a client may filter on (the screener's methodology outcomes).
VALID_VERDICTS = {"BUY", "WATCH", "HOLD", "AVOID", "N/A", "INSUFFICIENT_DATA"}

_cache: dict[str, tuple[float, list[dict]]] = {}
_cache_lock = threading.Lock()
_compute_locks: dict[str, threading.Lock] = {}


def _cached_universe(key: str, compute: Callable[[], list[dict]]) -> list[dict]:
    """Cached (TTL) universe rows; one computation at a time per key."""
    with _cache_lock:
        lock = _compute_locks.setdefault(key, threading.Lock())
    with lock:
        with _cache_lock:
            hit = _cache.get(key)
            if hit is not None and time.monotonic() - hit[0] < CACHE_TTL_SECONDS:
                return hit[1]
        rows = compute()
        with _cache_lock:
            _cache[key] = (time.monotonic(), rows)
        return rows


def _validate_numeric(name: str, value: float | None) -> None:
    if value is not None and value < 0:
        raise ApiError(400, "INVALID_FILTER", f"{name} cannot be negative")


def _parse_verdicts(verdict: str | None) -> set[str] | None:
    if not verdict:
        return None
    wanted = {item.strip().upper() for item in verdict.split(",")}
    wanted.discard("")
    invalid = wanted - VALID_VERDICTS
    if invalid:
        raise ApiError(
            400,
            "INVALID_FILTER",
            "Unknown verdict(s): "
            f"{', '.join(sorted(invalid))}. Valid: {', '.join(sorted(VALID_VERDICTS))}.",
        )
    return wanted


def _parse_categories(category: str | None) -> set[str] | None:
    if not category:
        return None
    wanted: set[str] = set()
    invalid: set[str] = set()
    for item in category.split(","):
        item = item.strip()
        if not item:
            continue
        normalized = normalize_lynch_category(item)
        if normalized in LYNCH_CATEGORIES:
            wanted.add(normalized)
        else:
            invalid.add(item)
    if invalid:
        raise ApiError(
            400,
            "INVALID_FILTER",
            "Unknown Lynch category: "
            f"{', '.join(sorted(invalid))}. Valid: {', '.join(LYNCH_CATEGORIES)}.",
        )
    return wanted


def _row_payload(row: dict) -> dict[str, Any]:
    """Internal enriched row -> API row (``per`` is exposed as ``pe``)."""
    return {
        "ticker": row["ticker"],
        "name": row["name"],
        "sector": row["sector"],
        "price": row["price"],
        "market_cap": row["market_cap"],
        "pe": row["per"],
        "roe": row["roe"],
        "fcf_yield": row["fcf_yield"],
        "verdict": row["verdict"],
        "score": row["score"],
        "category": row["category"],
        "key_reason": row["key_reason"],
    }


@router.get("/screener", dependencies=[Depends(require_api_key)])
def get_screener(
    universe: str = "sp500",
    sector: str | None = None,
    verdict: str | None = None,
    category: str | None = None,
    pe_max: float | None = None,
    roe_min: float | None = None,
    fcf_yield_min: float | None = None,
    market_cap_min: float | None = None,
    market_cap_max: float | None = None,
    page: int = 1,
    page_size: int = 50,
    repository: Any = Depends(get_repository),
    source: Callable[[list[str], Any], list[dict]] = Depends(get_screener_source),
) -> dict[str, Any]:
    """Screen a universe, filter the rows and return one page.

    Units match the CLI/Streamlit screener: ``roe_min`` and
    ``fcf_yield_min`` are percentages, ``market_cap_min``/``market_cap_max``
    are billions of USD, ``pe_max`` is a ratio. ``page_size`` is capped at
    :data:`MAX_PAGE_SIZE`. Numeric filters reject negatives; ``0`` behaves
    as "filter disabled". ``verdict`` and ``category`` accept comma-separated
    lists. ``universe`` is one of ``sp500``, ``nasdaq100``, ``russell2000``,
    ``european``, ``all`` or a comma-separated union (``all`` warns that the
    first call can take minutes; the result is cached for 5 minutes).
    """
    echo, tokens = canonical_universe(universe)
    _validate_numeric("pe_max", pe_max)
    _validate_numeric("roe_min", roe_min)
    _validate_numeric("fcf_yield_min", fcf_yield_min)
    _validate_numeric("market_cap_min", market_cap_min)
    _validate_numeric("market_cap_max", market_cap_max)
    if (
        market_cap_min is not None
        and market_cap_max is not None
        and market_cap_max < market_cap_min
    ):
        raise ApiError(
            400,
            "INVALID_FILTER",
            "market_cap_max cannot be less than market_cap_min",
        )
    if page < 1:
        raise ApiError(400, "INVALID_PAGE", "page must be >= 1")
    if page_size < 1:
        raise ApiError(400, "INVALID_PAGE", "page_size must be >= 1")
    wanted_verdicts = _parse_verdicts(verdict)
    wanted_categories = _parse_categories(category)
    effective_page_size = min(page_size, MAX_PAGE_SIZE)

    tickers = resolve_universe_tickers(tokens)
    rows = _cached_universe(echo, lambda: source(tickers, repository))

    rows = apply_numeric_filters(
        rows,
        mcap_min=market_cap_min or 0.0,
        mcap_max=market_cap_max or 0.0,
        pe_max=pe_max or 0.0,
        roe_min=(roe_min or 0.0) / 100.0,
        fcf_min=(fcf_yield_min or 0.0) / 100.0,
    )
    if sector:
        wanted_sectors = {
            item.strip().lower() for item in sector.split(",") if item.strip()
        }
        rows = [row for row in rows if (row["sector"] or "").lower() in wanted_sectors]
    if wanted_verdicts is not None:
        rows = [
            row for row in rows if (row["verdict"] or "").upper() in wanted_verdicts
        ]
    if wanted_categories is not None:
        rows = [row for row in rows if row["category"] in wanted_categories]

    count = len(rows)
    total_pages = math.ceil(count / effective_page_size) if count else 0
    start = (page - 1) * effective_page_size
    page_rows = rows[start : start + effective_page_size]

    data: dict[str, Any] = {
        "universe": echo,
        "methodology": DEFAULT_METHODOLOGY,
        "filters": {
            "sector": sector,
            "verdict": verdict,
            "category": category,
            "pe_max": pe_max,
            "roe_min": roe_min,
            "fcf_yield_min": fcf_yield_min,
            "market_cap_min": market_cap_min,
            "market_cap_max": market_cap_max,
        },
        "rows": [_row_payload(row) for row in page_rows],
        "count": count,
        "page": page,
        "page_size": effective_page_size,
        "total_pages": total_pages,
    }
    if "all" in tokens:
        data["warning"] = (
            "universe=all screens the full master universe; the first call "
            "can take several minutes (the result is cached for 5 minutes)."
        )
    return ok(data, source="mixed", cache_ttl=CACHE_TTL_SECONDS)
