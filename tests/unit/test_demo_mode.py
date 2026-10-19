"""Demo mode: the offline bundle works and never touches the network."""

from __future__ import annotations

import json
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

#: The eight tickers the offline demo bundle originally shipped with
#: (v0.18 fixture, commit c7e4768). The bundle has since grown to 76
#: tickers, but these eight remain a historical contract: prices and the
#: Greenblatt rankings must keep covering them.
ORIGINAL_DEMO_TICKERS = (
    "AAPL",
    "JNJ",
    "JPM",
    "KO",
    "MSFT",
    "PLD",
    "TSLA",
    "XOM",
)


def test_bundle_is_complete_and_within_size_cap():
    """The bundle ships its files; the byte ceiling lives in the cap test."""
    files = [path for path in Path("data/demo").rglob("*") if path.is_file()]
    assert len(files) >= 10


def test_bundle_covers_the_original_eight_tickers():
    """Prices still cover the original cohort, all inside the bundle."""
    prices = set(load_demo_prices())
    assert set(ORIGINAL_DEMO_TICKERS) <= prices
    assert prices <= set(DEMO_TICKERS)


def test_demo_tickers_is_non_empty_and_sorted():
    assert DEMO_TICKERS
    assert list(DEMO_TICKERS) == sorted(DEMO_TICKERS)


def test_bundle_manifest_matches_files():
    """``DEMO_TICKERS`` and the fixture files on disk never drift apart."""
    fixture_dir = Path("data/demo/fundamentals")
    expected = tuple(sorted(path.stem.upper() for path in fixture_dir.glob("*.json")))
    assert DEMO_TICKERS == expected


BUNDLE_SIZE_CAP_BYTES = 2 * 1024 * 1024  # 2 MB


def test_bundle_size_under_cap():
    """Hard ceiling for the whole offline demo bundle.

    The bundle started at ~500 KB for eight tickers; commit ``4a96233``
    took it to ~1.5 MB with the 76-ticker expansion, and Streamlit pays
    for every byte at demo startup. 2 MB leaves room for roughly one
    more expansion of this size while catching an accidental "commit
    the whole history" regression. If the growth is intentional, raise
    this cap explicitly here and document why in the commit message.
    """
    total = sum(
        path.stat().st_size for path in Path("data/demo").rglob("*") if path.is_file()
    )
    assert total < BUNDLE_SIZE_CAP_BYTES, (
        f"demo bundle is {total} bytes, over the {BUNDLE_SIZE_CAP_BYTES} byte cap; "
        f"raise the cap deliberately if the growth is intentional"
    )


def test_bundle_has_no_duplicate_or_empty_files():
    """Every fundamentals fixture is non-empty, parses, and is unique."""
    seen: set[str] = set()
    for path in sorted(Path("data/demo/fundamentals").glob("*.json")):
        assert path.stat().st_size > 0, f"{path} is empty"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload, f"{path} parses to empty content"
        key = path.stem.upper()
        assert key not in seen, f"duplicate fixture for {key} ({path.name})"
        seen.add(key)


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


def test_demo_repository_exposes_facts(monkeypatch):
    """The demo store answers ``list_all_facts`` like the database one."""
    monkeypatch.setenv("VI_DEMO", "1")
    from backend.app.cli import build_financial_repository

    repository = build_financial_repository()
    facts = repository.list_all_facts("AAPL", "FY")
    assert facts
    assert {"concept", "value", "fiscal_year", "fiscal_period"} <= set(facts[0])
    assert facts == repository.list_all_facts("AAPL", "FY")


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
    ranked = set(payload["rankings"])
    # The pinned fixture ranks the original eight demo companies plus
    # filler beyond them (filler makes the ranking meaningful), and the
    # universe covers every entry it ranks.
    assert set(ORIGINAL_DEMO_TICKERS) <= ranked
    assert ranked - set(ORIGINAL_DEMO_TICKERS), "rankings have no filler"
    assert payload["universe_size"] >= len(ranked)


def test_demo_rankings_are_never_stale(monkeypatch, tmp_path):
    """Pinned demo fixtures must not age out like the live weekly file."""
    import json

    monkeypatch.setenv("VI_DEMO", "1")
    stale = tmp_path / "greenblatt_stale.json"
    stale.write_text(
        json.dumps({"date": "2020-01-01", "rankings": {}, "universe_size": 0}),
        encoding="utf-8",
    )
    from backend.services import demo_mode

    monkeypatch.setattr(demo_mode, "demo_rankings_dir", lambda: tmp_path)
    from backend.methodologies.greenblatt.methodology import GreenblattMethodology

    payload, error = GreenblattMethodology()._load_rankings()
    assert error is None
    assert payload is not None


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
