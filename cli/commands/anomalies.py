from backend.app.cli import (
    add_refresh_arguments,
    build_analysis_service,
    build_universe,
    refresh_analysis_inputs,
)
from backend.intelligence.anomaly_detection import anomaly_summary
from cli.formatters import bold, green, print_header, red, yellow


def register(subparsers):
    p = subparsers.add_parser(
        "anomalies",
        help="Anomalies in the last fiscal year's fundamentals",
        description=(
            "Compares the latest year against the historical mean/deviation "
            "(z-score) and abnormal year-over-year jumps, flagging each one "
            "with its severity."
        ),
    )
    p.add_argument(
        "tickers",
        type=str,
        nargs="*",
        help="Ticker(s) to inspect (optional: uses the loaded universe)",
    )
    add_refresh_arguments(p)
    p.set_defaults(func=_run)


def _severity_color(severity: str) -> str:
    return red(severity) if severity == "STRONG" else yellow(severity)


def _direction_symbol(direction: str) -> str:
    return "+" if direction == "UP" else "−"


def _run(args):
    service = build_analysis_service()
    universe = build_universe(args.tickers)
    refresh_analysis_inputs(universe, args, explicit=bool(args.tickers))

    total_flags = 0
    for ticker in universe:
        result = service.analyze(ticker)
        if result is None:
            continue
        anomalies = result.get("anomalies") or []
        if not anomalies:
            continue

        total_flags += len(anomalies)
        print_header(f"Anomalies: {ticker}")
        print(f"  {anomaly_summary(anomalies)}")
        for anomaly in anomalies:
            detail = (
                f"z={anomaly['zscore']:+.2f} (mean {anomaly['mean']:,.0f}, "
                f"std {anomaly['stddev']:,.0f})"
                if anomaly["type"] == "zscore"
                else f"change of {anomaly['change']:+.0%}"
            )
            print(
                f"  {_direction_symbol(anomaly['direction'])} "
                f"{bold(anomaly['metric'])} ({anomaly['year']}) — "
                f"{detail} [{_severity_color(anomaly['severity'])}]"
            )
        print()

    if total_flags == 0:
        print(f"  {green('No anomalies')} in the analyzed universe.")

    print(green("Done."))
