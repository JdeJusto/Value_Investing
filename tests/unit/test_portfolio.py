"""Unit tests: portfolio models, performance, allocation and service.

No providers, no network — prices and analytics are mocked.
"""

from datetime import datetime, timezone, UTC

import pytest

from backend.portfolio.allocation import (
    overconcentration,
    risk_concentration,
    sector_exposure,
)
from backend.portfolio.models import Portfolio, Position
from backend.portfolio.performance import (
    portfolio_performance,
    total_return,
)
from backend.portfolio.portfolio_repository import JsonPortfolioRepository
from backend.portfolio.portfolio_service import PortfolioService


def _position(
    ticker, quantity=10.0, avg_price=100.0, current=None, year=2025, **kwargs
) -> Position:
    return Position(
        ticker=ticker,
        quantity=quantity,
        avg_price=avg_price,
        current_price=current if current is not None else avg_price,
        entry_date=datetime(year, 1, 1, tzinfo=UTC),
        **kwargs,
    )


# ----------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------
def test_position_roundtrip_through_dict():
    position = _position(
        "AAPL",
        12.5,
        150.0,
        current=160.0,
        thesis="poder de precios",
        signal_at_entry="BUY",
    )
    restored = Position.from_dict(position.to_dict())
    assert restored == position
    assert restored.entry_date == position.entry_date


def test_position_computed_values():
    position = _position("KO", quantity=10.0, avg_price=100.0, current=120.0)
    assert position.market_value == 1200.0
    assert position.cost_basis == 1000.0
    assert position.unrealized_pnl == 200.0
    assert position.unrealized_return == pytest.approx(0.20)
    assert position.is_open is True


def test_position_realized_pnl_on_close():
    position = _position("KO", 10.0, 100.0, current=90.0)
    position.exit_price = 110.0
    assert position.realized_pnl == 100.0


def test_portfolio_average_in_merges_positions():
    portfolio = Portfolio()
    portfolio.add(_position("AAPL", quantity=10, avg_price=100.0))
    portfolio.add(_position("AAPL", quantity=10, avg_price=120.0))
    merged = portfolio.position("AAPL")
    assert merged.quantity == 20
    assert merged.avg_price == pytest.approx(110.0)


def test_portfolio_close_and_remove():
    portfolio = Portfolio()
    position = _position("MSFT", 5.0, 200.0)
    portfolio.add(position)
    assert portfolio.close("MSFT", 250.0) is position
    assert position.is_open is False
    assert portfolio.remove("MSFT") is position
    assert portfolio.positions == []


# ----------------------------------------------------------------------
# Performance
# ----------------------------------------------------------------------
def test_performance_snapshot_is_exact():
    portfolio = Portfolio()
    portfolio.add(_position("AAA", 10.0, 100.0, current=110.0))
    portfolio.add(_position("BBB", 10.0, 100.0, current=90.0))
    closed = _position("CCC", 10.0, 50.0, current=50.0)
    portfolio.add(closed)
    portfolio.close("CCC", 60.0)

    perf = portfolio_performance(portfolio)
    assert perf["market_value"] == 2000.0
    assert perf["cost_basis"] == 2500.0
    assert perf["unrealized_pnl"] == 0.0
    assert perf["realized_pnl"] == 100.0
    assert perf["total_pnl"] == 100.0
    assert perf["total_return"] == pytest.approx((2000 + 600 - 2500) / 2500)
    assert perf["position_weights"] == {"AAA": 0.55, "BBB": 0.45}
    assert len(perf["positions"]) == 2


def test_total_return_empty_portfolio_is_none():
    assert total_return(Portfolio()) is None


def test_json_repository_roundtrip(tmp_path):
    repo = JsonPortfolioRepository(tmp_path / "portfolio.json")
    portfolio = Portfolio()
    portfolio.add(_position("AAPL", 10.0, 150.0, thesis="calidad"))
    repo.save(portfolio)

    loaded = repo.load()
    assert loaded.name == "default"
    assert loaded.position("AAPL").quantity == 10.0
    assert loaded.position("AAPL").thesis == "calidad"


def test_json_repository_missing_file_returns_empty(tmp_path):
    repo = JsonPortfolioRepository(tmp_path / "nope.json")
    assert repo.load().positions == []


# ----------------------------------------------------------------------
# Allocation
# ----------------------------------------------------------------------
def test_overconcentration_flags_big_positions():
    portfolio = Portfolio()
    portfolio.add(_position("BIG", 75.0, 100.0, current=100.0))
    portfolio.add(_position("SMALL", 25.0, 100.0, current=100.0))
    findings = overconcentration(portfolio, threshold=0.30)
    assert [f["ticker"] for f in findings] == ["BIG"]
    assert findings[0]["weight"] == pytest.approx(0.75)


def test_sector_exposure_groups_by_sector():
    portfolio = Portfolio()
    portfolio.add(_position("AA", 1.0, 100.0))
    portfolio.add(_position("BB", 1.0, 100.0))
    portfolio.add(_position("CC", 1.0, 100.0))
    sectors = {"AA": "Tech", "BB": "Tech", "CC": "Energy"}
    exposure = sector_exposure(portfolio, sectors)
    by_sector = {e["sector"]: e["weight"] for e in exposure}
    assert by_sector["Tech"] == pytest.approx(2 / 3, abs=0.001)
    assert by_sector["Energy"] == pytest.approx(1 / 3, abs=0.001)


def test_risk_concentration_detects_single_name_risk():
    portfolio = Portfolio()
    portfolio.add(_position("ONE", 90.0, 100.0))
    portfolio.add(_position("TWO", 10.0, 100.0))
    risk = risk_concentration(portfolio)
    assert risk["largest_position_weight"] == pytest.approx(0.9)
    assert risk["single_name_risk"] is True
    assert risk["top_n_risk"] is True


# ----------------------------------------------------------------------
# Service (integration with a mocked analyzer)
# ----------------------------------------------------------------------
class MockAnalyzer:
    def __init__(self, result=None):
        self._result = result
        self.calls = 0

    def __call__(self, ticker):
        self.calls += 1
        return self._result


def _analysis_result(price=180.0, buffett=80, moat="STRONG", signal="BUY"):
    return {
        "ticker": "AAPL",
        "current_price": price,
        "buffett_score": buffett,
        "moat_analysis": {"moat_score": 75.0, "moat_type": moat},
        "composite_score": {"total_score": 85.0, "rating": "A", "confidence": "HIGH"},
        "quality_metrics": {},
        "delta_metrics": {},
        "buffett_breakdown": {
            "profitability": 80.0,
            "financial_strength": 80.0,
            "cash_generation": 80.0,
            "stability": 80.0,
        },
        "dcf_value": 200.0,
        "dcf_margin_of_safety": 0.30,
        "insight": [],
    }


def test_service_add_and_persist(tmp_path):
    repo = JsonPortfolioRepository(tmp_path / "p.json")
    service = PortfolioService(repo)
    service.add("AAPL", 10.0, 150.0, thesis="calidad")

    loaded = repo.load()
    assert loaded.position("AAPL").quantity == 10.0
    assert loaded.position("AAPL").avg_price == 150.0
    assert loaded.position("AAPL").thesis == "calidad"


def test_service_view_enriches_with_analytics(tmp_path):
    repo = JsonPortfolioRepository(tmp_path / "p.json")
    service = PortfolioService(repo, analyzer=MockAnalyzer(_analysis_result()))
    service.add("AAPL", 10.0, 150.0)

    positions = service.view()
    assert positions[0]["current_price"] == 180.0
    assert positions[0]["buffett_score"] == 80
    assert positions[0]["moat"] == "STRONG"
    assert positions[0]["signal"] == "BUY"
    assert positions[0]["opportunity_type"] in (
        "UNDERVALUED_QUALITY",
        "COMPOUNDERS",
        None,
    )


def test_service_view_keeps_stored_price_without_analyzer(tmp_path):
    repo = JsonPortfolioRepository(tmp_path / "p.json")
    service = PortfolioService(repo)
    service.add("AAPL", 10.0, 150.0)
    positions = service.view()
    assert positions[0]["current_price"] == 150.0
    assert positions[0]["buffett_score"] is None
    assert positions[0]["price_source"] == "stored"


def test_service_exit_records_realized_pnl(tmp_path):
    repo = JsonPortfolioRepository(tmp_path / "p.json")
    service = PortfolioService(repo)
    service.add("AAPL", 10.0, 100.0)
    closed = service.exit("AAPL", 130.0)
    assert closed.realized_pnl == 300.0
    assert service.view() == []


def test_service_performance_reports_allocation(tmp_path):
    repo = JsonPortfolioRepository(tmp_path / "p.json")
    service = PortfolioService(repo)
    service.add("AAA", 80.0, 100.0)
    service.add("BBB", 20.0, 100.0)

    perf = service.performance()
    assert perf["market_value"] == pytest.approx(10000.0)
    assert perf["allocation"]["risk"]["single_name_risk"] is True
