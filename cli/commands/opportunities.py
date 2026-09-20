from backend.app.cli import (
    add_refresh_arguments,
    build_investment_screener,
    refresh_analysis_inputs,
)
from cli.formatters import bold, dim, green, print_header, print_key_value, yellow


def register(subparsers):
    p = subparsers.add_parser(
        "opportunities",
        help="Oportunidades detectadas: quality barata, compounders, turnarounds",
        description=(
            "Analiza el universo cargado y muestra situaciones accionables "
            "con su tipo, confianza y las razones de cada deteccion."
        ),
    )
    p.add_argument(
        "--tickers",
        type=str,
        help="Tickers separados por coma (ej: AAPL,MSFT,GOOGL)",
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
        help="Filtrar por tipo de oportunidad",
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

    print_header("Oportunidades")
    service = build_investment_screener(universe)
    opportunities = service.opportunities()

    if args.opportunity_type:
        opportunities = [o for o in opportunities if o["type"] == args.opportunity_type]

    if not opportunities:
        print(f"  {yellow('No se detectaron oportunidades en el universo actual.')}")
        print(
            "  Sugerencia: asegurate de tener datos cargados con 'main.py load-data TICKER'."
        )
        return

    print(f"  {green(str(len(opportunities)))} oportunidades detectadas\n")
    for opportunity in opportunities:
        signal = opportunity.get("signal", "")
        print(
            f"  {bold(opportunity['ticker'])} — "
            f"{_color_for(opportunity['type'])} "
            f"({dim(opportunity['confidence'])})"
        )
        print_key_value("  Ranking", f"{opportunity['rank_score']:.1f}")
        print_key_value("  Senal", signal)
        for reason in opportunity["reason"]:
            print(f"    - {reason}")
        print()

    print(green("Listo."))
