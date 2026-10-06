from backend.analytics.interpretation import print_analysis
from backend.app.cli import (
    add_refresh_arguments,
    build_analysis_service,
    refresh_analysis_inputs,
)
from cli.formatters import (
    bold,
    dim,
    green,
    print_header,
    print_key_value,
    red,
    yellow,
)


def register(subparsers):
    p = subparsers.add_parser(
        "buffett-analysis",
        help="Buffett analysis: filter, moat and composite score",
        description=(
            "Evaluates business quality (moat), financial strength and generates "
            "interpretable insights in Buffett/Munger style."
        ),
    )
    p.add_argument(
        "tickers",
        type=str,
        nargs="+",
        help="Ticker(s) to evaluate (e.g.: AAPL or AAPL MSFT GOOGL)",
    )
    p.add_argument(
        "--full",
        action="store_true",
        help="In addition to the summary, prints the full fundamental analysis",
    )
    add_refresh_arguments(p)
    p.set_defaults(func=_run)


def _moat_color(moat_type: str) -> str:
    if moat_type == "STRONG":
        return green(moat_type)
    if moat_type == "MODERATE":
        return yellow(moat_type)
    return red(moat_type)


def _rating_color(rating: str) -> str:
    if rating in ("A", "B"):
        return green(rating)
    if rating == "C":
        return yellow(rating)
    return red(rating)


def _run(args):
    service = build_analysis_service()
    tickers = [t.upper().strip() for t in args.tickers]
    refresh_analysis_inputs(tickers, args)

    for raw_ticker in tickers:
        ticker = raw_ticker
        print_header(f"Buffett analysis: {ticker}")

        try:
            result = service.analyze(ticker)
        except Exception as e:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
            print(f"  {red('ERROR:')} {e}")
            continue

        if result is None:
            print(f"  {red('Not enough data for')} {ticker}")
            continue

        composite = result["composite_score"]
        moat = result["moat_analysis"]

        print_key_value("Buffett score", f"{result['buffett_score']:.1f}/100")
        for pillar, value in result["buffett_breakdown"].items():
            print_key_value(
                f"  {pillar.replace('_', ' ').title()}",
                f"{value:.1f}",
            )
        print_key_value("Moat", _moat_color(moat["moat_type"]))
        print_key_value("  Moat score", f"{moat['moat_score']:.1f}")
        print_key_value(
            "Composite score",
            f"{composite['total_score']:.1f} ({_rating_color(composite['rating'])})",
        )
        print_key_value("Confidence", composite["confidence"])

        margin = result.get("dcf_margin_of_safety")
        if margin is not None:
            label = green(f"{margin:.0%}") if margin >= 0.15 else dim(f"{margin:.0%}")
            print_key_value("Margin of safety (DCF)", label)

        print(f"  {bold('Insights')}")
        for insight in result["insight"]:
            print(f"    - {insight}")

        moat_lines = moat.get("strengths", []) + [
            f"weakness: {w}" for w in moat.get("weaknesses", [])
        ]
        if moat_lines:
            print(f"  {bold('Moat signals')}")
            for line in moat_lines:
                print(f"    - {line}")

        if args.full:
            print_analysis(result)

        print()
