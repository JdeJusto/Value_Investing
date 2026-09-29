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
        help="Analisis fundamental completo de uno o varios tickers",
        description=(
            "Ejecuta el analisis completo (ratios, scoring, DCF) y "
            "muestra resultados detallados."
        ),
    )
    p.add_argument(
        "tickers",
        type=str,
        nargs="+",
        help="Ticker(s) a analizar (ej: AAPL o AAPL MSFT GOOGL)",
    )
    add_refresh_arguments(p)
    p.set_defaults(func=_run)


def _run(args):
    service = build_analysis_service()
    tickers = [t.upper().strip() for t in args.tickers]
    refresh_analysis_inputs(tickers, args)

    for ticker in tickers:
        t = ticker
        print_header(f"Analisis fundamental: {t}")

        try:
            result = service.analyze(t)
        except Exception as e:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
            print(f"  {red('ERROR:')} {e}")
            continue

        if result is None:
            print(f"  {red('Sin datos suficientes para')} {t}")
            continue

        _print_analysis(result)
