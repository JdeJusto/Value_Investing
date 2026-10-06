from backend.app.cli import (
    add_refresh_arguments,
    build_investment_screener,
    refresh_analysis_inputs,
)
from cli.formatters import bold, dim, green, print_header, print_key_value, yellow


def register(subparsers):
    p = subparsers.add_parser(
        "opportunities",
        help="Detected opportunities: cheap quality, compounders, turnarounds",
        description=(
            "Analyzes the loaded universe and shows actionable situations "
            "with their type, confidence and the reasons behind each detection."
        ),
    )
    p.add_argument(
        "--tickers",
        type=str,
        help="Comma-separated tickers (e.g.: AAPL,MSFT,GOOGL)",
    )
    p.add_argument(
        "--type",
        dest="opportunity_type",
        type=str,
        choices=(
            "UNDERVALUED_QUALITY",
            "COMPOUNDERS",
            "TURNAROUNDS",
            "SPECIAL_SITUATIONS",
        ),
        help="Filter by opportunity type",
    )
    add_refresh_arguments(p)
    p.set_defaults(func=_run)


def _color_for(op_type: str) -> str:
    if op_type == "UNDERVALUED_QUALITY":
        return green(op_type)
    if op_type == "COMPOUNDERS":
        return green(op_type)
    if op_type == "TURNAROUNDS":
        return yellow(op_type)
    return yellow(op_type)


def _run(args):
    universe = None
    if args.tickers:
        universe = [t.strip().upper() for t in args.tickers.split(",")]

    if universe:
        refresh_analysis_inputs(universe, args, explicit=True)

    print_header("Opportunities")
    service = build_investment_screener(universe)
    opportunities = service.opportunities()

    if args.opportunity_type:
        opportunities = [o for o in opportunities if o["type"] == args.opportunity_type]

    if not opportunities:
        print(f"  {yellow('No opportunities detected in the current universe.')}")
        print("  Hint: make sure you have data loaded with 'main.py load-data TICKER'.")
        return

    print(f"  {green(str(len(opportunities)))} opportunities detected\n")
    for opportunity in opportunities:
        signal = opportunity.get("signal", "")
        print(
            f"  {bold(opportunity['ticker'])} — "
            f"{_color_for(opportunity['type'])} "
            f"({dim(opportunity['confidence'])})"
        )
        print_key_value("  Ranking", f"{opportunity['rank_score']:.1f}")
        print_key_value("  Signal", signal)
        for reason in opportunity["reason"]:
            print(f"    - {reason}")
        print()

    print(green("Done."))
