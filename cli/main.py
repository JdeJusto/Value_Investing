import argparse
import logging
import sys

from backend.services import cli_output

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
            "Examples:\n"
            "  main.py screener --per-max 15 --roe-min 12 --top 10\n"
            '  main.py screener --search "apple"\n'
            "  main.py company AAPL\n"
            "  main.py consensus AAPL\n"
            "  main.py consensus-ranking --universe sp500 --top 10\n"
            "  main.py consensus-by-category --universe sp500\n"
            "  main.py analyze AAPL MSFT GOOGL\n"
            "  main.py buffett-analysis AAPL\n"
            "  main.py load-data AAPL\n"
            "  main.py load-data AAPL --years 15 --force\n"
            "  main.py data-status AAPL\n"
            "  main.py screener --tickers AAPL,MSFT --pb-min 1 --pb-max 5\n"
            "  main.py screener --filter moat=STRONG min_score=80\n"
            "  main.py opportunities\n"
            "  main.py anomalies AAPL\n"
            "  main.py momentum\n"
            '  main.py portfolio add AAPL 10 180 --thesis "strong moat"\n'
            "  main.py portfolio view\n"
            "  main.py portfolio performance\n"
            "  main.py backtest --strategy momentum --top 3\n"
            "  main.py backtest --strategy buffett --prices prices.csv\n"
            "  main.py alerts\n"
            '  main.py watchlist add AAPL --note "pending entry"\n'
            "  main.py watchlist list\n"
            "  main.py debug\n"
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
        filing_balance_sheet,
        filing_section,
        filing_statement,
        filings,
        financial_alerts,
        historical_valuation,
        interactive,
        load_data,
        momentum,
        opportunities,
        portfolio,
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
    filing_balance_sheet.register(sub)
    filing_statement.register(sub)
    filing_section.register(sub)
    financial_alerts.register(sub)
    interactive.register(sub)
    register_methodologies(sub)

    # After registration: the root and every (nested) subparser accept
    # --no-color, so the flag works before or after the command name.
    _add_no_color(parser)

    if len(sys.argv) == 1:
        parser.print_help()
        return

    args = parser.parse_args()
    cli_output.set_no_color(getattr(args, "no_color", False))
    if getattr(args, "demo", False):
        from backend.services.demo_mode import enable_demo

        enable_demo()
    args.func(args)
