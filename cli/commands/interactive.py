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
import os
import re
import shlex
import shutil
from collections.abc import Callable
from datetime import date
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
from cli.menu_prompts import (
    PromptCancelled,
    ask_choice,
    ask_float,
    ask_int,
    ask_methodology,
    ask_text,
    ask_ticker,
    ask_universe,
    ask_yes_no,
)

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
_ADVANCED = "x"


class Action(NamedTuple):
    """One executable menu option."""

    label: str
    description: str
    module: object
    argv: tuple[str, ...] = ()
    prompt: str = ""
    default: str = ""
    #: Guided flow returning the extra argv, or ``None`` when cancelled.
    #: Every built-in action has one; ``prompt``/``default`` remain only as
    #: a fallback for ad-hoc actions (tests, third-party callers).
    guide: Callable[[], list[str] | None] | None = None

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


# ---------------------------------------------------------------------------
# guided flows (one per menu option)
# ---------------------------------------------------------------------------
def _guide_none() -> list[str]:
    """Options that need no input (portfolio view/performance)."""
    return []


# ---------------------------------------------------------------------------
# portfolio mutations
# ---------------------------------------------------------------------------
def _portfolio_path() -> str:
    """The JSON path used by the CLI (demo bundle when demo mode is on)."""
    from backend.services.demo_mode import DEMO_PORTFOLIO, is_demo

    if is_demo():
        return str(DEMO_PORTFOLIO)
    return os.getenv("PORTFOLIO_PATH", "data/portfolio.json")


def _open_positions() -> list:
    """Read open positions without refreshing prices (no network)."""
    from backend.portfolio.portfolio_repository import JsonPortfolioRepository

    portfolio = JsonPortfolioRepository(_portfolio_path()).load()
    return sorted(
        (position for position in portfolio.positions if position.is_open),
        key=lambda position: position.ticker,
    )


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError):
        return False
    return True


def _guide_portfolio_add() -> list[str] | None:
    ticker = ask_ticker("Ticker", default=None)
    if any(
        position.ticker.upper() == ticker for position in _open_positions()
    ) and not ask_yes_no(
        f"{ticker} already exists. Average into the position?", default=True
    ):
        return None
    shares = ask_int("Shares", min_val=1)
    cost = ask_float("Cost basis per share", min_val=0.01)
    extra = [ticker, str(shares), str(cost)]
    if ask_yes_no("Specify purchase date?", default=False):
        purchase_date = ask_text(
            "Date (YYYY-MM-DD)",
            validator=_is_iso_date,
            validator_error="Use YYYY-MM-DD.",
        )
        extra.extend(["--date", purchase_date])
    return extra


def _guide_portfolio_thesis() -> list[str] | None:
    positions = _open_positions()
    if not positions:
        print(_c("  Portfolio is empty.", "dim"))
        return None
    ticker = ask_choice(
        "Which position?",
        [(position.ticker, position.ticker) for position in positions],
    )
    position = next((item for item in positions if item.ticker == ticker), None)
    if position is not None and position.thesis:
        print()
        print(_c(f"Current thesis ({ticker}):", "gold"))
        print(f"  {position.thesis}")
        print()
    action = ask_choice(
        "Action",
        [
            ("Set / update thesis", "set"),
            ("Clear thesis", "clear"),
            ("Cancel", "cancel"),
        ],
    )
    if action == "cancel":
        return None
    if action == "clear":
        return [ticker, "--clear"]
    text = ask_text("Thesis (one line)")
    return [ticker, "--set", text]


def _guide_portfolio_remove() -> list[str] | None:
    positions = _open_positions()
    if not positions:
        print(_c("  Portfolio is empty.", "dim"))
        return None
    ticker = ask_choice(
        "Remove which position?",
        [
            (f"{position.ticker} · {position.quantity:g} shares", position.ticker)
            for position in positions
        ],
    )
    if not ask_yes_no(f"Remove {ticker} without recording a sale?", default=False):
        print(_c("  Cancelled.", "dim"))
        return None
    return [ticker]


def _guide_portfolio_exit() -> list[str] | None:
    positions = _open_positions()
    if not positions:
        print(_c("  Portfolio is empty.", "dim"))
        return None
    ticker = ask_choice(
        "Exit which position?",
        [
            (f"{position.ticker} · {position.quantity:g} shares", position.ticker)
            for position in positions
        ],
    )
    price = ask_float("Exit price per share", min_val=0.01)
    if not ask_yes_no(
        f"Close the full {ticker} position at {price:,.2f}?", default=False
    ):
        print(_c("  Cancelled.", "dim"))
        return None
    return [ticker, str(price)]


def _guide_scorecard() -> list[str]:
    ticker = ask_ticker("Ticker")
    as_json = ask_yes_no("Show JSON output?", default=False)
    return [ticker, *(["--json"] if as_json else [])]


def _guide_balance() -> list[str]:
    ticker = ask_ticker("Ticker")
    years = ask_int("How many fiscal years?", default=5, min_val=1, max_val=20)
    return [ticker, "--years", str(years)]


def _guide_methodologies() -> list[str]:
    methods, _strategy = ask_methodology("Which methodology?")
    return [methods[0]]


def _guide_dcf() -> list[str]:
    return [ask_ticker("Ticker")]


def _guide_compare() -> list[str]:
    return [ask_ticker("Ticker")]


def _guide_full() -> list[str]:
    tickers = ask_text("Ticker(s), space-separated", default="AAPL")
    prices = ask_yes_no("Fetch live prices?", default=True)
    return shlex.split(tickers) + ([] if prices else ["--no-prices"])


def _rank_args(
    methods: list[str], strategy: str | None, top: int, universe: str
) -> list[str]:
    if strategy:
        return [
            "--combine",
            ",".join(methods),
            "--strategy",
            strategy,
            "--top",
            str(top),
            "--universe",
            universe,
        ]
    return ["--by", methods[0], "--top", str(top), "--universe", universe]


def _guide_rank() -> list[str]:
    methods, strategy = ask_methodology("Which methodology?", include_combine=True)
    top = ask_int("How many top tickers?", default=20, min_val=1, max_val=500)
    universe = ask_universe()
    return _rank_args(methods, strategy, top, universe)


def _guide_combine() -> list[str]:
    methods, strategy = ask_methodology(
        "Which methodologies?", include_combine=True, combine_only=True
    )
    top = ask_int("How many top tickers?", default=20, min_val=1, max_val=500)
    universe = ask_universe()
    return _rank_args(methods, strategy or "and", top, universe)


def _guide_consensus() -> list[str]:
    ticker = ask_ticker("Ticker")
    universe = ask_universe()
    return [ticker, "--universe", universe]


def _guide_consensus_ranking() -> list[str]:
    universe = ask_universe()
    top = ask_int("How many rows?", default=20, min_val=1, max_val=500)
    return ["--universe", universe, "--top", str(top)]


def _guide_screener() -> list[str]:
    filter_type = ask_choice(
        "Filter by",
        [("No filter", "none"), ("Methodology verdict", "methodology")],
    )
    args = ["--universe", ask_universe("demo")]
    if filter_type == "methodology":
        methods, _strategy = ask_methodology("Which methodology?")
        verdict = ask_choice(
            "Verdict",
            [("BUY", "BUY"), ("WATCH", "WATCH"), ("HOLD", "HOLD"), ("AVOID", "AVOID")],
        )
        args += ["--methodology", f"{methods[0]}:{verdict}"]
    top = ask_int("How many results?", default=20, min_val=1, max_val=100)
    return [*args, "--top", str(top)]


def _guide_refresh() -> list[str]:
    ticker = ask_ticker("Ticker")
    mode = ask_choice(
        "Refresh",
        [
            ("Both facts and prices", "both"),
            ("Facts only", "facts"),
            ("Prices only", "prices"),
        ],
    )
    if mode == "facts":
        return [ticker, "--facts-only"]
    if mode == "prices":
        return [ticker, "--prices-only"]
    return [ticker]


def _guide_data_status() -> list[str]:
    return [ask_ticker("Ticker")]


def _guide_load_data() -> list[str]:
    ticker = ask_ticker("Ticker")
    years = ask_int("How many fiscal years?", default=10, min_val=1, max_val=30)
    force = ask_yes_no("Overwrite existing data?", default=False)
    return [ticker, "--years", str(years), *(["--force"] if force else [])]


def _guide_filings() -> list[str]:
    ticker = ask_ticker("Ticker")
    limit = ask_int("How many filings?", default=40, min_val=1, max_val=200)
    return [ticker, "--limit", str(limit)]


def _guide_alerts() -> list[str]:
    return [ask_ticker("Ticker")]


def _backtest_methodologies() -> list[str]:
    """Registered methodologies the backtest can evaluate (no greenblatt)."""
    from backend.methodologies.registry import discover, registry

    discover()
    return [name for name in registry.list() if name != "greenblatt"]


def _guide_backtest() -> list[str]:
    methods, _strategy = ask_methodology(
        "Which methodology?", names=_backtest_methodologies()
    )
    years = ask_int("How many years?", default=5, min_val=1, max_val=20)
    limit = ask_int("How many tickers (limit)?", default=400, min_val=10, max_val=500)
    equal_weight = ask_yes_no("Use equal-weight (legacy)?", default=False)
    return [
        "--methodology",
        methods[0],
        "--years",
        str(years),
        "--limit",
        str(limit),
        *(["--equal-weight"] if equal_weight else []),
    ]


# ---------------------------------------------------------------------------
# menu model
# ---------------------------------------------------------------------------
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
            guide=_guide_scorecard,
        ),
        Action(
            "Balance",
            "T-view assets | liabilities",
            financials,
            prompt="Ticker",
            default="AAPL",
            guide=_guide_balance,
        ),
        Action(
            "Methodologies",
            "8 methods · rules",
            methodologies,
            argv=("show",),
            prompt="Methodology",
            default="graham",
            guide=_guide_methodologies,
        ),
        Action(
            "DCF",
            "Two-stage valuation",
            dcf,
            prompt="Ticker",
            default="AAPL",
            guide=_guide_dcf,
        ),
        Action(
            "Compare",
            "All methods side-by-side",
            compare_methodologies,
            prompt="Ticker",
            default="AAPL",
            guide=_guide_compare,
        ),
        Action(
            "Full analysis",
            "Consolidated report",
            analyze_full,
            prompt="Ticker(s) and flags",
            default="AAPL --no-prices",
            guide=_guide_full,
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
            guide=_guide_rank,
        ),
        Action(
            "Combine methods",
            "AND / OR / weighted",
            rank,
            prompt="Methods and flags",
            default="--combine graham,lynch_garp --strategy and --top 20",
            guide=_guide_combine,
        ),
        Action(
            "Consensus",
            "All 8 for one ticker",
            consensus,
            prompt="Ticker",
            default="AAPL",
            guide=_guide_consensus,
        ),
        Action(
            "Consensus ranking",
            "Rank the consensus file",
            consensus_ranking,
            prompt="Flags",
            default="--universe sp500 --top 10",
            guide=_guide_consensus_ranking,
        ),
        Action(
            "Screener",
            "Filters + verdicts",
            screener,
            prompt="Filters and flags",
            default="--tickers AAPL,MSFT,GOOGL --top 5 --no-refresh",
            guide=_guide_screener,
        ),
    ),
)

_DATA = Category(
    "data",
    "Portfolio · Data · Backtesting",
    "Portfolio · refresh · filings",
    (
        Action(
            "Portfolio view",
            "Positions and scores",
            portfolio,
            argv=("view",),
            guide=_guide_none,
        ),
        Action(
            "Performance",
            "PnL and allocation",
            portfolio,
            argv=("performance",),
            guide=_guide_none,
        ),
        Action(
            "Add position",
            "Open or average in",
            portfolio,
            argv=("add",),
            guide=_guide_portfolio_add,
        ),
        Action(
            "Remove position",
            "Delete without a sale",
            portfolio,
            argv=("remove",),
            guide=_guide_portfolio_remove,
        ),
        Action(
            "Exit position",
            "Close and record PnL",
            portfolio,
            argv=("exit",),
            guide=_guide_portfolio_exit,
        ),
        Action(
            "Thesis",
            "Set or clear a thesis",
            portfolio,
            argv=("thesis",),
            guide=_guide_portfolio_thesis,
        ),
        Action(
            "Refresh",
            "Facts + prices for a ticker",
            refresh,
            prompt="Ticker",
            default="AAPL",
            guide=_guide_refresh,
        ),
        Action(
            "Data status",
            "Coverage and freshness",
            data_status,
            prompt="Ticker",
            default="AAPL",
            guide=_guide_data_status,
        ),
        Action(
            "Load data",
            "Download + store",
            load_data,
            prompt="Ticker and flags",
            default="AAPL",
            guide=_guide_load_data,
        ),
        Action(
            "Filings",
            "SEC documents",
            filings,
            argv=("--prompt-open",),
            prompt="Ticker",
            default="AAPL",
            guide=_guide_filings,
        ),
        Action(
            "Financial alerts",
            "Cash, margins, debt",
            financial_alerts,
            prompt="Ticker",
            default="AAPL",
            guide=_guide_alerts,
        ),
        Action(
            "Backtest",
            "Methodology history (PoC)",
            backtest,
            prompt="Methodology and flags",
            default="--methodology graham --years 5",
            guide=_guide_backtest,
        ),
    ),
)

_CATEGORIES: dict[str, Category] = {
    "analysis": _ANALYSIS,
    "ranking": _RANKING,
    "data": _DATA,
}

#: Command name -> module, used by the advanced raw-command mode.
_MODULES: dict[str, object] = {
    "analyze-full": analyze_full,
    "backtest": backtest,
    "compare-methodologies": compare_methodologies,
    "consensus": consensus,
    "consensus-ranking": consensus_ranking,
    "data-status": data_status,
    "dcf": dcf,
    "filings": filings,
    "financial-alerts": financial_alerts,
    "financials": financials,
    "load-data": load_data,
    "methodologies": methodologies,
    "portfolio": portfolio,
    "rank": rank,
    "refresh": refresh,
    "scorecard": scorecard,
    "screener": screener,
}
_COMMAND_OF = {id(module): name for name, module in _MODULES.items()}


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
    lines.append(
        _footer(
            ("s", "Search"),
            ("?", "Help"),
            ("x", "Advanced"),
            ("q", "Quit"),
        )
    )
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
def _execute(parsed) -> None:
    """Run one parsed command (the seam the flow tests patch)."""
    parsed.func(parsed)


def _legacy_extra(action: Action) -> list[str] | None:
    """Fallback text prompt for ad-hoc actions without a guided flow."""
    if not action.prompt:
        return []
    try:
        raw = input(f"  {action.prompt} [{action.default}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise PromptCancelled() from None
    return shlex.split(raw or action.default)


def _display_command(action: Action, extra: list[str]) -> str:
    command = _COMMAND_OF.get(id(action.module))
    parts = ([command] if command else []) + list(action.argv) + list(extra)
    return "vi " + " ".join(shlex.quote(part) for part in parts if part)


def _run_action(action: Action) -> None:
    try:
        extra = action.guide() if action.guide is not None else _legacy_extra(action)
    except PromptCancelled:
        print(_c("  (back to the menu)", "dim"))
        return
    if extra is None:
        return
    print(_c(f"  Running: {_display_command(action, extra)}", "dim"))
    try:
        parsed = action.build(extra)
    except SystemExit:
        print(_c("  (back to the menu)", "dim"))
        return
    _execute(parsed)


def _advanced() -> None:
    """Raw-command mode for power users / cases outside the guided flows."""
    try:
        raw = ask_text(
            "Enter full command (e.g. backtest --methodology graham --years 10)",
            allow_empty=True,
        )
    except PromptCancelled:
        return
    if not raw.strip():
        return
    argv = shlex.split(raw)
    module = _MODULES.get(argv[0])
    if module is None:
        print(_c(f"  Unknown command: {argv[0]}", "pink"))
        return
    print(_c(f"  Running: vi {raw}", "dim"))
    try:
        parsed = Action("", "", module).build(argv[1:])
    except SystemExit:
        print(_c("  (back to the menu)", "dim"))
        return
    _execute(parsed)


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
            try:
                query = ask_text("Search commands", allow_empty=True)
            except PromptCancelled:
                continue
            if query:
                print(render_search_results(query) or f"No commands match '{query}'.")
            continue
        if choice == _ADVANCED:
            _advanced()
            continue
        if choice not in choices:
            print(
                _c(
                    f"  Choose {', '.join(sorted(choices))}, h, s, x, ?, q.",
                    "dim",
                )
            )
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
        help="Menu mode: guided prompts for every command",
        description=(
            "Shows a synthwave categorized menu of the regular commands with "
            "guided prompts (numbered selectors, numeric fields with defaults, "
            "y/n), and runs them in-process. h=home, s=search, x=advanced "
            "raw command, ?=help, q=quit. q/back/Ctrl+C cancels a prompt and "
            "returns to the previous menu."
        ),
    )
    p.set_defaults(func=_run)
