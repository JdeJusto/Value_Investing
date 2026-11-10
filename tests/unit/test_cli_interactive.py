"""Synthwave interactive menu: navigation, colors, width and dispatch."""

from __future__ import annotations

import argparse
import io
import shlex
import sys
import types

import pytest

from backend.services import cli_output
from cli.commands import interactive

ESC = "\x1b"


@pytest.fixture(autouse=True)
def _clean_color_state():
    cli_output.reset_no_color()
    yield
    cli_output.reset_no_color()


def _stdin(monkeypatch, *lines: str) -> None:
    monkeypatch.setattr(
        sys, "stdin", io.StringIO("".join(f"{line}\n" for line in lines))
    )


def _fake_module(ran: list) -> types.SimpleNamespace:
    def register(sub):
        parser = sub.add_parser("fake-cmd", help="a command for the tests")
        parser.add_argument("ticker")
        parser.set_defaults(func=lambda args: ran.append(args.ticker))

    return types.SimpleNamespace(register=register)


def _capture(monkeypatch, capsys, *lines: str) -> str:
    _stdin(monkeypatch, *lines)
    interactive._run(None)
    return capsys.readouterr().out


def test_home_shows_categories_and_hints(monkeypatch, capsys):
    out = _capture(monkeypatch, capsys, "q")

    assert "V A L U E   I N V E S T I N G" in out
    for title in ("ANALYSIS", "RANKING & SCREENING", "PORTFOLIO · DATA · BACKTESTING"):
        assert title in out
    assert "[s] Search" in out
    assert "[q] Quit" in out
    assert "Goodbye." in out
    assert ESC not in out  # capsys is not a TTY -> plain fallback


def test_analysis_submenu_and_back_home(monkeypatch, capsys):
    out = _capture(monkeypatch, capsys, "1", "h", "q")

    assert "Scorecard" in out
    assert "Balance" in out
    assert "Full analysis" in out
    assert (
        out.count("V A L U E   I N V E S T I N G") == 3
    )  # home -> submenu -> home -> exit


def test_colors_are_emitted_when_enabled(monkeypatch, capsys):
    monkeypatch.setattr(interactive, "_colors", lambda: True)
    out = _capture(monkeypatch, capsys, "q")

    assert ESC in out
    assert "\033[38;5;51m" in out  # cyan
    assert "\033[38;5;205m" in out  # pink


def test_no_color_has_no_ansi(monkeypatch, capsys):
    monkeypatch.setattr(interactive, "_colors", lambda: False)
    out = _capture(monkeypatch, capsys, "q")

    assert ESC not in out
    assert "+- ANALYSIS" in out


def test_submenu_dispatches_an_action(monkeypatch, capsys):
    ran: list = []
    action = interactive.Action(
        "Fake command",
        "test",
        _fake_module(ran),
        prompt="Ticker",
        default="AAPL",
    )
    category = interactive.Category("fake", "Fake", "test", (action,))
    monkeypatch.setitem(interactive._CATEGORIES, "fake", category)
    _stdin(monkeypatch, "4", "1", "MSFT", "q")
    interactive._run(None)

    assert ran == ["MSFT"]


def test_five_routes_parse_their_defaults():
    wanted = {
        "Scorecard",
        "Rank top N",
        "Portfolio view",
        "Refresh",
        "Backtest",
    }
    actions = [
        action
        for category in interactive._CATEGORIES.values()
        for action in category.actions
        if action.label in wanted
    ]
    assert len(actions) == 5
    for action in actions:
        extra = shlex.split(action.default) if action.prompt else []
        args = action.build(extra)
        assert callable(args.func), action.label


def test_rank_default_is_the_reported_top_20_task():
    action = next(
        action
        for action in interactive._ANALYSIS.actions + interactive._RANKING.actions
        if action.label == "Rank top N"
    )
    args = action.build(shlex.split(action.default))

    assert args.by == "graham"
    assert args.top == 20
    assert args.universe == "sp500"


def test_search_and_help_from_home(monkeypatch, capsys):
    _stdin(monkeypatch, "s", "methodology", "?", "q")
    interactive._run(None)

    out = capsys.readouterr().out
    assert "Top matches for 'methodology'" in out
    assert "vi rank" in out
    assert "Common tasks:" in out


def test_width_respects_a_narrow_terminal(monkeypatch, capsys):
    monkeypatch.setenv("COLUMNS", "50")
    out = _capture(monkeypatch, capsys, "q")

    plain = [line for line in out.splitlines() if line.strip()]
    assert max(len(line) for line in plain) <= 52


def test_empty_input_quits(monkeypatch, capsys):
    out = _capture(monkeypatch, capsys, "")
    assert "Goodbye." in out


def test_interactive_is_registered_as_a_command():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    interactive.register(sub)
    assert sub.choices["interactive"].get_default("func") is interactive._run
