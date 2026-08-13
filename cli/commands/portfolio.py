from datetime import datetime

from backend.app.cli import build_portfolio_service
from cli.formatters import (
    bold,
    dim,
    fmt_dollar,
    fmt_pct,
    green,
    print_header,
    print_key_value,
    print_table,
    red,
    yellow,
)


def register(subparsers):
    p = subparsers.add_parser(
        "portfolio",
        help="Seguimiento de cartera: posiciones, PnL y asignacion",
        description=(
            "Gestiona posiciones (add/remove/exit), muestra valor, PnL "
            "realizado y no realizado, y analiza concentracion de riesgo "
            "y exposicion por sector."
        ),
    )
    sub = p.add_subparsers(dest="action", title="Acciones", required=True)

    add = sub.add_parser("add", help="Anade (o promedia) una posicion")
    add.add_argument("ticker", type=str)
    add.add_argument("quantity", type=float)
    add.add_argument("avg_price", type=float)
    add.add_argument("--thesis", type=str, default="", help="Tesis de inversion")
    add.add_argument(
        "--signal",
        dest="signal_at_entry",
        type=str,
        default="",
        help="Senal en el momento de compra (ej: BUY)",
    )
    add.add_argument(
        "--date",
        type=lambda s: datetime.fromisoformat(s),
        default=None,
        help="Fecha de entrada ISO (default: hoy)",
    )
    add.set_defaults(func=_add)

    exit_ = sub.add_parser("exit", help="Cierra una posicion vendiendo")
    exit_.add_argument("ticker", type=str)
    exit_.add_argument("price", type=float)
    exit_.add_argument(
        "--date",
        type=lambda s: datetime.fromisoformat(s),
        default=None,
        help="Fecha de venta ISO (default: hoy)",
    )
    exit_.set_defaults(func=_exit)

    remove = sub.add_parser("remove", help="Borra una posicion sin registrar venta")
    remove.add_argument("ticker", type=str)
    remove.set_defaults(func=_remove)

    sub.add_parser(
        "view", help="Posiciones enriquecidas con puntuaciones"
    ).set_defaults(func=_view)

    sub.add_parser(
        "performance",
        help="Rentabilidad, PnL y analisis de asignacion de la cartera",
    ).set_defaults(func=_performance)


def _add(args):
    service = build_portfolio_service()
    position = service.add(
        ticker=args.ticker,
        quantity=args.quantity,
        avg_price=args.avg_price,
        entry_date=args.date,
        thesis=args.thesis,
        signal_at_entry=args.signal_at_entry,
    )
    print(
        green(
            f"Posicion {position.ticker} registrada"
            f" ({position.quantity} acciones a {position.avg_price:,.2f})"
        )
    )


def _exit(args):
    service = build_portfolio_service()
    position = service.exit(args.ticker, args.price)
    if position is None:
        print(f"  {red('Sin posicion abierta para')} {args.ticker}")
        return
    print(
        green(f"Posicion {args.ticker} cerrada")
        + f" — PnL realizado {position.realized_pnl:+,.2f}"
    )


def _remove(args):
    service = build_portfolio_service()
    position = service.remove(args.ticker)
    if position is None:
        print(f"  {red('Sin posicion para')} {args.ticker}")
        return
    print(f"  {yellow('Posicion borrada:')} {args.ticker}")


def _view(args):
    service = build_portfolio_service()
    positions = service.view()
    print_header(f"Cartera ({len(positions)} posiciones)")
    if not positions:
        print(
            f"  {yellow('Cartera vacia.')} Usa 'main.py portfolio add TICKER CANTIDAD PRECIO'."
        )
        return

    headers = [
        ("Ticker", 0),
        ("Cant.", 1),
        ("Precio", 1),
        ("Valor", 1),
        ("Retorno", 1),
        ("Buffett", 1),
        ("Moat", 0),
        ("Senal", 0),
        ("Oport.", 0),
    ]
    rows = []
    for p in positions:
        ret = (
            fmt_pct(p["unrealized_return"])
            if p["unrealized_return"] is not None
            else dim("N/A")
        )
        if p["unrealized_return"] is not None:
            ret = green(ret) if p["unrealized_return"] >= 0 else red(ret)
        rows.append(
            [
                p["ticker"],
                f"{p['quantity']:,.0f}",
                fmt_dollar(p["current_price"]),
                fmt_dollar(p["quantity"] * p["current_price"]),
                ret,
                (
                    f"{p['buffett_score']:.0f}"
                    if p["buffett_score"] is not None
                    else dim("N/A")
                ),
                p["moat"] or dim("N/A"),
                p["signal"] or dim("N/A"),
                p["opportunity_type"] or dim("-"),
            ]
        )
    print_table(headers, rows)

    print(f"  {bold('Tesis')}")
    for p in positions:
        thesis = p["thesis"] or dim("(sin tesis)")
        print(f"  - {bold(p['ticker'])}: {thesis}")


def _performance(args):
    service = build_portfolio_service()
    perf = service.performance()

    return_label = (
        fmt_pct(perf["total_return"])
        if perf["total_return"] is not None
        else dim("N/A")
    )
    print_header("Rendimiento de la cartera")
    print_key_value("Valor de mercado", fmt_dollar(perf["market_value"]))
    print_key_value("Coste", fmt_dollar(perf["cost_basis"]))
    print_key_value("PnL no realizado", fmt_dollar(perf["unrealized_pnl"]))
    print_key_value("PnL realizado", fmt_dollar(perf["realized_pnl"]))
    print_key_value("PnL total", fmt_dollar(perf["total_pnl"]))
    print_key_value("Retorno total", return_label)

    allocation = perf["allocation"]
    if allocation["overconcentrated"]:
        print(f"  {red('Sobreconcentracion:')}")
        for finding in allocation["overconcentrated"]:
            print(
                f"    - {finding['ticker']}: {finding['weight']:.0%}"
                f" (limite {finding['threshold']:.0%})"
            )
    else:
        print(f"  {green('Sin sobreconcentracion.')}")

    if allocation["sector_exposure"]:
        print(f"  {bold('Exposicion por sector')}")
        for exposure in allocation["sector_exposure"]:
            print(f"    - {exposure['sector']}: {exposure['weight']:.0%}")

    risk = allocation["risk"]
    print(f"  {bold('Riesgo de concentracion')}")
    print_key_value("Posicion mayor", f"{risk['largest_position_weight']:.0%}")
    print_key_value("Top-5", f"{risk['top_n_share']:.0%}")
    print_key_value("HHI", f"{risk['hhi']:.3f}")
