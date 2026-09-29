"""Unit tests for the portfolio view adapter (``build_portfolio_view``).

Pure transformations only: fixture portfolios in, view data out. No network,
no database, and no writes (the adapter is read-only by design).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.portfolio.models import Portfolio, Position
from backend.portfolio.portfolio_repository import JsonPortfolioRepository
from backend.services.ui_adapter import DASH, build_portfolio_view

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _load(name: str) -> Portfolio:
    return JsonPortfolioRepository(FIXTURES / f"{name}.json").load()


def _position(ticker, quantity=1.0, avg=100.0, current=100.0):
    return Position(
        ticker=ticker,
        quantity=quantity,
        avg_price=avg,
        current_price=current,
        entry_date=datetime(2025, 1, 1, tzinfo=UTC),
    )


def test_empty_portfolio_view():
    view = build_portfolio_view(_load("portfolio_empty"))
    assert view.is_empty is True
    assert view.positions == []
    assert view.totals["market_value"] == 0.0
    assert view.totals["total_pnl"] == 0.0
    assert view.totals["total_return"] is None
    assert view.warnings == []
    assert view.sector_exposure == []


def test_three_position_totals():
    view = build_portfolio_view(_load("portfolio_three"))
    assert view.is_empty is False
    assert len(view.positions) == 3
    assert view.totals["market_value"] == pytest.approx(8400.0)
    assert view.totals["cost_basis"] == pytest.approx(6800.0)
    assert view.totals["unrealized_pnl"] == pytest.approx(1600.0)
    assert view.totals["total_pnl"] == pytest.approx(1600.0)
    assert view.totals["total_return"] == pytest.approx(1600.0 / 6800.0)
    assert view.positions[0]["Thesis"] == "moat fuerte"
    assert view.positions[0]["Signal"] == "BUY"


@pytest.mark.parametrize("count", [1, 2, 5, 10])
def test_hhi_for_equal_weights(count):
    portfolio = Portfolio(positions=[_position(f"T{i}") for i in range(count)])
    view = build_portfolio_view(portfolio)
    assert view.risk["hhi"] == pytest.approx(1.0 / count, abs=1e-3)


def test_sector_exposure_aggregates():
    portfolio = _load("portfolio_three")
    sectors = {
        "AAPL": "Technology",
        "MSFT": "Technology",
        "KO": "Consumer Defensive",
    }
    view = build_portfolio_view(portfolio, sectors)
    exposure = {row["sector"]: row["weight"] for row in view.sector_exposure}
    assert exposure["Technology"] == pytest.approx(6400.0 / 8400.0, abs=1e-3)
    assert exposure["Consumer Defensive"] == pytest.approx(2000.0 / 8400.0, abs=1e-3)


def test_single_name_concentration_warning():
    view = build_portfolio_view(_load("portfolio_concentrated"))
    assert any("AAPL" in warning and "25%" in warning for warning in view.warnings)
    assert view.risk["largest_position_weight"] == pytest.approx(0.9, abs=1e-3)
    assert view.risk["single_name_risk"] is True


def test_sector_concentration_warning():
    portfolio = _load("portfolio_three")
    sectors = {
        "AAPL": "Technology",
        "MSFT": "Technology",
        "KO": "Consumer Defensive",
    }
    view = build_portfolio_view(portfolio, sectors)
    assert any(
        "Technology" in warning and "40%" in warning for warning in view.warnings
    )


def test_missing_price_renders_dash():
    portfolio = Portfolio(positions=[_position("AAPL", current=0.0)])
    view = build_portfolio_view(portfolio)
    row = view.positions[0]
    assert row["Current Price"] == DASH
    assert row["Value"] == DASH
    assert row["PnL"] == DASH
    assert row["PnL%"] == DASH
