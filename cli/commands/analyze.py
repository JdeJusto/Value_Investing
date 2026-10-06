from backend.analytics.interpretation import print_analysis as _print_analysis
from backend.app.cli import (
    add_refresh_arguments,
    build_analysis_service,
    refresh_analysis_inputs,
)
from cli.formatters import print_header, red


def register(subparsers):
    p = subparsers.add_parser(
        "analyze",
        help="Full fundamental analysis of one or more tickers",
        description=(
            "Runs the full analysis (ratios, scoring, DCF) and shows detailed results."
        ),
    )
    p.add_argument(
        "tickers",
        type=str,
        nargs="+",
        help="Ticker(s) to analyze (e.g.: AAPL or AAPL MSFT GOOGL)",
    )
    add_refresh_arguments(p)
    p.set_defaults(func=_run)


def _run(args):
    service = build_analysis_service()
    tickers = [t.upper().strip() for t in args.tickers]
    refresh_analysis_inputs(tickers, args)

    for ticker in tickers:
        t = ticker
        print_header(f"Fundamental analysis: {t}")

        try:
            result = service.analyze(t)
        except Exception as e:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
            print(f"  {red('ERROR:')} {e}")
            continue

        if result is None:
            print(f"  {red('Not enough data for')} {t}")
            continue

        _print_analysis(result)
