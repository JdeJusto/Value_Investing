"""Portfolio sector enrichment (FDB → GICS) and clarified columns."""

from __future__ import annotations

from argparse import Namespace

import pytest

from backend.portfolio.portfolio_repository import JsonPortfolioRepository
from backend.portfolio.portfolio_service import PortfolioService
from backend.portfolio.sectors import canonical_sector
from cli.commands import portfolio as portfolio_cli


def test_canonical_sector_maps_yahoo_labels():
    assert canonical_sector("Consumer Defensive") == "Consumer Staples"
    assert canonical_sector("Consumer Cyclical") == "Consumer Discretionary"
    assert canonical_sector("Technology") == "Information Technology"
    assert canonical_sector("Communication Services") == "Communication Services"
    assert canonical_sector(None) is None


def test_portfolio_view_includes_canonical_sector(tmp_path):
    repository = JsonPortfolioRepository(tmp_path / "portfolio.json")
    service = PortfolioService(
        repository,
        sector_lookup={
            "HSY": "Consumer Defensive",
            "PDD": "Consumer Cyclical",
            "CMCSA": "Communication Services",
        }.get,
    )
    service.add("HSY", 10, 100.0)
    service.add("PDD", 5, 50.0)
    service.add("CMCSA", 20, 30.0)

    sectors = {row["ticker"]: row["sector"] for row in service.view()}

    assert sectors == {
        "HSY": "Consumer Staples",
        "PDD": "Consumer Discretionary",
        "CMCSA": "Communication Services",
    }


def test_sector_exposure_groups_by_real_sector(tmp_path):
    repository = JsonPortfolioRepository(tmp_path / "portfolio.json")
    service = PortfolioService(
        repository,
        sector_lookup={
            "HSY": "Consumer Defensive",
            "PDD": "Consumer Cyclical",
        }.get,
    )
    service.add("HSY", 10, 100.0)
    service.add("PDD", 5, 50.0)

    exposure = {
        row["sector"]: row["weight"]
        for row in service.performance()["allocation"]["sector_exposure"]
    }

    assert exposure == {
        "Consumer Staples": pytest.approx(0.8),
        "Consumer Discretionary": pytest.approx(0.2),
    }
    assert "N/A" not in exposure


def test_unknown_sector_falls_back_to_unknown(tmp_path):
    repository = JsonPortfolioRepository(tmp_path / "portfolio.json")
    service = PortfolioService(repository, sector_lookup=lambda _ticker: None)
    service.add("ZZZZ", 10, 100.0)

    view = service.view()
    exposure = service.performance()["allocation"]["sector_exposure"]

    assert view[0]["sector"] == "Unknown"
    assert exposure[0]["sector"] == "Unknown"


def test_view_renders_sector_and_clarified_headers(monkeypatch, capsys):
    class _Service:
        def view(self):
            return [
                {
                    "ticker": "HSY",
                    "sector": "Consumer Staples",
                    "quantity": 10,
                    "current_price": 200.0,
                    "unrealized_return": 0.1,
                    "buffett_score": 72.0,
                    "moat": "WIDE",
                    "signal": "HOLD",
                    "opportunity_type": None,
                    "thesis": "Brand moat",
                }
            ]

    monkeypatch.setattr(portfolio_cli, "build_portfolio_service", lambda: _Service())
    portfolio_cli._view(Namespace())

    out = capsys.readouterr().out
    assert "Sector" in out
    assert "Consumer Staples" in out
    assert "Buffett score" in out
    assert "Signal (screener)" in out
    assert "Brand moat" in out
