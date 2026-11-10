"""`interactive` — categorized menu over the regular commands.

The menu never re-implements a command: it parses the typed arguments with the
command's own parser (so flags, help and validation stay identical) and then
dispatches in-process. ``q``/Ctrl+C leaves; ``?`` prints the grouped help and
``s`` searches the command catalog.
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
    backtest,
    compare_methodologies,
    consensus,
    consensus_ranking,
    data_status,
    dcf,
    filings,
    financial_alerts,
    financials,
    load_data,
    methodologies,
    portfolio,
    rank,
    refresh,
    scorecard,
    screener,
)
from cli.help_utils import render_help_footer, render_search_results

_QUIT_KEY = "q"
_HELP_KEY = "?"
_SEARCH_KEY = "s"


class Entry(NamedTuple):
    """One menu row: the label, the command module and how to ask for its
    arguments (``prompt`` empty means the fixed ``argv`` is enough)."""

    label: str
    module: object  # a cli.commands module exposing register(subparsers)
    group: str = "Analysis"
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
    # --- Analysis ---------------------------------------------------------
    Entry(
        "Scorecard (six dimensions)",
        scorecard,
        "Analysis",
        prompt="Ticker and flags",
        default="AAPL",
    ),
    Entry(
        "Balance sheet (T-view)",
        financials,
        "Analysis",
        prompt="Ticker",
        default="AAPL",
    ),
    Entry(
        "Methodology details",
        methodologies,
        "Analysis",
        argv=("show",),
        prompt="Methodology name",
        default="graham",
    ),
    Entry(
        "DCF valuation",
        dcf,
        "Analysis",
        prompt="Ticker and flags",
        default="AAPL",
    ),
    Entry(
        "Compare all methodologies",
        compare_methodologies,
        "Analysis",
        prompt="Ticker",
        default="AAPL",
    ),
    Entry(
        "Full analysis report",
        analyze_full,
        "Analysis",
        prompt="Ticker(s) and flags",
        default="AAPL --no-prices",
    ),
    # --- Ranking & screening ---------------------------------------------
    Entry(
        "Top N by methodology",
        rank,
        "Ranking & screening",
        prompt="Methodology and flags",
        default="--by graham --universe sp500 --top 20",
    ),
    Entry(
        "Combine methodologies (AND/OR)",
        rank,
        "Ranking & screening",
        prompt="Methodologies and flags",
        default="--combine graham,lynch_garp --strategy and --top 20",
    ),
    Entry(
        "Consensus for a ticker",
        consensus,
        "Ranking & screening",
        prompt="Ticker",
        default="AAPL",
    ),
    Entry(
        "Consensus ranking",
        consensus_ranking,
        "Ranking & screening",
        prompt="Flags",
        default="--universe sp500 --top 10",
    ),
    Entry(
        "Screener with filters",
        screener,
        "Ranking & screening",
        prompt="Filters and flags",
        default="--tickers AAPL,MSFT,GOOGL --top 5 --no-refresh",
    ),
    # --- Portfolio --------------------------------------------------------
    Entry("Portfolio view", portfolio, "Portfolio", argv=("view",)),
    Entry("Portfolio performance", portfolio, "Portfolio", argv=("performance",)),
    # --- Data & refresh ---------------------------------------------------
    Entry(
        "Refresh a ticker (facts + prices)",
        refresh,
        "Data & refresh",
        prompt="Ticker",
        default="AAPL",
    ),
    Entry(
        "Data status",
        data_status,
        "Data & refresh",
        prompt="Ticker",
        default="AAPL",
    ),
    Entry(
        "Load data (download + store)",
        load_data,
        "Data & refresh",
        prompt="Ticker and flags",
        default="AAPL",
    ),
    Entry(
        "SEC filings",
        filings,
        "Data & refresh",
        prompt="Ticker",
        default="AAPL",
    ),
    Entry(
        "Financial alerts",
        financial_alerts,
        "Data & refresh",
        prompt="Ticker",
        default="AAPL",
    ),
    # --- Backtesting ------------------------------------------------------
    Entry(
        "Backtest a methodology (PoC)",
        backtest,
        "Backtesting",
        prompt="Methodology and flags",
        default="--methodology graham --years 5",
    ),
)


def _keys() -> dict[str, Entry | None]:
    """Menu keys: ``1..n`` for the entries, ``q`` to quit."""
    mapping: dict[str, Entry | None] = {
        str(index): entry for index, entry in enumerate(_ENTRIES, 1)
    }
    mapping[_QUIT_KEY] = None
    return mapping


def _menu_body(mapping: dict[str, Entry | None]) -> Group:
    lines: list[Text] = []
    current_group = None
    for key, entry in mapping.items():
        if entry is None:
            continue
        if entry.group != current_group:
            if current_group is not None:
                lines.append(Text(""))
            current_group = entry.group
            lines.append(Text(f"  {current_group.upper()}", style=cli_output.HEADER))
        line = Text("  ")
        line.append(f"{key:>2}", style=cli_output.ACCENT)
        line.append(f"   {entry.label}")
        lines.append(line)
    lines.append(Text(""))
    lines.append(Text("  HELP", style=cli_output.HEADER))
    help_line = Text("  ")
    help_line.append(f"{_HELP_KEY:>2}", style=cli_output.ACCENT)
    help_line.append("   Full command list")
    lines.append(help_line)
    search_line = Text("  ")
    search_line.append(f"{_SEARCH_KEY:>2}", style=cli_output.ACCENT)
    search_line.append("   Search commands")
    lines.append(search_line)
    quit_line = Text("  ")
    quit_line.append(f"{_QUIT_KEY:>2}", style=cli_output.ACCENT)
    quit_line.append("   Quit")
    lines.append(quit_line)
    return Group(*lines)


def _say_goodbye(console) -> None:
    console.print(Text("  Goodbye.", style=cli_output.MUTED))


def _ask_choice(console, mapping: dict[str, Entry | None]) -> str:
    console.print()
    cli_output.print_panel(
        cli_output.section_panel("Value Investing", _menu_body(mapping)),
        console=console,
        width=64,
    )
    return Prompt.ask(
        "  Choice",
        choices=[*mapping, _HELP_KEY, _SEARCH_KEY],
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
            if choice == _HELP_KEY:
                console.print(render_help_footer())
                continue
            if choice == _SEARCH_KEY:
                query = Prompt.ask("  Search commands", console=console)
                results = render_search_results(query)
                console.print(results or f"No commands match '{query}'.")
                continue
            if choice == _QUIT_KEY or mapping.get(choice) is None:
                _say_goodbye(console)
                return
            _run_entry(console, mapping[choice])
    except (KeyboardInterrupt, EOFError):
        console.print()
        _say_goodbye(console)


def run_menu() -> None:
    """Open the menu (entry point for ``vi`` with no arguments)."""
    _run(None)


def register(subparsers):
    p = subparsers.add_parser(
        "interactive",
        help="Menu mode: pick a command, type its arguments, run it",
        description=(
            "Shows a categorized menu of the regular commands, asks for their "
            "arguments and runs them in-process. Press ? for help, s to search "
            "and q or Ctrl+C to leave."
        ),
    )
    p.set_defaults(func=_run)
