"""CLI `interactive`: one-level menu, in-process dispatch, clean Ctrl+C."""

from __future__ import annotations

import argparse
import io
import shlex
import sys
import types
from argparse import Namespace

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
    """Feed ``lines`` to the prompts (rich reads them through input())."""
    monkeypatch.setattr(
        sys, "stdin", io.StringIO("".join(f"{line}\n" for line in lines))
    )


def _fake_module(ran: list, *, required: bool = True) -> types.SimpleNamespace:
    """A stand-in command module exposing ``register(subparsers)``."""

    def register(sub):
        parser = sub.add_parser("fake-cmd", help="a command for the tests")
        if required:
            parser.add_argument("ticker")
        parser.set_defaults(func=lambda args: ran.append(getattr(args, "ticker", None)))

    return types.SimpleNamespace(register=register)


def test_menu_lists_every_entry_without_ansi(monkeypatch, capsys):
    _stdin(monkeypatch, "q")
    interactive._run(Namespace())

    out = capsys.readouterr().out
    for entry in interactive._ENTRIES:
        assert entry.label in out
    assert "Value Investing" in out  # menu panel title
    assert "Goodbye." in out
    assert ESC not in out


def test_empty_input_quits_with_the_default(monkeypatch, capsys):
    _stdin(monkeypatch, "")
    interactive._run(Namespace())
    assert "Goodbye." in capsys.readouterr().out


def test_menu_rejects_an_unknown_key_and_asks_again(monkeypatch, capsys):
    _stdin(monkeypatch, "zz", "q")
    interactive._run(Namespace())

    captured = capsys.readouterr()
    assert "Please select one of the available options" in captured.out
    assert captured.out.count("Value Investing") == 1  # rich re-asks, no redraw
    assert "Goodbye." in captured.out


def test_entries_parse_their_default_arguments():
    """Every shipped entry parses with its own command's real parser."""
    for entry in interactive._ENTRIES:
        extra = shlex.split(entry.default) if entry.prompt else []
        args = entry.build(extra)
        assert callable(args.func), entry.label


def test_entry_with_a_fixed_action_skips_the_prompt():
    portfolio = next(
        e for e in interactive._ENTRIES if e.label == "Portfolio performance"
    )
    assert portfolio.prompt == ""
    args = portfolio.build([])
    assert args.action == "performance"
    assert callable(args.func)


def test_choice_runs_the_command_in_process(monkeypatch, capsys):
    ran: list = []
    monkeypatch.setattr(interactive, "_ENTRIES", (_entry(ran),))
    _stdin(monkeypatch, "1", "AAPL", "q")

    interactive._run(Namespace())

    assert ran == ["AAPL"]  # parsed and dispatched without a subprocess
    assert "Goodbye." in capsys.readouterr().out


def test_bad_arguments_return_to_the_menu(monkeypatch, capsys):
    ran: list = []
    monkeypatch.setattr(interactive, "_ENTRIES", (_entry(ran),))
    _stdin(monkeypatch, "1", "--bogus", "q")

    interactive._run(Namespace())

    captured = capsys.readouterr()
    assert ran == []  # nothing ran
    assert "(back to the menu)" in captured.out
    assert captured.out.count("Value Investing") == 2
    assert "Goodbye." in captured.out


def test_ctrl_c_leaves_the_menu_cleanly(monkeypatch, capsys):
    class _Interrupt(io.StringIO):
        def readline(self, *args):  # pragma: no cover - exercised below
            raise KeyboardInterrupt

    monkeypatch.setattr(sys, "stdin", _Interrupt())

    interactive._run(Namespace())  # must not raise

    out = capsys.readouterr().out
    assert "Goodbye." in out
    assert "Traceback" not in out


def test_ctrl_c_while_asking_for_arguments_also_leaves(monkeypatch, capsys):
    ran: list = []
    monkeypatch.setattr(interactive, "_ENTRIES", (_entry(ran),))

    class _InterruptAfter(io.StringIO):
        def __init__(self, lines):
            super().__init__(lines)
            self.calls = 0

        def readline(self, *args):
            self.calls += 1
            if self.calls > 1:
                raise KeyboardInterrupt
            return super().readline(*args)

    monkeypatch.setattr(sys, "stdin", _InterruptAfter("1\n"))

    interactive._run(Namespace())  # menu key accepted, then Ctrl+C at the prompt

    assert ran == []
    assert "Goodbye." in capsys.readouterr().out


def test_interactive_is_registered_as_a_command():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    interactive.register(sub)
    assert sub.choices["interactive"].get_default("func") is interactive._run


def _entry(ran: list) -> interactive.Entry:
    return interactive.Entry(
        "Fake command", _fake_module(ran), prompt="Ticker", default="AAPL"
    )


def test_run_menu_opens_the_menu(monkeypatch, capsys):
    _stdin(monkeypatch, "q")

    interactive.run_menu()

    assert "Value Investing" in capsys.readouterr().out


def test_cli_without_arguments_opens_the_menu(monkeypatch, capsys):
    from cli.main import main

    monkeypatch.setattr(sys, "argv", ["main.py"])
    _stdin(monkeypatch, "q")

    main()

    out = capsys.readouterr().out
    assert "Value Investing" in out
    assert "usage:" not in out


def test_cli_help_still_prints_usage_without_the_menu(monkeypatch, capsys):
    from cli.main import main

    monkeypatch.setattr(sys, "argv", ["main.py", "--help"])
    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    assert "usage:" in out
    assert "Choice" not in out


def test_menu_shows_categories(monkeypatch, capsys):
    _stdin(monkeypatch, "q")

    interactive._run(Namespace())

    out = capsys.readouterr().out
    for category in (
        "ANALYSIS",
        "RANKING & SCREENING",
        "PORTFOLIO",
        "DATA & REFRESH",
        "BACKTESTING",
        "HELP",
    ):
        assert category in out


def test_menu_help_option_prints_the_catalog(monkeypatch, capsys):
    _stdin(monkeypatch, "?", "q")

    interactive._run(Namespace())

    out = capsys.readouterr().out
    assert "Common tasks:" in out
    assert "Search: vi help --search" in out


def test_menu_search_finds_rank(monkeypatch, capsys):
    _stdin(monkeypatch, "s", "methodology", "q")

    interactive._run(Namespace())

    out = capsys.readouterr().out
    assert "Top matches for 'methodology'" in out
    assert "vi rank" in out


def test_rank_entry_defaults_to_top_20():
    entry = next(e for e in interactive._ENTRIES if e.label == "Top N by methodology")
    args = entry.build(shlex.split(entry.default))

    assert args.by == "graham"
    assert args.top == 20
    assert callable(args.func)


def test_five_menu_routes_parse_and_dispatch():
    wanted = {
        "Scorecard (six dimensions)",
        "Top N by methodology",
        "Portfolio view",
        "Refresh a ticker (facts + prices)",
        "Backtest a methodology (PoC)",
    }
    entries = [entry for entry in interactive._ENTRIES if entry.label in wanted]
    assert len(entries) == 5
    for entry in entries:
        extra = shlex.split(entry.default) if entry.prompt else []
        args = entry.build(extra)
        assert callable(args.func), entry.label
