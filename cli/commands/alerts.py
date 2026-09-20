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
        help="Evaluar senales de compra/venta y eventos",
        description=(
            "Ejecuta el motor de alertas (BUY_SIGNAL, SELL_WARNING, "
            "TRIGGER_EVENT) sobre el universo. Con --state JSON evalua "
            "caidas de score respecto al estado anterior."
        ),
    )
    p.add_argument(
        "--state",
        default=None,
        help="JSON con analisis previos ({ticker: analysis}) para SELL_WARNING",
    )
    p.add_argument(
        "tickers",
        type=str,
        nargs="*",
        help="Tickers a evaluar (opcional: universo cargado)",
    )
    add_refresh_arguments(p)
    p.set_defaults(func=_run)


def _load_state(path):
    import json

    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        print(f"  {red('ERROR:')} No existe el archivo de estado '{path}'.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"  {red('ERROR:')} El archivo de estado '{path}' no es JSON valido.")
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

    print_header(f"Alertas ({len(analyses)} empresas evaluadas)")
    alerts = run(analyses, previous)
    if not alerts:
        print(
            f"  {yellow('Sin alertas.')} La cartera se mantiene dentro de parametros."
        )
        print()
        print(green("Listo."))
        return

    for alert in alerts:
        reason = "; ".join(alert.reason) if alert.reason else "-"
        label = {
            "BUY_SIGNAL": "COMPRA",
            "SELL_WARNING": "VENTA",
            "TRIGGER_EVENT": "EVENTO",
        }[alert.alert_type]
        print(
            f"  {bold(alert.ticker):<10} [{label}] {alert.alert_type} "
            f"(confianza {alert.confidence}): {reason}"
        )

    print()
    print(green("Listo."))
