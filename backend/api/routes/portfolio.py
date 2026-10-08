"""Portfolio endpoints — positions, performance, add/exit/remove.

Every route goes through :class:`PortfolioService`, so writes share the
exclusive ``fcntl.flock`` with the CLI and the Streamlit UI; no handler
touches the JSON directly. Exit prices come from ``PriceService`` (in-memory
only — prices are never persisted).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.api.auth import require_api_key
from backend.api.deps import (
    get_portfolio_service,
    get_price_service,
    get_repository,
    load_company_rows,
)
from backend.api.responses import ApiError, ok
from backend.services.portfolio_adapter import (
    PortfolioActionError,
    add_position,
    remove_position,
)

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])

CACHE_TTL_SECONDS = 60
VALID_SIGNALS = {"BUY", "WATCH", "HOLD"}


class PositionCreate(BaseModel):
    """Body of ``POST /api/v1/portfolio/positions``."""

    ticker: str
    shares: float
    price: float
    thesis: str | None = None
    signal: str | None = None  # BUY | WATCH | HOLD
    date: str | None = None  # ISO date, defaults to today


def _parse_entry_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ApiError(
            400, "VALIDATION_ERROR", f"date must be ISO YYYY-MM-DD: {value!r}"
        ) from exc


def _parse_signal(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip().upper()
    if normalized not in VALID_SIGNALS:
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            f"signal must be one of {', '.join(sorted(VALID_SIGNALS))}",
        )
    return normalized


def _view_payload(row: dict) -> dict[str, Any]:
    """One ``PortfolioService.view()`` row as the API position shape."""
    quantity = float(row.get("quantity") or 0.0)
    avg_price = row.get("avg_price")
    current_price = row.get("current_price")
    value = quantity * float(current_price) if current_price is not None else None
    pnl = (
        (float(current_price) - float(avg_price)) * quantity
        if current_price is not None and avg_price is not None
        else None
    )
    opened = row.get("entry_date")
    return {
        "ticker": row["ticker"],
        "shares": quantity,
        "avg_price": avg_price,
        "current_price": current_price,
        "value": value,
        "pnl": pnl,
        "pnl_pct": row.get("unrealized_return"),
        "thesis": row.get("thesis") or None,
        "signal": row.get("signal"),
        "signal_at_entry": row.get("signal_at_entry") or None,
        "price_source": row.get("price_source"),
        "opened_at": opened[:10] if opened else None,
    }


def _summary(rows: list[dict]) -> dict[str, Any]:
    cost = sum(
        float(row.get("quantity") or 0.0) * float(row.get("avg_price") or 0.0)
        for row in rows
    )
    value = sum(
        float(row.get("quantity") or 0.0) * float(row.get("current_price") or 0.0)
        for row in rows
    )
    pnl = value - cost
    return {
        "cost": cost,
        "value": value,
        "pnl": pnl,
        "return_pct": (pnl / cost) if cost else None,
    }


@router.get("", dependencies=[Depends(require_api_key)])
def get_portfolio(service: Any = Depends(get_portfolio_service)) -> dict[str, Any]:
    """Open positions (live-refreshed) with their PnL and a summary."""
    rows = service.view()
    data = {
        "positions": [_view_payload(row) for row in rows],
        "summary": _summary(rows),
    }
    return ok(data, source="portfolio_json", cache_ttl=CACHE_TTL_SECONDS)


@router.get("/performance", dependencies=[Depends(require_api_key)])
def get_performance(service: Any = Depends(get_portfolio_service)) -> dict[str, Any]:
    """Performance snapshot plus allocation warnings (same as the CLI view)."""
    return ok(
        service.performance(), source="portfolio_json", cache_ttl=CACHE_TTL_SECONDS
    )


@router.post("/positions", status_code=201, dependencies=[Depends(require_api_key)])
def add_position_endpoint(
    payload: PositionCreate,
    service: Any = Depends(get_portfolio_service),
    repository: Any = Depends(get_repository),
) -> dict[str, Any]:
    """Add a position (averaging into an existing open one).

    Validates shares/price/date/signal; unknown tickers (no fundamentals in
    the database) are a 404. The response echoes the newly added lot; a
    subsequent GET reflects the merged position.
    """
    ticker = (payload.ticker or "").strip().upper()
    if not ticker:
        raise ApiError(400, "VALIDATION_ERROR", "Ticker is required.")
    load_company_rows(repository, ticker)  # 404 TICKER_NOT_FOUND / 503
    entry_date = _parse_entry_date(payload.date)
    signal = _parse_signal(payload.signal)
    try:
        position = add_position(
            service,
            ticker,
            payload.shares,
            payload.price,
            entry_date=entry_date,
            thesis=payload.thesis or "",
            signal=signal,
        )
    except PortfolioActionError as exc:
        raise ApiError(400, "VALIDATION_ERROR", str(exc)) from exc
    return ok(
        _created_payload(position), source="portfolio_json", cache_ttl=CACHE_TTL_SECONDS
    )


def _created_payload(position: Any) -> dict[str, Any]:
    return {
        "ticker": position.ticker,
        "shares": position.quantity,
        "avg_price": position.avg_price,
        "current_price": position.current_price,
        "value": position.market_value,
        "pnl": position.unrealized_pnl,
        "pnl_pct": position.unrealized_return,
        "thesis": position.thesis or None,
        "signal": None,
        "signal_at_entry": position.signal_at_entry or None,
        "opened_at": position.entry_date.date().isoformat(),
    }


@router.delete("/positions/{ticker}", dependencies=[Depends(require_api_key)])
def remove_position_endpoint(
    ticker: str, service: Any = Depends(get_portfolio_service)
) -> dict[str, Any]:
    """Remove a position without recording PnL (404 when absent)."""
    try:
        remove_position(service, ticker)
    except PortfolioActionError as exc:
        raise ApiError(404, "POSITION_NOT_FOUND", str(exc)) from exc
    return ok({"removed": True}, source="portfolio_json", cache_ttl=CACHE_TTL_SECONDS)


@router.post("/positions/{ticker}/exit", dependencies=[Depends(require_api_key)])
def exit_position_endpoint(
    ticker: str,
    service: Any = Depends(get_portfolio_service),
    prices: Any = Depends(get_price_service),
) -> dict[str, Any]:
    """Sell at the live price and record the realized PnL (404 when absent)."""
    normalized = (ticker or "").strip().upper()
    try:
        price = prices.get_current_price(normalized)
    except Exception as exc:  # a Yahoo failure is a 503, not a 500
        raise ApiError(
            503,
            "SERVICE_UNAVAILABLE",
            f"Could not fetch the current price for {normalized}",
        ) from exc
    if price is None or float(price) <= 0:
        raise ApiError(
            503,
            "SERVICE_UNAVAILABLE",
            f"Current price unavailable for {normalized}; try again later",
        )
    closed = service.exit(normalized, float(price))
    if closed is None:
        raise ApiError(404, "POSITION_NOT_FOUND", f"No open position for {normalized}")
    realized_pct = (
        (float(closed.exit_price) - float(closed.avg_price)) / float(closed.avg_price)
        if closed.avg_price
        else None
    )
    data = {
        "ticker": closed.ticker,
        "exit_price": closed.exit_price,
        "realized_pnl": closed.realized_pnl,
        "realized_pnl_pct": realized_pct,
    }
    return ok(data, source="portfolio_json", cache_ttl=CACHE_TTL_SECONDS)
