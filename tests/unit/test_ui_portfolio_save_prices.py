"""The Streamlit "Save prices" button must write through PortfolioService.

Drives the real page with ``AppTest``: seed the in-memory quotes, click
"Save prices to portfolio", and assert the service persisted them (and was
the thing called — not the repository directly).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from streamlit.testing.v1 import AppTest

from backend.portfolio.models import Portfolio, Position
from backend.portfolio.portfolio_repository import JsonPortfolioRepository
from backend.portfolio.portfolio_service import PortfolioService

PAGE = str(Path(__file__).resolve().parents[2] / "ui/pages/04_portfolio.py")
HOME_PAGE = str(Path(__file__).resolve().parents[2] / "ui/pages/01_home.py")


def _seed_portfolio(path: Path) -> JsonPortfolioRepository:
    repository = JsonPortfolioRepository(path)
    repository.save(
        Portfolio(
            positions=[
                Position(
                    ticker="AAPL",
                    quantity=10.0,
                    avg_price=100.0,
                    current_price=100.0,
                    entry_date=datetime(2025, 1, 1, tzinfo=UTC),
                )
            ]
        )
    )
    return repository


def test_save_prices_button_goes_through_the_locked_service(tmp_path, monkeypatch):
    portfolio_path = tmp_path / "portfolio.json"
    repository = _seed_portfolio(portfolio_path)
    monkeypatch.setenv("PORTFOLIO_PATH", str(portfolio_path))

    calls: list[dict] = []
    original = PortfolioService.save_prices

    def spy(service_self, prices):
        calls.append(dict(prices))
        return original(service_self, prices)

    monkeypatch.setattr(PortfolioService, "save_prices", spy)

    at = AppTest.from_file(PAGE, default_timeout=60)
    at.session_state["pf_quotes"] = {"AAPL": 123.0}
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]

    save_button = next(button for button in at.button if button.key == "pf_save")
    save_button.click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]

    assert calls == [{"AAPL": 123.0}]
    assert repository.load().position("AAPL").current_price == 123.0
    assert (tmp_path / "portfolio.json.lock").exists()


def test_home_save_prices_button_goes_through_the_locked_service(tmp_path, monkeypatch):
    portfolio_path = tmp_path / "portfolio.json"
    repository = _seed_portfolio(portfolio_path)
    monkeypatch.setenv("PORTFOLIO_PATH", str(portfolio_path))

    calls: list[dict] = []
    original = PortfolioService.save_prices

    def spy(service_self, prices):
        calls.append(dict(prices))
        return original(service_self, prices)

    monkeypatch.setattr(PortfolioService, "save_prices", spy)

    at = AppTest.from_file(HOME_PAGE, default_timeout=60)
    at.session_state["home_prices"] = {
        "AAPL": {"stored": 100.0, "new": 155.0, "delta_pct": 0.55}
    }
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]

    save_button = next(button for button in at.button if button.key == "home_save")
    save_button.click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]

    assert calls == [{"AAPL": 155.0}]
    assert repository.load().position("AAPL").current_price == 155.0
