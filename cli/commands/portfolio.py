from datetime import datetime

from backend.app.cli import add_demo_argument, build_portfolio_service
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
        help="Portfolio tracking: positions, PnL and allocation",
        description=(
            "Manages positions (add/remove/exit), shows value, realized and "
            "unrealized PnL, and analyzes risk concentration "
            "and sector exposure."
        ),
    )
    sub = p.add_subparsers(dest="action", title="Actions", required=True)

    add = sub.add_parser("add", help="Add (or average) a position")
    add.add_argument("ticker", type=str)
    add.add_argument("quantity", type=float)
    add.add_argument("avg_price", type=float)
    add.add_argument("--thesis", type=str, default="", help="Investment thesis")
    add.add_argument(
        "--signal",
        dest="signal_at_entry",
        type=str,
        default="",
        help="Signal at entry time (e.g.: BUY)",
    )
    add.add_argument(
        "--date",
        type=lambda s: datetime.fromisoformat(s),
        default=None,
        help="ISO entry date (default: today)",
    )
    add_demo_argument(add)
    add.set_defaults(func=_add)

    exit_ = sub.add_parser("exit", help="Close a position by selling")
    exit_.add_argument("ticker", type=str)
    exit_.add_argument("price", type=float)
    exit_.add_argument(
        "--date",
        type=lambda s: datetime.fromisoformat(s),
        default=None,
        help="ISO exit date (default: today)",
    )
    add_demo_argument(exit_)
    exit_.set_defaults(func=_exit)

    remove = sub.add_parser("remove", help="Delete a position without recording a sale")
    remove.add_argument("ticker", type=str)
    add_demo_argument(remove)
    remove.set_defaults(func=_remove)

    view = sub.add_parser("view", help="Positions enriched with scores")
    add_demo_argument(view)
    view.set_defaults(func=_view)

    sub.add_parser(
        "performance",
        help="Portfolio returns, PnL and allocation analysis",
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
            f"Position {position.ticker} recorded"
            f" ({position.quantity} shares at {position.avg_price:,.2f})"
        )
    )


def _exit(args):
    service = build_portfolio_service()
    position = service.exit(args.ticker, args.price)
    if position is None:
        print(f"  {red('No open position for')} {args.ticker}")
        return
    print(
        green(f"Position {args.ticker} closed")
        + f" — Realized PnL {position.realized_pnl:+,.2f}"
    )


def _remove(args):
    service = build_portfolio_service()
    position = service.remove(args.ticker)
    if position is None:
        print(f"  {red('No position for')} {args.ticker}")
        return
    print(f"  {yellow('Position removed:')} {args.ticker}")


def _view(args):
    service = build_portfolio_service()
    positions = service.view()
    print_header(f"Portfolio ({len(positions)} positions)")
    if not positions:
        print(
            f"  {yellow('Empty portfolio.')} Use 'main.py portfolio add TICKER QUANTITY PRICE'."
        )
        return

    headers = [
        ("Ticker", 0),
        ("Qty", 1),
        ("Price", 1),
        ("Value", 1),
        ("Return", 1),
        ("Buffett", 1),
        ("Moat", 0),
        ("Signal", 0),
        ("Opp.", 0),
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

    print(f"  {bold('Thesis')}")
    for p in positions:
        thesis = p["thesis"] or dim("(no thesis)")
        print(f"  - {bold(p['ticker'])}: {thesis}")


def _performance(args):
    service = build_portfolio_service()
    perf = service.performance()

    return_label = (
        fmt_pct(perf["total_return"])
        if perf["total_return"] is not None
        else dim("N/A")
    )
    print_header("Portfolio performance")
    print_key_value("Market value", fmt_dollar(perf["market_value"]))
    print_key_value("Cost basis", fmt_dollar(perf["cost_basis"]))
    print_key_value("Unrealized PnL", fmt_dollar(perf["unrealized_pnl"]))
    print_key_value("Realized PnL", fmt_dollar(perf["realized_pnl"]))
    print_key_value("Total PnL", fmt_dollar(perf["total_pnl"]))
    print_key_value("Total return", return_label)

    allocation = perf["allocation"]
    if allocation["overconcentrated"]:
        print(f"  {red('Overconcentration:')}")
        for finding in allocation["overconcentrated"]:
            print(
                f"    - {finding['ticker']}: {finding['weight']:.0%}"
                f" (limit {finding['threshold']:.0%})"
            )
    else:
        print(f"  {green('No overconcentration.')}")

    if allocation["sector_exposure"]:
        print(f"  {bold('Sector exposure')}")
        for exposure in allocation["sector_exposure"]:
            print(f"    - {exposure['sector']}: {exposure['weight']:.0%}")

    risk = allocation["risk"]
    print(f"  {bold('Concentration risk')}")
    print_key_value("Largest position", f"{risk['largest_position_weight']:.0%}")
    print_key_value("Top-5", f"{risk['top_n_share']:.0%}")
    print_key_value("HHI", f"{risk['hhi']:.3f}")
