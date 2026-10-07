"""`interactive` — a one-level menu over the regular commands.

The menu never re-implements a command: it parses the typed arguments with
the command's own parser (so flags, help and validation stay identical)
and then dispatches in-process. ``q`` or Ctrl+C leaves the menu cleanly.
"""

from __future__ import annotations

import argparse
import shlex
from typing import NamedTuple

from rich.console import Group
from rich.prompt import Prompt
from rich.text import Text

from backend.services import cli_output
from cli.commands import (
    analyze_full,
    consensus,
    filings,
    financial_alerts,
    portfolio,
    screener,
)

_QUIT_KEY = "q"


class Entry(NamedTuple):
    """One menu row: the label, the command module and how to ask for its
    arguments (``prompt`` empty means the fixed ``argv`` is enough)."""

    label: str
    module: object  # a cli.commands module exposing register(subparsers)
    argv: tuple[str, ...] = ()
    prompt: str = ""
    default: str = ""

    def build(self, extra: list[str]):
        """Parse ``extra`` with the command's own parser and return args."""
        parser = argparse.ArgumentParser(prog="main.py")
        sub = parser.add_subparsers(dest="command")
        self.module.register(sub)
        name = next(iter(sub.choices))
        return parser.parse_args([name, *self.argv, *extra])


_ENTRIES: tuple[Entry, ...] = (
    Entry(
        "Full analysis",
        analyze_full,
        prompt="Ticker(s) and flags",
        default="AAPL --no-refresh",
    ),
    Entry(
        "Screener",
        screener,
        prompt="Filters and flags",
        default="--tickers AAPL,MSFT,GOOGL --top 5",
    ),
    Entry("Portfolio performance", portfolio, ("performance",)),
    Entry("Financial alerts", financial_alerts, prompt="Ticker", default="AAPL"),
    Entry("Consensus verdicts", consensus, prompt="Ticker", default="AAPL"),
    Entry("SEC filings", filings, prompt="Ticker", default="AAPL"),
)


def _keys() -> dict[str, Entry | None]:
    """Menu keys: ``1..n`` for the entries, ``q`` to quit."""
    mapping: dict[str, Entry | None] = {
        str(index): entry for index, entry in enumerate(_ENTRIES, 1)
    }
    mapping[_QUIT_KEY] = None
    return mapping


def _menu_body(mapping: dict[str, Entry | None]) -> Group:
    lines = []
    for key, entry in mapping.items():
        line = Text("  ")
        line.append(f"{key}", style=cli_output.ACCENT)
        line.append("   Quit" if entry is None else f"   {entry.label}")
        lines.append(line)
    return Group(*lines)


def _say_goodbye(console) -> None:
    console.print(Text("  Goodbye.", style=cli_output.MUTED))


def _ask_choice(console, mapping: dict[str, Entry | None]) -> str:
    console.print()
    cli_output.print_panel(
        cli_output.section_panel("Value Investing", _menu_body(mapping)),
        console=console,
        width=44,
    )
    return Prompt.ask(
        "  Choice",
        choices=list(mapping),
        default=_QUIT_KEY,
        console=console,
    )


def _run_entry(console, entry: Entry) -> bool:
    """Prompt for the arguments, parse them and run the command.

    Returns ``False`` when the arguments were rejected (argparse already
    printed the reason) so the menu is shown again.
    """
    extra: list[str] = []
    if entry.prompt:
        raw = Prompt.ask(f"  {entry.prompt}", default=entry.default, console=console)
        extra = shlex.split(raw)
    try:
        parsed = entry.build(extra)
    except SystemExit:
        console.print(Text("  (back to the menu)", style=cli_output.MUTED))
        return False
    parsed.func(parsed)
    return True


def _run(args) -> None:
    console = cli_output.get_console()
    mapping = _keys()
    try:
        while True:
            choice = _ask_choice(console, mapping)
            if choice == _QUIT_KEY or mapping.get(choice) is None:
                _say_goodbye(console)
                return
            _run_entry(console, mapping[choice])
    except (KeyboardInterrupt, EOFError):
        console.print()
        _say_goodbye(console)


def register(subparsers):
    p = subparsers.add_parser(
        "interactive",
        help="Menu mode: pick a command, type its arguments, run it",
        description=(
            "Shows a menu of the regular commands, asks for their arguments "
            "and runs them in-process. Press q or Ctrl+C to leave."
        ),
    )
    p.set_defaults(func=_run)
