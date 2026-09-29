"""Unit tests for the validated portfolio actions (add / exit / remove).

Everything runs against a throwaway portfolio JSON in ``tmp_path``: the real
``data/portfolio.json`` is never touched.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from backend.portfolio.portfolio_repository import JsonPortfolioRepository
from backend.portfolio.portfolio_service import PortfolioService
from backend.services.ui_adapter import (
    PortfolioActionError,
    add_position,
    exit_position,
    remove_position,
    validate_new_position,
)


def _service(tmp_path: Path) -> PortfolioService:
    return PortfolioService(
        repository=JsonPortfolioRepository(tmp_path / "portfolio.json")
    )


def _checker(known=("AAPL", "KO")):
    return lambda ticker: ticker in known


def test_add_with_valid_inputs_creates_position(tmp_path):
    service = _service(tmp_path)
    position = add_position(
        service,
        "aapl",
        10,
        180.0,
        thesis="moat fuerte",
        signal="BUY",
        ticker_checker=_checker(),
    )
    assert position.ticker == "AAPL"
    assert position.quantity == 10
    assert position.avg_price == 180.0
    stored = JsonPortfolioRepository(tmp_path / "portfolio.json").load()
    assert stored.position("AAPL") is not None


def test_add_with_invalid_ticker_raises(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(PortfolioActionError, match="no existe"):
        add_position(service, "NOPE", 10, 100.0, ticker_checker=_checker())


def test_add_with_non_positive_shares_raises(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(PortfolioActionError, match="acciones"):
        add_position(service, "AAPL", 0, 100.0, ticker_checker=_checker())


def test_add_with_non_positive_price_raises(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(PortfolioActionError, match="precio"):
        add_position(service, "AAPL", 1, 0.0, ticker_checker=_checker())


def test_add_with_future_date_raises(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(PortfolioActionError, match="futura"):
        add_position(
            service,
            "AAPL",
            1,
            100.0,
            entry_date=date(2099, 1, 1),
            ticker_checker=_checker(),
        )


def test_add_existing_ticker_averages_price(tmp_path):
    service = _service(tmp_path)
    add_position(service, "AAPL", 10, 100.0, ticker_checker=_checker())
    add_position(service, "AAPL", 10, 120.0, ticker_checker=_checker())
    position = (
        JsonPortfolioRepository(tmp_path / "portfolio.json").load().position("AAPL")
    )
    assert position.quantity == 20
    assert position.avg_price == pytest.approx(110.0)


def test_exit_computes_realized_pnl(tmp_path):
    service = _service(tmp_path)
    add_position(service, "AAPL", 10, 100.0, ticker_checker=_checker())
    closed = exit_position(service, "AAPL", 150.0)
    assert closed.realized_pnl == pytest.approx(500.0)
    assert closed.exit_price == 150.0
    assert closed.is_open is False


def test_exit_without_open_position_raises(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(PortfolioActionError, match="abierta"):
        exit_position(service, "AAPL", 100.0)


def test_exit_zero_share_position_raises(tmp_path):
    service = _service(tmp_path)
    add_position(service, "AAPL", 1, 100.0, ticker_checker=_checker())
    portfolio = JsonPortfolioRepository(tmp_path / "portfolio.json").load()
    portfolio.position("AAPL").quantity = 0.0
    with pytest.raises(PortfolioActionError, match="Remove"):
        exit_position(service, "AAPL", 100.0, portfolio=portfolio)


def test_remove_without_exit_records_no_pnl(tmp_path):
    service = _service(tmp_path)
    add_position(service, "AAPL", 10, 100.0, ticker_checker=_checker())
    removed = remove_position(service, "AAPL")
    assert removed.realized_pnl == 0.0
    portfolio = JsonPortfolioRepository(tmp_path / "portfolio.json").load()
    assert portfolio.position("AAPL") is None


def test_remove_missing_position_raises(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(PortfolioActionError, match="No hay posición"):
        remove_position(service, "AAPL")


def test_validation_without_checker_skips_fdb(tmp_path):
    service = _service(tmp_path)
    position = add_position(service, "UNKNOWN_TICKER", 1, 10.0)
    assert position.ticker == "UNKNOWN_TICKER"


def test_validate_returns_normalized_ticker():
    assert validate_new_position("  ko ", 1, 10.0) == "KO"
