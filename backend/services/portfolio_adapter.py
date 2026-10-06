"""Portfolio view-model and actions for the Streamlit UI.

Pure move out of ``ui_adapter``: the portfolio page and home read these
dataclasses and helpers. Prices arrive through the injected price service
and are never persisted here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from backend.portfolio.allocation import (
    overconcentration,
    risk_concentration,
    sector_exposure,
)
from backend.portfolio.performance import portfolio_performance
from backend.services.ui_format import DASH, fmt_or_dash

SECTOR_CONCENTRATION_THRESHOLD = 0.40


@dataclass
class PortfolioView:
    """Everything the UI needs for the read-only portfolio page."""

    name: str
    is_empty: bool
    positions: list[dict[str, Any]] = field(default_factory=list)
    totals: dict[str, Any] = field(default_factory=dict)
    sector_exposure: list[dict[str, Any]] = field(default_factory=list)
    risk: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def build_portfolio_view(portfolio: Any, sectors: dict | None = None) -> PortfolioView:
    """Pure transformation: a Portfolio -> portfolio page view data.

    Read-only: reuses the pure performance/allocation functions; it never
    refreshes or saves prices (the CLI owns that side effect).
    """
    sectors = sectors or {}
    performance = portfolio_performance(portfolio)
    open_positions = [p for p in portfolio.positions if p.is_open]
    rows: list[dict[str, Any]] = []
    for position in open_positions:
        has_price = bool(position.current_price and position.current_price > 0)
        rows.append(
            {
                "Ticker": position.ticker,
                "Shares": position.quantity,
                "Avg Price": fmt_or_dash(position.avg_price),
                "Current Price": (
                    fmt_or_dash(position.current_price) if has_price else DASH
                ),
                "Value": fmt_or_dash(position.market_value) if has_price else DASH,
                "PnL": fmt_or_dash(position.unrealized_pnl) if has_price else DASH,
                "PnL%": (
                    fmt_or_dash(position.unrealized_return, percent=True)
                    if has_price
                    else DASH
                ),
                "Thesis": position.thesis or DASH,
                "Signal": position.signal_at_entry or DASH,
            }
        )
    exposure = sector_exposure(portfolio, sectors, top=50)
    warnings = [
        f"{finding['ticker']} weighs {finding['weight']:.1%} of the portfolio "
        "(threshold 25%)"
        for finding in overconcentration(portfolio)
    ]
    warnings += [
        f"Sector {row['sector']} weighs {row['weight']:.1%} of the portfolio "
        "(threshold 40%)"
        for row in exposure
        if row["sector"] != "N/A" and row["weight"] > SECTOR_CONCENTRATION_THRESHOLD
    ]
    return PortfolioView(
        name=portfolio.name,
        is_empty=not open_positions,
        positions=rows,
        totals={
            "market_value": performance["market_value"],
            "cost_basis": performance["cost_basis"],
            "unrealized_pnl": performance["unrealized_pnl"],
            "realized_pnl": performance["realized_pnl"],
            "total_pnl": performance["total_pnl"],
            "total_return": performance["total_return"],
        },
        sector_exposure=exposure,
        risk=risk_concentration(portfolio),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Portfolio actions (validated; the UI form and buttons call these)
# ---------------------------------------------------------------------------
class PortfolioActionError(ValueError):
    """A portfolio action that failed validation; the message is user-facing."""


def validate_new_position(
    ticker: str,
    shares: float | None,
    price: float | None,
    entry_date: date | None = None,
    ticker_checker: Any = None,
    today: date | None = None,
) -> str:
    """Validate an add-position input; returns the normalized ticker.

    ``ticker_checker`` is an optional callable that answers "does this ticker
    exist in the fundamentals database?"; when omitted, no existence check is
    performed (graceful fallback).
    """
    normalized = (ticker or "").strip().upper()
    if not normalized:
        raise PortfolioActionError("Ticker is required.")
    if ticker_checker is not None and not ticker_checker(normalized):
        raise PortfolioActionError(
            f"Ticker {normalized} does not exist in the database."
        )
    if shares is None or shares <= 0:
        raise PortfolioActionError("Shares must be greater than 0.")
    if price is None or price <= 0:
        raise PortfolioActionError("Price must be greater than 0.")
    reference = today or datetime.now(UTC).date()
    if entry_date is not None and entry_date > reference:
        raise PortfolioActionError("Entry date cannot be in the future.")
    return normalized


def add_position(
    service: Any,
    ticker: str,
    shares: float | None,
    price: float | None,
    entry_date: date | None = None,
    thesis: str = "",
    signal: str = "",
    ticker_checker: Any = None,
    today: date | None = None,
):
    """Validated add; averages into an existing open position when present."""
    normalized = validate_new_position(
        ticker, shares, price, entry_date, ticker_checker, today
    )
    entry_dt = None
    if entry_date is not None:
        entry_dt = datetime(
            entry_date.year, entry_date.month, entry_date.day, tzinfo=UTC
        )
    return service.add(
        normalized,
        shares,
        price,
        entry_date=entry_dt,
        thesis=thesis,
        signal_at_entry=signal,
    )


def exit_position(
    service: Any, ticker: str, price: float | None, portfolio: Any = None
):
    """Validated exit; returns the closed position (realized PnL recorded)."""
    normalized = (ticker or "").strip().upper()
    if not normalized:
        raise PortfolioActionError("Ticker is required.")
    if price is None or price <= 0:
        raise PortfolioActionError("Exit price must be greater than 0.")
    if portfolio is not None:
        position = portfolio.position(normalized)
        if position is None:
            raise PortfolioActionError(f"No open position for {normalized}.")
        if position.quantity <= 0:
            raise PortfolioActionError(
                f"{normalized} has no shares; use Remove instead of Exit."
            )
    closed = service.exit(normalized, price)
    if closed is None:
        raise PortfolioActionError(f"No open position for {normalized}.")
    return closed


def remove_position(service: Any, ticker: str, portfolio: Any = None):
    """Validated remove (no PnL recorded); returns the removed position."""
    normalized = (ticker or "").strip().upper()
    if not normalized:
        raise PortfolioActionError("Ticker is required.")
    if portfolio is not None and not any(
        p.ticker.upper() == normalized for p in portfolio.positions
    ):
        raise PortfolioActionError(f"No position for {normalized}.")
    removed = service.remove(normalized)
    if removed is None:
        raise PortfolioActionError(f"No position for {normalized}.")
    return removed


# ---------------------------------------------------------------------------
# Daily report parsing (Home page)
# ---------------------------------------------------------------------------
def refresh_portfolio_prices(portfolio: Any, price_service: Any) -> dict[str, dict]:
    """Current price per open position vs the stored one; persists nothing.

    Returns ``{ticker: {"stored", "new", "delta_pct"}}``. Tickers whose fetch
    fails (or returns a non-positive price) are omitted — no fabricated price.
    """
    refreshed: dict[str, dict] = {}
    for position in portfolio.positions:
        if not position.is_open:
            continue
        try:
            price = price_service.get_current_price(position.ticker)
        except Exception:  # noqa: BLE001 — a failed fetch is not a crash
            price = None
        if price is None or price <= 0:
            continue
        stored = float(position.current_price or 0.0)
        delta = (float(price) - stored) / stored if stored else None
        refreshed[position.ticker] = {
            "stored": stored,
            "new": float(price),
            "delta_pct": delta,
        }
    return refreshed


def save_portfolio_prices(
    portfolio: Any, prices: dict[str, dict], repository: Any
) -> int:
    """Persist refreshed prices through the repository; returns how many.

    Only tickers present in ``prices`` are touched; the portfolio object is
    updated in place and saved atomically by the repository. This is the only
    path that writes prices, and the UI calls it from an explicit button.
    """
    updated = 0
    for ticker, data in prices.items():
        position = portfolio.position(ticker)
        if position is None:
            continue
        position.current_price = float(data["new"])
        updated += 1
    if updated:
        repository.save(portfolio)
    return updated
