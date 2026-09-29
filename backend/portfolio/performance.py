"""Portfolio performance: returns, PnL and weights.

Deterministic math over position prices — no external data required.
``current_price`` is refreshed upstream by the analytics layer.
"""

from typing import Optional

from backend.portfolio.models import Portfolio, Position


def position_market_value(position: Position) -> float:
    return position.quantity * position.current_price


def position_cost_basis(position: Position) -> float:
    return position.quantity * position.avg_price


def position_weight(position: Position, total_value: float) -> float | None:
    if total_value <= 0:
        return None
    return position_market_value(position) / total_value


def unrealized_pnl(position: Position) -> float:
    return position.unrealized_pnl


def realized_pnl(position: Position) -> float:
    return position.realized_pnl


def total_return(portfolio: Portfolio) -> float | None:
    """(open market value + exit proceeds - total cost) / total cost."""
    cost = sum(position_cost_basis(p) for p in portfolio.positions)
    value = sum(position_market_value(p) for p in portfolio.positions if p.is_open)
    proceeds = sum(
        (p.exit_price or 0.0) * p.quantity for p in portfolio.positions if not p.is_open
    )
    if cost <= 0:
        return None
    return (value - cost + proceeds) / cost


def portfolio_performance(portfolio: Portfolio) -> dict:
    """Full performance snapshot with per-position detail."""
    open_positions = [p for p in portfolio.positions if p.is_open]
    closed_positions = [p for p in portfolio.positions if not p.is_open]
    cost = sum(position_cost_basis(p) for p in portfolio.positions)
    value = sum(position_market_value(p) for p in open_positions)
    unrealized = sum(unrealized_pnl(p) for p in open_positions)
    realized = sum(realized_pnl(p) for p in closed_positions)

    weights = {
        p.ticker: w
        for p in open_positions
        if (w := position_weight(p, value)) is not None
    }

    return {
        "market_value": round(value, 2),
        "cost_basis": round(cost, 2),
        "unrealized_pnl": round(unrealized, 2),
        "realized_pnl": round(realized, 2),
        "total_pnl": round(unrealized + realized, 2),
        "total_return": total_return(portfolio),
        "position_weights": weights,
        "positions": [
            {
                "ticker": p.ticker,
                "quantity": p.quantity,
                "avg_price": p.avg_price,
                "current_price": p.current_price,
                "market_value": round(position_market_value(p), 2),
                "unrealized_return": p.unrealized_return,
                "is_open": p.is_open,
            }
            for p in open_positions
        ],
    }
