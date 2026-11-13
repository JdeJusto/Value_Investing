"""End-to-end guided flows for the interactive menu.

Every test drives the real menu loop with a fixed answer sequence and patches
``_execute`` so the parsed argparse namespace can be asserted without running
the command.
"""

from __future__ import annotations

import argparse

import pytest

from cli.commands import interactive


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


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------
def test_scorecard_flow(monkeypatch, capsys):
    calls, out = _drive(monkeypatch, capsys, "1", "1", "AAPL", "n", "q")

    assert len(calls) == 1
    assert calls[0].command == "scorecard"
    assert calls[0].ticker == "AAPL"
    assert calls[0].json is False
    assert "Running: vi scorecard AAPL" in out
    assert "Show JSON output?" in out


def test_scorecard_json_flow(monkeypatch, capsys):
    calls, _out = _drive(monkeypatch, capsys, "1", "1", "MSFT", "y", "q")

    assert calls[0].ticker == "MSFT"
    assert calls[0].json is True


def test_balance_flow_asks_for_years(monkeypatch, capsys):
    calls, out = _drive(monkeypatch, capsys, "1", "2", "AAPL", "3", "q")

    assert calls[0].command == "financials"
    assert calls[0].ticker == "AAPL"
    assert calls[0].years == 3
    assert "How many fiscal years?" in out


def test_methodology_details_flow(monkeypatch, capsys):
    calls, _out = _drive(monkeypatch, capsys, "1", "3", "4", "q")

    assert calls[0].command == "methodologies"
    assert calls[0].methodology_command == "show"
    # argparse stores the show subcommand's methodology name on the namespace.
    assert any(getattr(calls[0], name, None) == "graham" for name in vars(calls[0]))


def test_dcf_flow(monkeypatch, capsys):
    calls, _out = _drive(monkeypatch, capsys, "1", "4", "AAPL", "q")
    assert calls[0].command == "dcf"
    assert calls[0].ticker == "AAPL"


def test_compare_flow(monkeypatch, capsys):
    calls, _out = _drive(monkeypatch, capsys, "1", "5", "AAPL", "q")
    assert calls[0].command == "compare-methodologies"
    assert calls[0].ticker == "AAPL"


def test_full_analysis_flow(monkeypatch, capsys):
    calls, _out = _drive(monkeypatch, capsys, "1", "6", "AAPL MSFT", "n", "q")

    assert calls[0].command == "analyze-full"
    assert calls[0].tickers == ["AAPL", "MSFT"]
    assert calls[0].no_prices is True


# ---------------------------------------------------------------------------
# ranking
# ---------------------------------------------------------------------------
def test_rank_by_flow(monkeypatch, capsys):
    calls, out = _drive(monkeypatch, capsys, "2", "1", "4", "20", "2", "q")

    assert calls[0].command == "rank"
    assert calls[0].by == "graham"
    assert calls[0].top == 20
    assert calls[0].universe == "sp500"
    assert "How many top tickers?" in out
    assert "Universe" in out


def test_rank_combine_flow(monkeypatch, capsys):
    calls, out = _drive(monkeypatch, capsys, "2", "2", "4,7", "1", "10", "1", "q")

    assert calls[0].command == "rank"
    assert calls[0].combine == "graham,lynch_garp"
    assert calls[0].strategy == "and"
    assert calls[0].top == 10
    assert calls[0].universe == "demo"
    assert "Which methodologies?" in out
    assert "Strategy" in out


def test_consensus_flow(monkeypatch, capsys):
    calls, _out = _drive(monkeypatch, capsys, "2", "3", "AAPL", "1", "q")

    assert calls[0].command == "consensus"
    assert calls[0].ticker == "AAPL"
    assert calls[0].universe == "demo"


def test_consensus_ranking_flow(monkeypatch, capsys):
    calls, _out = _drive(monkeypatch, capsys, "2", "4", "2", "5", "q")

    assert calls[0].command == "consensus-ranking"
    assert calls[0].universe == "sp500"
    assert calls[0].top == 5


def test_screener_flow_with_methodology_filter(monkeypatch, capsys):
    calls, out = _drive(monkeypatch, capsys, "2", "5", "2", "1", "4", "1", "10", "q")

    assert calls[0].command == "screener"
    assert calls[0].universe == "demo"
    assert calls[0].methodology == ["graham:BUY"]
    assert calls[0].top == 10
    assert "Filter by" in out
    assert "Verdict" in out


def test_screener_without_filter(monkeypatch, capsys):
    calls, _out = _drive(monkeypatch, capsys, "2", "5", "1", "1", "5", "q")

    assert calls[0].methodology is None
    assert calls[0].top == 5


# ---------------------------------------------------------------------------
# portfolio / data / backtesting
# ---------------------------------------------------------------------------
def test_portfolio_view_has_no_prompts(monkeypatch, capsys):
    calls, out = _drive(monkeypatch, capsys, "3", "1", "q")

    assert calls[0].command == "portfolio"
    assert calls[0].action == "view"
    assert "Ticker" not in out


def test_performance_has_no_prompts(monkeypatch, capsys):
    calls, _out = _drive(monkeypatch, capsys, "3", "2", "q")

    assert calls[0].command == "portfolio"
    assert calls[0].action == "performance"


def test_refresh_flow_facts_only(monkeypatch, capsys):
    calls, out = _drive(monkeypatch, capsys, "3", "7", "AAPL", "2", "q")

    assert calls[0].command == "refresh"
    assert calls[0].ticker == "AAPL"
    assert calls[0].facts_only is True
    assert calls[0].prices_only is False
    assert "Both facts and prices" in out


def test_refresh_flow_prices_only(monkeypatch, capsys):
    calls, _out = _drive(monkeypatch, capsys, "3", "7", "AAPL", "3", "q")
    assert calls[0].prices_only is True


def test_data_status_flow(monkeypatch, capsys):
    calls, _out = _drive(monkeypatch, capsys, "3", "8", "AAPL", "q")
    assert calls[0].command == "data-status"
    assert calls[0].tickers == ["AAPL"]


def test_load_data_flow(monkeypatch, capsys):
    calls, _out = _drive(monkeypatch, capsys, "3", "9", "AAPL", "8", "n", "q")

    assert calls[0].command == "load-data"
    assert calls[0].tickers == ["AAPL"]
    assert calls[0].years == 8
    assert calls[0].force is False


def test_filings_flow(monkeypatch, capsys):
    calls, _out = _drive(monkeypatch, capsys, "3", "10", "AAPL", "10", "q")
    assert calls[0].command == "filings"
    assert calls[0].ticker == "AAPL"
    assert calls[0].limit == 10


def test_alerts_flow(monkeypatch, capsys):
    calls, _out = _drive(monkeypatch, capsys, "3", "11", "AAPL", "q")
    assert calls[0].command == "financial-alerts"
    assert calls[0].ticker == "AAPL"


def test_backtest_flow(monkeypatch, capsys):
    calls, out = _drive(monkeypatch, capsys, "3", "12", "4", "10", "400", "n", "q")

    assert calls[0].command == "backtest"
    assert calls[0].methodology == ["graham"]
    assert calls[0].years == 10
    assert calls[0].limit == 400
    assert calls[0].equal_weight is False
    assert "Which methodology?" in out
    assert "How many years?" in out
    assert "How many tickers (limit)?" in out
    assert "Use equal-weight (legacy)?" in out


def test_backtest_excludes_greenblatt(monkeypatch, capsys):
    calls, out = _drive(monkeypatch, capsys, "3", "12", "7", "5", "50", "y", "q")

    assert calls[0].methodology == ["marks"]
    assert calls[0].equal_weight is True
    assert "greenblatt" not in out
    assert "How many years?" in out


# ---------------------------------------------------------------------------
# cancellation and advanced mode
# ---------------------------------------------------------------------------
def test_cancel_at_ticker_returns_to_the_menu(monkeypatch, capsys):
    calls, out = _drive(monkeypatch, capsys, "1", "1", "q", "h", "q")

    assert calls == []
    assert "(back to the menu)" in out


def test_cancel_at_integer_returns_to_the_menu(monkeypatch, capsys):
    calls, out = _drive(monkeypatch, capsys, "1", "2", "AAPL", "back", "h", "q")

    assert calls == []
    assert "(back to the menu)" in out


def test_advanced_mode_runs_a_raw_command(monkeypatch, capsys):
    calls, out = _drive(
        monkeypatch,
        capsys,
        "x",
        "backtest --methodology graham --years 10",
        "q",
    )

    assert calls[0].command == "backtest"
    assert calls[0].methodology == ["graham"]
    assert calls[0].years == 10
    assert "Running: vi backtest --methodology graham --years 10" in out


def test_advanced_mode_ignores_an_empty_command(monkeypatch, capsys):
    calls, _out = _drive(monkeypatch, capsys, "x", "", "q")
    assert calls == []


def test_advanced_mode_rejects_unknown_commands(monkeypatch, capsys):
    calls, out = _drive(monkeypatch, capsys, "x", "nope --flag", "q")

    assert calls == []
    assert "Unknown command: nope" in out


# ---------------------------------------------------------------------------
# home / navigation
# ---------------------------------------------------------------------------
def test_home_shows_the_advanced_hint(monkeypatch, capsys):
    _calls, out = _drive(monkeypatch, capsys, "q")
    assert "[x] Advanced" in out


def test_every_menu_action_has_a_guided_flow():
    for category in interactive._CATEGORIES.values():
        for action in category.actions:
            assert action.guide is not None, action.label


def test_guided_flows_do_not_ask_for_raw_flags(monkeypatch, capsys):
    """The old 'Methodology and flags [...]' prompt is gone."""
    _calls, out = _drive(monkeypatch, capsys, "3", "12", "4", "5", "50", "n", "q")
    assert "flags" not in out.lower().replace("--flags", "")
