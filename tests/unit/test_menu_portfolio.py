"""Portfolio mutations from the interactive menu (add/remove/exit)."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

import pytest

from backend.portfolio.models import Portfolio, Position
from backend.portfolio.portfolio_repository import JsonPortfolioRepository
from cli.commands import interactive
from cli.menu_prompts import PromptCancelled, ask_float


def _drive(monkeypatch, capsys, *answers: str):
    responses = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))
    calls: list[argparse.Namespace] = []
    monkeypatch.setattr(interactive, "_execute", lambda parsed: calls.append(parsed))
    interactive._run(None)
    return calls, capsys.readouterr().out


@pytest.fixture(autouse=True)
def _known_tickers(monkeypatch):
    monkeypatch.setattr(
        "backend.services.ticker_resolver.resolve_ticker",
        lambda ticker: ticker if ticker in {"AAPL", "MSFT", "VICI"} else None,
    )


@pytest.fixture
def portfolio_path(tmp_path, monkeypatch):
    path = tmp_path / "portfolio.json"
    monkeypatch.setenv("PORTFOLIO_PATH", str(path))
    return path


def _write_positions(path, tickers):
    positions = [
        Position(
            ticker=ticker,
            quantity=10,
            avg_price=100.0,
            current_price=110.0,
            entry_date=datetime.now(UTC),
        )
        for ticker in tickers
    ]
    JsonPortfolioRepository(path).save(Portfolio(positions=positions))


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------
def test_add_position_flow(monkeypatch, capsys, portfolio_path):
    calls, out = _drive(monkeypatch, capsys, "3", "3", "AAPL", "10", "185.50", "n", "q")

    assert len(calls) == 1
    assert calls[0].command == "portfolio"
    assert calls[0].action == "add"
    assert calls[0].ticker == "AAPL"
    assert calls[0].quantity == 10.0
    assert calls[0].avg_price == 185.5
    assert calls[0].date is None
    assert "Add position" in out
    assert "Running: vi portfolio add AAPL 10 185.5" in out


def test_add_position_with_date(monkeypatch, capsys, portfolio_path):
    calls, _out = _drive(
        monkeypatch,
        capsys,
        "3",
        "3",
        "AAPL",
        "10",
        "185.5",
        "y",
        "2024-01-02",
        "q",
    )

    assert calls[0].date == datetime.fromisoformat("2024-01-02")


def test_add_cancel_at_ticker(monkeypatch, capsys, portfolio_path):
    calls, out = _drive(monkeypatch, capsys, "3", "3", "q", "q")

    assert calls == []
    assert "(back to the menu)" in out


def test_add_existing_position_asks_to_average(monkeypatch, capsys, portfolio_path):
    _write_positions(portfolio_path, ["AAPL"])

    calls, out = _drive(monkeypatch, capsys, "3", "3", "AAPL", "n", "q")

    assert calls == []
    assert "already exists" in out
    assert "Average into the position?" in out


def test_add_existing_position_averages_when_confirmed(
    monkeypatch, capsys, portfolio_path
):
    _write_positions(portfolio_path, ["AAPL"])

    calls, _out = _drive(
        monkeypatch, capsys, "3", "3", "AAPL", "y", "5", "200", "n", "q"
    )

    assert calls[0].quantity == 5.0
    assert calls[0].avg_price == 200.0


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------
def test_remove_empty_portfolio(monkeypatch, capsys, portfolio_path):
    calls, out = _drive(monkeypatch, capsys, "3", "4", "q")

    assert calls == []
    assert "Portfolio is empty." in out


def test_remove_position_flow(monkeypatch, capsys, portfolio_path):
    _write_positions(portfolio_path, ["AAPL", "MSFT"])

    calls, out = _drive(monkeypatch, capsys, "3", "4", "2", "y", "q")

    assert calls[0].command == "portfolio"
    assert calls[0].action == "remove"
    assert calls[0].ticker == "MSFT"
    assert "Remove which position?" in out
    assert "Running: vi portfolio remove MSFT" in out


def test_remove_position_can_be_cancelled(monkeypatch, capsys, portfolio_path):
    _write_positions(portfolio_path, ["AAPL"])

    calls, out = _drive(monkeypatch, capsys, "3", "4", "1", "n", "q")

    assert calls == []
    assert "Cancelled." in out


# ---------------------------------------------------------------------------
# exit
# ---------------------------------------------------------------------------
def test_exit_position_flow(monkeypatch, capsys, portfolio_path):
    _write_positions(portfolio_path, ["AAPL"])

    calls, out = _drive(monkeypatch, capsys, "3", "5", "1", "200", "y", "q")

    assert calls[0].command == "portfolio"
    assert calls[0].action == "exit"
    assert calls[0].ticker == "AAPL"
    assert calls[0].price == 200.0
    assert "Exit which position?" in out
    assert "Running: vi portfolio exit AAPL 200.0" in out


def test_exit_position_can_be_cancelled(monkeypatch, capsys, portfolio_path):
    _write_positions(portfolio_path, ["AAPL"])

    calls, out = _drive(monkeypatch, capsys, "3", "5", "1", "200", "n", "q")

    assert calls == []
    assert "Cancelled." in out


# ---------------------------------------------------------------------------
# numbering and ask_float
# ---------------------------------------------------------------------------
def test_portfolio_menu_numbering_is_stable():
    _text, choices = interactive._render("data")
    labels = [action.label for action in interactive._DATA.actions]

    assert len(choices) == 11
    assert labels[:8] == [
        "Portfolio view",
        "Performance",
        "Add position",
        "Remove position",
        "Exit position",
        "Refresh",
        "Data status",
        "Load data",
    ]
    assert labels[8:] == ["Filings", "Financial alerts", "Backtest"]


def test_ask_float_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    assert ask_float("Cost", default=12.5) == 12.5


def test_ask_float_range_retries(monkeypatch):
    responses = iter(["0", "5"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))
    assert ask_float("Shares", min_val=1) == 5.0


def test_ask_float_invalid_retries(monkeypatch):
    responses = iter(["abc", "2.5"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))
    assert ask_float("Cost") == 2.5


def test_ask_float_cancel(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "q")
    with pytest.raises(PromptCancelled):
        ask_float("Cost")
