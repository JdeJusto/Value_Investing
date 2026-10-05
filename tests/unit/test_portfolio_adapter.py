"""portfolio_adapter: re-export shim and refresh edge cases (moved module)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.portfolio.models import Portfolio, Position
from backend.services import portfolio_adapter, ui_adapter


def _position(ticker, quantity=1.0, avg=100.0, current=100.0):
    return Position(
        ticker=ticker,
        quantity=quantity,
        avg_price=avg,
        current_price=current,
        entry_date=datetime(2025, 1, 1, tzinfo=UTC),
    )


def test_ui_adapter_still_exposes_the_moved_view_models():
    """The compatibility shim: pages and tests import these from ui_adapter."""
    assert ui_adapter.build_portfolio_view is portfolio_adapter.build_portfolio_view
    assert ui_adapter.PortfolioView is portfolio_adapter.PortfolioView
    assert ui_adapter.PortfolioActionError is portfolio_adapter.PortfolioActionError
    assert ui_adapter.add_position is portfolio_adapter.add_position
    assert ui_adapter.exit_position is portfolio_adapter.exit_position
    assert ui_adapter.remove_position is portfolio_adapter.remove_position
    assert ui_adapter.validate_new_position is portfolio_adapter.validate_new_position
    assert (
        ui_adapter.refresh_portfolio_prices
        is portfolio_adapter.refresh_portfolio_prices
    )
    assert ui_adapter.save_portfolio_prices is portfolio_adapter.save_portfolio_prices


def test_sector_concentration_threshold_moved_with_the_block():
    assert portfolio_adapter.SECTOR_CONCENTRATION_THRESHOLD == 0.40


class _Prices:
    def __init__(self, prices):
        self._prices = prices

    def get_current_price(self, ticker):
        value = self._prices.get(ticker)
        if value == "boom":
            raise RuntimeError("yahoo down")
        return value


def test_refresh_skips_failed_and_non_positive_prices():
    portfolio = Portfolio(
        positions=[
            _position("AAPL", current=100.0),
            _position("ZERO", current=50.0),
            _position("BOOM", current=50.0),
            _position("MSFT", current=200.0),
        ]
    )
    refreshed = portfolio_adapter.refresh_portfolio_prices(
        portfolio,
        _Prices({"AAPL": 110.0, "ZERO": 0.0, "BOOM": "boom", "MSFT": 220.0}),
    )
    # A failed fetch (exception), a non-positive price and a missing ticker are
    # omitted — no fabricated price.
    assert set(refreshed) == {"AAPL", "MSFT"}
    assert refreshed["AAPL"]["delta_pct"] == pytest.approx(0.1)
