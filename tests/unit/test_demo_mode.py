"""Demo mode: the offline bundle works and never touches the network."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from backend.repositories.json_financial_repository import JsonFinancialRepository
from backend.services.demo_mode import (
    DEMO_FUNDAMENTALS,
    DEMO_REPORTS,
    DEMO_TICKERS,
    DemoPriceService,
    is_demo_ticker,
    load_demo_prices,
)


def test_bundle_is_complete_and_small():
    files = [path for path in Path("data/demo").rglob("*") if path.is_file()]
    assert len(files) >= 10
    total = sum(path.stat().st_size for path in files)
    assert total < 500 * 1024, f"demo bundle too heavy: {total / 1024:.0f} KB"


def test_bundle_covers_the_eight_tickers():
    assert sorted(load_demo_prices()) == list(DEMO_TICKERS)


def test_demo_tickers_is_non_empty_and_sorted():
    assert DEMO_TICKERS
    assert list(DEMO_TICKERS) == sorted(DEMO_TICKERS)


def test_demo_tickers_match_the_fixture_filenames():
    fixture_dir = Path("data/demo/fundamentals")
    expected = tuple(sorted(path.stem.upper() for path in fixture_dir.glob("*.json")))
    assert DEMO_TICKERS == expected


def test_is_demo_ticker_supports_the_bundle_case_insensitively():
    assert is_demo_ticker("AAPL") is True
    assert is_demo_ticker("aapl") is True
    assert is_demo_ticker("META") is False


def test_demo_repository_reads_ten_years(monkeypatch):
    monkeypatch.setenv("VI_DEMO", "1")
    from backend.app.cli import build_financial_repository

    repository = build_financial_repository()
    assert isinstance(repository, JsonFinancialRepository)
    assert repository._dir == DEMO_FUNDAMENTALS
    rows = repository.get_best_available("AAPL")
    assert rows and rows[0].fiscal_year == 2025
    assert len(rows) == 10


def test_without_the_flag_the_database_path_is_used(monkeypatch):
    monkeypatch.delenv("VI_DEMO", raising=False)
    from backend.app.cli import build_financial_repository

    repository = build_financial_repository()
    assert getattr(repository, "_dir", None) != DEMO_FUNDAMENTALS


def test_demo_prices_never_touch_the_network(monkeypatch):
    calls: list = []

    def boom(*args, **kwargs):
        calls.append(args)
        raise AssertionError("network call in demo mode")

    monkeypatch.setattr("backend.services.price_service.yf.Ticker", boom)
    service = DemoPriceService()
    assert service.get_current_price("AAPL") == 340.0
    assert service.get_current_prices(["AAPL", "KO"])["KO"] == 70.0
    assert service.get_market_cap("AAPL") > 0
    assert service.get_price_on_date("AAPL", date(2020, 1, 1)) == 340.0
    assert service.get_price_at_fiscal_year_end("AAPL", 2024) == 340.0
    assert service.get_historical_prices("AAPL")
    assert service.get_market_snapshots(["AAPL"])["AAPL"]["marketCap"] > 0
    assert calls == []


def test_price_service_factory_returns_the_demo_service(monkeypatch):
    monkeypatch.setenv("VI_DEMO", "1")
    import backend.services.price_service as price_service_module

    monkeypatch.setattr(price_service_module, "_PRICE_SERVICE", None)
    assert isinstance(price_service_module.get_price_service(), DemoPriceService)


def test_greenblatt_reads_the_demo_rankings(monkeypatch):
    monkeypatch.setenv("VI_DEMO", "1")
    from backend.methodologies.greenblatt.methodology import GreenblattMethodology

    payload, error = GreenblattMethodology()._load_rankings()
    assert error is None
    assert payload is not None and "AAPL" in payload["rankings"]
    assert payload["universe_size"] > len(DEMO_TICKERS)  # filler makes it meaningful


def test_demo_portfolio_has_three_positions():
    from backend.portfolio.models import Portfolio
    from backend.portfolio.portfolio_repository import JsonPortfolioRepository

    portfolio = JsonPortfolioRepository("data/demo/portfolio.json").load()
    assert isinstance(portfolio, Portfolio)
    assert sorted(p.ticker for p in portfolio.positions) == ["AAPL", "JPM", "KO"]


def test_demo_reports_dir_has_the_sample_report():
    assert (DEMO_REPORTS / "daily_demo.md").exists()


def test_ui_pages_run_in_demo_mode(monkeypatch):
    monkeypatch.setenv("VI_DEMO", "1")
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).resolve().parents[2]
    for page in ("ui/pages/01_home.py", "ui/pages/04_portfolio.py"):
        at = AppTest.from_file(str(root / page), default_timeout=60)
        at.run()
        assert not at.exception, f"{page}: {at.exception}"
