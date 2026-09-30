"""Regression: every analyze command rejects unknown tickers with exit 2.

The resolver is stubbed, so no database is touched. The valid-ticker path
patches the repository/price stubs and the refresh helper, mirroring
test_cli_no_refresh.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from cli.main import main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

COMMANDS = [
    "analyze-graham",
    "analyze-graham-dodd",
    "analyze-buffett-classic",
    "analyze-buffett-clark",
    "analyze-fisher-quant",
    "analyze-lynch-garp",
    "analyze-full",
]


class _Prices:
    def get_current_price(self, ticker):
        return 100.0


class _Repo:
    def get_best_available(self, ticker):
        rows = json.loads((FIXTURES / "graham_pass.json").read_text())
        return [NormalizedFinancials.from_dict(row) for row in rows]


def _stub_data_sources(monkeypatch):
    monkeypatch.setattr("backend.app.cli.build_financial_repository", lambda: _Repo())
    monkeypatch.setattr(
        "backend.services.price_service.get_price_service", lambda: _Prices()
    )
    monkeypatch.setattr("backend.app.cli.refresh_analysis_inputs", lambda *a, **k: None)
    monkeypatch.setattr(
        "cli.commands.analyze_full.refresh_analysis_inputs", lambda *a, **k: None
    )

    class _Service:
        def _analyze_ticker(self, ticker, no_prices=False):
            return None

    monkeypatch.setattr(
        "cli.commands.analyze_full.build_screener_service", lambda: _Service()
    )


@pytest.mark.parametrize("command", COMMANDS)
def test_unknown_ticker_exits_2(command, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", command, "ZZZZ"])
    monkeypatch.setattr(
        "backend.services.ticker_resolver.resolve_ticker", lambda ticker: None
    )
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2
    out = capsys.readouterr().out
    assert "not found in Financial-DataBase" in out
    assert "daily_workflow --refresh" in out


@pytest.mark.parametrize("command", COMMANDS)
def test_valid_ticker_does_not_exit(command, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", command, "AAPL", "--no-refresh"])
    monkeypatch.setattr(
        "backend.services.ticker_resolver.resolve_ticker",
        lambda ticker: ticker.upper(),
    )
    _stub_data_sources(monkeypatch)
    main()  # no SystemExit
    assert capsys.readouterr().out
