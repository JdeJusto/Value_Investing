"""CLI: run the alert engine over the universe and notify."""

import sys

from backend.alerts import run
from backend.app.cli import (
    add_refresh_arguments,
    build_analysis_service,
    build_universe,
    refresh_analysis_inputs,
)
from cli.formatters import bold, green, print_header, red, yellow


def register(subparsers):
    p = subparsers.add_parser(
        "alerts",
        help="Evaluate buy/sell signals and events",
        description=(
            "Runs the alert engine (BUY_SIGNAL, SELL_WARNING, "
            "TRIGGER_EVENT) over the universe. With --state JSON, evaluates "
            "score drops versus the previous state."
        ),
    )
    p.add_argument(
        "--state",
        default=None,
        help="JSON with previous analyses ({ticker: analysis}) for SELL_WARNING",
    )
    p.add_argument(
        "tickers",
        type=str,
        nargs="*",
        help="Tickers to evaluate (optional: loaded universe)",
    )
    add_refresh_arguments(p)
    p.set_defaults(func=_run)


def _load_state(path):
    import json

    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        print(f"  {red('ERROR:')} State file '{path}' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"  {red('ERROR:')} The state file '{path}' is not valid JSON.")
        sys.exit(1)


def _run(args):
    service = build_analysis_service()
    universe = build_universe(args.tickers)
    refresh_analysis_inputs(universe, args, explicit=bool(args.tickers))
    previous = _load_state(args.state) if args.state else {}

    analyses = {}
    for ticker in universe:
        result = service.analyze(ticker)
        if result is not None:
            analyses[ticker] = result

    print_header(f"Alerts ({len(analyses)} companies evaluated)")
    alerts = run(analyses, previous)
    if not alerts:
        print(f"  {yellow('No alerts.')} The portfolio stays within parameters.")
        print()
        print(green("Done."))
        return

    for alert in alerts:
        reason = "; ".join(alert.reason) if alert.reason else "-"
        label = {
            "BUY_SIGNAL": "BUY",
            "SELL_WARNING": "SELL",
            "TRIGGER_EVENT": "EVENT",
        }[alert.alert_type]
        print(
            f"  {bold(alert.ticker):<10} [{label}] {alert.alert_type} "
            f"(confidence {alert.confidence}): {reason}"
        )

    print()
    print(green("Done."))
