from backend.app.cli import (
    add_refresh_arguments,
    build_analysis_service,
    build_universe,
    refresh_analysis_inputs,
)
from backend.screener.ranking_engine import (
    fundamental_momentum,
    momentum_reasons,
    rank_score,
)
from backend.screener.signals import detect_trigger
from cli.formatters import (
    bold,
    dim,
    fmt_pct,
    green,
    print_header,
    print_table,
    red,
    yellow,
)


def register(subparsers):
    p = subparsers.add_parser(
        "momentum",
        help="Clasificacion por momentum fundamental",
        description=(
            "Ordena por el factor de momentum (aceleracion de ingresos, "
            "margenes, ROIC y FCF) con su trigger dominante."
        ),
    )
    p.add_argument(
        "tickers",
        type=str,
        nargs="*",
        help="Ticker(s) a evaluar (opcional: usa el universo cargado)",
    )
    add_refresh_arguments(p)
    p.set_defaults(func=_run)


def _delta_color(value):
    if value is None:
        return dim("N/A")
    if value >= 0:
        return green(f"{value * 100:+.1f}pp")
    return red(f"{value * 100:+.1f}pp")


def _run(args):
    service = build_analysis_service()
    universe = build_universe(args.tickers)
    refresh_analysis_inputs(
        universe, args, explicit=bool(args.tickers)
    )

    rows = []
    for ticker in universe:
        result = service.analyze(ticker)
        if result is None:
            continue
        micro_momentum = fundamental_momentum(result)
        deltas = result.get("delta_metrics") or {}
        rows.append(
            {
                "ticker": ticker,
                "momentum": micro_momentum,
                "rank_score": rank_score(result),
                "revenue_growth_delta": deltas.get("revenue_growth_delta"),
                "gross_margin_delta": deltas.get("gross_margin_delta"),
                "roic_delta": deltas.get("roic_delta"),
                "fcf_delta": deltas.get("fcf_delta"),
                "trigger": detect_trigger(result),
                "item": result,
            }
        )

    rows.sort(key=lambda r: r["momentum"], reverse=True)

    print_header(f"Momentum fundamental ({len(rows)} empresas)")
    if not rows:
        print(
            f"  {yellow('Sin datos para evaluar.')} Carga datos con 'main.py load-data TICKER'."
        )
        return

    headers = [
        ("#", 0),
        ("Ticker", 0),
        ("Momentum", 1),
        ("Rev Δ", 0),
        ("Margen Δ", 0),
        ("ROIC Δ", 0),
        ("FCF Δ", 0),
        ("Trigger", 0),
        ("Ranking", 1),
    ]
    table_rows = []
    for i, row in enumerate(rows, start=1):
        table_rows.append(
            [
                str(i),
                row["ticker"],
                fmt_pct(row["momentum"]),
                _delta_color(row["revenue_growth_delta"]),
                _delta_color(row["gross_margin_delta"]),
                _delta_color(row["roic_delta"]),
                _delta_color(row["fcf_delta"]),
                row["trigger"] if row["trigger"] else dim("-"),
                f"{row['rank_score']:.1f}",
            ]
        )
    print_table(headers, table_rows)

    print(f"\n  {bold('Por que?')}")
    for row in rows[:10]:
        reasons = momentum_reasons(row["item"])
        if not reasons:
            reasons = [dim("sin movimientos significativos")]
        print(
            f"  {green(str(rows.index(row) + 1)):>3}. {bold(row['ticker'])} — {'; '.join(reasons)}"
        )

    print()
    print(green("Listo."))
