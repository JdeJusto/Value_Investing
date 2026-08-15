from backend.app.cli import build_analysis_service, build_universe
from backend.intelligence.anomaly_detection import anomaly_summary
from cli.formatters import bold, green, print_header, red, yellow


def register(subparsers):
    p = subparsers.add_parser(
        "anomalies",
        help="Anomalias en los fundamentales del ultimo ejercicio",
        description=(
            "Compara el ultimo anio contra la media/desviacion historica (z-score) "
            "y saltos anormales interanuales, marcando cada flag con severidad."
        ),
    )
    p.add_argument(
        "tickers",
        type=str,
        nargs="*",
        help="Ticker(s) a inspeccionar (opcional: usa el universo cargado)",
    )
    p.set_defaults(func=_run)


def _severity_color(severity: str) -> str:
    return red(severity) if severity == "STRONG" else yellow(severity)


def _direction_symbol(direction: str) -> str:
    return "+" if direction == "UP" else "−"


def _run(args):
    service = build_analysis_service()
    universe = build_universe(args.tickers)

    total_flags = 0
    for ticker in universe:
        result = service.analyze(ticker)
        if result is None:
            continue
        anomalies = result.get("anomalies") or []
        if not anomalies:
            continue

        total_flags += len(anomalies)
        print_header(f"Anomalias: {ticker}")
        print(f"  {anomaly_summary(anomalies)}")
        for anomaly in anomalies:
            detail = (
                f"z={anomaly['zscore']:+.2f} (media {anomaly['mean']:,.0f}, "
                f"desv {anomaly['stddev']:,.0f})"
                if anomaly["type"] == "zscore"
                else f"cambio de {anomaly['change']:+.0%}"
            )
            print(
                f"  {_direction_symbol(anomaly['direction'])} "
                f"{bold(anomaly['metric'])} ({anomaly['year']}) — "
                f"{detail} [{_severity_color(anomaly['severity'])}]"
            )
        print()

    if total_flags == 0:
        print(f"  {green('Sin anomalias')} en el universo analizado.")

    print(green("Listo."))
