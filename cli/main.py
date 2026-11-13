import argparse
import logging
import sys

from backend.services import cli_output
from cli.command_catalog import CATALOG, format_catalog, format_common_tasks
from cli.help_utils import render_search_results, suggest_command

logging.getLogger("sqlalchemy.engine").setLevel(logging.ERROR)

NO_COLOR_HELP = "Disable colored output (same as NO_COLOR=1)."


def _add_no_color(
    parser: argparse.ArgumentParser, seen: set[int] | None = None
) -> None:
    """Register ``--no-color`` on ``parser`` and on every nested subparser.

    The CLI is argparse-based, so the flag is repeated per subparser instead
    of living on a Click context: that way ``main.py --no-color portfolio
    view`` and ``main.py portfolio view --no-color`` behave the same and the
    flag shows up in every ``--help``. argparse exposes no public API to walk
    the subparser tree, hence the private attributes.

    ``SUPPRESS`` matters: argparse applies each subparser's default into the
    same namespace, so a plain ``default=False`` would silently reset a
    ``--no-color`` typed before the command. ``seen`` keeps a parser
    reachable twice from being registered twice.
    """
    if seen is None:
        seen = set()
    if id(parser) in seen:
        return
    seen.add(id(parser))
    parser.add_argument(
        "--no-color", action="store_true", default=argparse.SUPPRESS, help=NO_COLOR_HELP
    )
    # argparse has no public accessor for the subparser tree.
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub_parser in action.choices.values():
                _add_no_color(sub_parser, seen)


def main():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Value Investing Platform — fundamental analysis from the terminal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            format_common_tasks()
            + "\n\n"
            + format_catalog()
            + "\n\nSearch: vi help --search <query>"
        ),
    )
    sub = parser.add_subparsers(dest="command", title="Commands")

    from cli.commands import (
        alerts,
        analyze,
        analyze_full,
        anomalies,
        backtest,
        buffett_analysis,
        company,
        consensus,
        consensus_by_category,
        consensus_ranking,
        data_status,
        dcf,
        debug,
        filing,
        filing_balance_sheet,
        filing_section,
        filing_statement,
        filings,
        financial_alerts,
        financials,
        historical_valuation,
        interactive,
        load_data,
        momentum,
        opportunities,
        portfolio,
        rank,
        refresh,
        scorecard,
        screener,
        sql_analysis,
        watchlist,
    )
    from cli.commands.methodologies import register as register_methodologies

    screener.register(sub)
    company.register(sub)
    consensus.register(sub)
    consensus_ranking.register(sub)
    consensus_by_category.register(sub)
    analyze.register(sub)
    analyze_full.register(sub)
    buffett_analysis.register(sub)
    historical_valuation.register(sub)
    load_data.register(sub)
    data_status.register(sub)
    dcf.register(sub)
    scorecard.register(sub)
    opportunities.register(sub)
    anomalies.register(sub)
    momentum.register(sub)
    portfolio.register(sub)
    backtest.register(sub)
    alerts.register(sub)
    watchlist.register(sub)
    debug.register(sub)
    sql_analysis.register(sub)
    filings.register(sub)
    filing.register(sub)
    filing_balance_sheet.register(sub)
    filing_statement.register(sub)
    filing_section.register(sub)
    financial_alerts.register(sub)
    financials.register(sub)
    refresh.register(sub)
    rank.register(sub)
    interactive.register(sub)
    register_methodologies(sub)

    # After registration: the root and every (nested) subparser accept
    # --no-color, so the flag works before or after the command name.
    _add_no_color(parser)

    if len(sys.argv) == 1:
        # No subcommand: open the one-level menu instead of dumping the
        # help text. ``vi --help`` still prints the full usage.
        interactive.run_menu()
        return

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "help":
            if len(sys.argv) == 2:
                parser.print_help()
                return
            if sys.argv[2] == "--search":
                query = " ".join(sys.argv[3:]).strip()
                results = render_search_results(query)
                if results:
                    print(results)
                else:
                    print(f"No commands match '{query}'. Try 'vi --help'.")
                return
            target = sys.argv[2]
            if target not in CATALOG:
                suggestion = suggest_command(target)
                message = f"Unknown command '{target}'."
                if suggestion:
                    message += f" Did you mean 'vi {suggestion}'?"
                else:
                    message += " Run 'vi --help' for the full list."
                print(message, file=sys.stderr)
                raise SystemExit(2)
            sys.argv = [sys.argv[0], target, "--help"]
        elif not command.startswith("-") and command not in CATALOG:
            suggestion = suggest_command(command)
            message = f"Unknown command '{command}'."
            if suggestion:
                message += f" Did you mean 'vi {suggestion}'?"
            else:
                message += " Run 'vi --help' for the full list."
            print(message, file=sys.stderr)
            raise SystemExit(2)

    args = parser.parse_args()
    cli_output.set_no_color(getattr(args, "no_color", False))
    if getattr(args, "demo", False):
        from backend.services.demo_mode import enable_demo

        enable_demo()
    args.func(args)
