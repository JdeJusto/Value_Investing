"""`interactive` — synthwave terminal menu over the regular commands.

A trading-terminal look (neon cyan/pink/gold, heavy box drawing, a compact
home screen) with three category submenus. Number-based navigation only: no
new dependency, works over SSH and pipes. ``NO_COLOR``, ``--no-color`` and a
non-TTY stdout fall back to plain ASCII borders and no ANSI.

The menu never re-implements a command: it parses the typed arguments with the
command's own parser and dispatches in-process.
"""

from __future__ import annotations

import argparse
import re
import shlex
import shutil
from typing import NamedTuple

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

_ANSI = {
    "cyan": "\033[38;5;51m",
    "pink": "\033[38;5;205m",
    "gold": "\033[38;5;220m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")
_QUIT = "q"
_HOME = "h"
_HELP = "?"
_SEARCH = "s"


class Action(NamedTuple):
    """One executable menu option."""

    label: str
    description: str
    module: object
    argv: tuple[str, ...] = ()
    prompt: str = ""
    default: str = ""

    def build(self, extra: list[str]):
        parser = argparse.ArgumentParser(prog="main.py")
        sub = parser.add_subparsers(dest="command")
        self.module.register(sub)
        name = next(iter(sub.choices))
        return parser.parse_args([name, *self.argv, *extra])


class Category(NamedTuple):
    key: str
    title: str
    description: str
    actions: tuple[Action, ...]


_ANALYSIS = Category(
    "analysis",
    "Analysis",
    "Scorecard · balance · DCF",
    (
        Action(
            "Scorecard",
            "6 dimensions · verdicts",
            scorecard,
            prompt="Ticker",
            default="AAPL",
        ),
        Action(
            "Balance",
            "T-view assets | liabilities",
            financials,
            prompt="Ticker",
            default="AAPL",
        ),
        Action(
            "Methodologies",
            "8 methods · rules",
            methodologies,
            argv=("show",),
            prompt="Methodology",
            default="graham",
        ),
        Action("DCF", "Two-stage valuation", dcf, prompt="Ticker", default="AAPL"),
        Action(
            "Compare",
            "All methods side-by-side",
            compare_methodologies,
            prompt="Ticker",
            default="AAPL",
        ),
        Action(
            "Full analysis",
            "Consolidated report",
            analyze_full,
            prompt="Ticker(s) and flags",
            default="AAPL --no-prices",
        ),
    ),
)

_RANKING = Category(
    "ranking",
    "Ranking & screening",
    "Top N · combine · consensus",
    (
        Action(
            "Rank top N",
            "e.g. graham --top 20",
            rank,
            prompt="Methodology and flags",
            default="--by graham --universe sp500 --top 20",
        ),
        Action(
            "Combine methods",
            "AND / OR / weighted",
            rank,
            prompt="Methods and flags",
            default="--combine graham,lynch_garp --strategy and --top 20",
        ),
        Action(
            "Consensus",
            "All 8 for one ticker",
            consensus,
            prompt="Ticker",
            default="AAPL",
        ),
        Action(
            "Consensus ranking",
            "Rank the consensus file",
            consensus_ranking,
            prompt="Flags",
            default="--universe sp500 --top 10",
        ),
        Action(
            "Screener",
            "Filters + verdicts",
            screener,
            prompt="Filters and flags",
            default="--tickers AAPL,MSFT,GOOGL --top 5 --no-refresh",
        ),
    ),
)

_DATA = Category(
    "data",
    "Portfolio · Data · Backtesting",
    "Portfolio · refresh · filings",
    (
        Action("Portfolio view", "Positions and scores", portfolio, argv=("view",)),
        Action("Performance", "PnL and allocation", portfolio, argv=("performance",)),
        Action(
            "Refresh",
            "Facts + prices for a ticker",
            refresh,
            prompt="Ticker",
            default="AAPL",
        ),
        Action(
            "Data status",
            "Coverage and freshness",
            data_status,
            prompt="Ticker",
            default="AAPL",
        ),
        Action(
            "Load data",
            "Download + store",
            load_data,
            prompt="Ticker and flags",
            default="AAPL",
        ),
        Action("Filings", "SEC documents", filings, prompt="Ticker", default="AAPL"),
        Action(
            "Financial alerts",
            "Cash, margins, debt",
            financial_alerts,
            prompt="Ticker",
            default="AAPL",
        ),
        Action(
            "Backtest",
            "Methodology history (PoC)",
            backtest,
            prompt="Methodology and flags",
            default="--methodology graham --years 5",
        ),
    ),
)

_CATEGORIES: dict[str, Category] = {
    "analysis": _ANALYSIS,
    "ranking": _RANKING,
    "data": _DATA,
}


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def _colors() -> bool:
    return cli_output.color_enabled()


def _c(text: str, *keys: str) -> str:
    if not _colors():
        return text
    return "".join(_ANSI[key] for key in keys) + text + _ANSI["reset"]


def _visible_len(text: str) -> int:
    return len(_ANSI_RE.sub("", text))


def _width() -> int:
    columns = shutil.get_terminal_size((80, 24)).columns
    return max(44, min(66, columns - 2))


def _truncate_visible(text: str, limit: int) -> str:
    """Trim a (possibly coloured) line to ``limit`` visible characters."""
    if _visible_len(text) <= limit:
        return text
    return _ANSI_RE.sub("", text)[: max(0, limit - 1)] + "…"


def _box(title: str, lines: list[str], width: int) -> list[str]:
    """A heavy-border box; ASCII fallback when colours are disabled."""
    content_width = max(8, width - 2)
    lines = [_truncate_visible(line, content_width) for line in lines]
    if _colors():
        fill = max(1, width - len(title) - 3)
        top = (
            _c("┏━ ", "gold", "bold")
            + _c(title.upper(), "pink", "bold")
            + _c(" " + "━" * fill + "┓", "gold", "bold")
        )
        body = []
        for line in lines:
            pad = max(0, content_width - _visible_len(line))
            body.append(_c("┃", "gold") + " " + line + " " * pad + _c(" ┃", "gold"))
        bottom = _c("┗" + "━" * width + "┛", "gold", "bold")
    else:
        top = "+- " + title.upper() + " " + "-" * max(1, width - len(title) - 3) + "+"
        body = [
            "| " + line + " " * max(0, content_width - _visible_len(line)) + " |"
            for line in lines
        ]
        bottom = "+" + "-" * width + "+"
    return [top, *body, bottom]


def _header(width: int) -> list[str]:
    title = "V A L U E   I N V E S T I N G"
    subtitle = "Terminal analysis · synthwave edition"
    if _colors():
        return [
            _c("╔" + "═" * width + "╗", "cyan", "bold"),
            _c("║", "cyan", "bold")
            + " "
            + _c(title, "pink", "bold")
            + " " * max(0, width - len(title) - 1)
            + _c("║", "cyan", "bold"),
            _c("║", "cyan", "bold")
            + " "
            + _c(subtitle, "cyan")
            + " " * max(0, width - len(subtitle) - 1)
            + _c("║", "cyan", "bold"),
            _c("╚" + "═" * width + "╝", "cyan", "bold"),
        ]
    return [
        "+" + "-" * width + "+",
        "| " + title + " " * max(0, width - len(title) - 1) + "|",
        "| " + subtitle + " " * max(0, width - len(subtitle) - 1) + "|",
        "+" + "-" * width + "+",
    ]


def _option(number: str, label: str, description: str) -> str:
    number_text = _c(f"[{number}]", "gold", "bold")
    label_text = _c(label.ljust(20), "cyan")
    return f"{number_text} {label_text} {_c(description, 'dim')}"


def _footer(*entries: tuple[str, str]) -> str:
    return "   ".join(
        _c(f"[{key}]", "pink", "bold") + f" {label}" for key, label in entries
    )


def render_home() -> str:
    width = _width()
    lines = _header(width)
    lines.append("")
    for index, category in enumerate(_CATEGORIES.values(), 1):
        label = category.title.split(" · ")[0]
        lines.extend(
            _box(
                category.title,
                [_option(str(index), label, category.description)],
                width,
            )
        )
    lines.append("")
    lines.append(_footer(("s", "Search"), ("?", "Help"), ("q", "Quit")))
    return "\n".join(lines)


def render_category(category: Category) -> str:
    width = _width()
    lines = _header(width)
    lines.append("")
    lines.extend(
        _box(
            category.title,
            [
                _option(str(index), action.label, action.description)
                for index, action in enumerate(category.actions, 1)
            ],
            width,
        )
    )
    lines.append("")
    lines.append(_footer(("h", "Home"), ("s", "Search"), ("?", "Help"), ("q", "Quit")))
    return "\n".join(lines)


def _render(screen: str) -> tuple[str, dict[str, str]]:
    if screen == "home":
        return render_home(), {
            str(index): key for index, key in enumerate(_CATEGORIES, 1)
        }
    category = _CATEGORIES[screen]
    return render_category(category), {
        str(index): str(index) for index in range(1, len(category.actions) + 1)
    }


# ---------------------------------------------------------------------------
# interaction
# ---------------------------------------------------------------------------
def _run_action(action: Action) -> None:
    extra: list[str] = []
    if action.prompt:
        raw = input(f"  {action.prompt} [{action.default}]: ").strip() or action.default
        extra = shlex.split(raw)
    try:
        parsed = action.build(extra)
    except SystemExit:
        print(_c("  (back to the menu)", "dim"))
        return
    parsed.func(parsed)


def _run(_args=None) -> None:
    screen = "home"
    print()
    while True:
        text, choices = _render(screen)
        print(text)
        try:
            choice = input("  Choice: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            print("  Goodbye.")
            return
        if choice in ("", _QUIT):
            print("  Goodbye.")
            return
        if choice == _HOME:
            screen = "home"
            continue
        if choice == _HELP:
            print(render_help_footer())
            continue
        if choice == _SEARCH:
            query = input("  Search commands: ").strip()
            print(render_search_results(query) or f"No commands match '{query}'.")
            continue
        if choice not in choices:
            print(_c(f"  Choose {', '.join(sorted(choices))}, h, s, ?, q.", "dim"))
            continue
        if screen == "home":
            screen = choices[choice]
            continue
        action = _CATEGORIES[screen].actions[int(choice) - 1]
        print()
        _run_action(action)
        print()


def run_menu() -> None:
    """Open the menu (entry point for ``vi`` with no arguments)."""
    _run(None)


def register(subparsers):
    p = subparsers.add_parser(
        "interactive",
        help="Menu mode: pick a command, type its arguments, run it",
        description=(
            "Shows a synthwave categorized menu of the regular commands, asks "
            "for their arguments and runs them in-process. h=home, s=search, "
            "?=help, q=quit."
        ),
    )
    p.set_defaults(func=_run)
