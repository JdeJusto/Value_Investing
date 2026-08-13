"""CLI: backtest a strategy against historical yearly snapshots."""

from backend.app.cli import build_financial_repository, build_universe
from backend.backtesting import get_strategy, run_backtest, sort_snapshots
from backend.intelligence.scoring_model import assess_investment
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

MIN_YEARS = 3


def register(subparsers):
    p = subparsers.add_parser(
        "backtest",
        help="Backtesting sobre snapshots anuales (determinista)",
        description=(
            "Reconstruye analisis historicos desde el repo y simula una "
            "cartera igual-ponderada con rebalanceo cada N anios. "
            "Usa --prices TICKER,AÑO,PRECIO por linea para retornos reales."
        ),
    )
    p.add_argument(
        "--strategy",
        choices=("buffett", "momentum"),
        default="buffett",
        help="Estrategia de seleccion (default: buffett)",
    )
    p.add_argument(
        "--years", type=int, default=10, help="Usar los ultimos N anios fiscales"
    )
    p.add_argument("--top", type=int, default=5, help="Numero de titulos por cartera")
    p.add_argument("--rebalance", type=int, default=1, help="Rebalancear cada N anios")
    p.add_argument(
        "--prices",
        default=None,
        help="Archivo con precios historicos: 'TICKER,AÑO,PRECIO' por linea",
    )
    p.add_argument(
        "tickers",
        type=str,
        nargs="*",
        help="Tickers a incluir (opcional: universo cargado)",
    )
    p.set_defaults(func=_run)


def _load_prices(path):
    prices = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",")
            if len(parts) < 3:
                continue
            ticker, year, price = parts[0].strip(), int(parts[1]), float(parts[2])
            prices.setdefault(ticker, {})[year] = price
    return prices


def _build_snapshots(tickers, years):
    repo = build_financial_repository()
    snapshots_by_year = {}
    for ticker in tickers:
        all_rows = repo.list_all(ticker)
        complete = [r for r in all_rows if r.is_complete]
        rows = complete if len(complete) >= MIN_YEARS else all_rows
        rows = sorted(
            rows,
            key=lambda r: (r.fiscal_year is not None, r.fiscal_year or 0),
        )
        rows = rows[-years:]
        for index in range(MIN_YEARS, len(rows) + 1):
            partial = rows[:index]
            analysis = assess_investment(partial, reliability=None)
            year = partial[-1].fiscal_year
            entry = snapshots_by_year.setdefault(
                year, {"year": year, "analyses": {}, "prices": {}}
            )
            entry["analyses"][ticker] = analysis
    return snapshots_by_year


def _run(args):
    if args.top < 1:
        parser_error = "top must be >= 1"
        raise SystemExit(f"error: {parser_error}")
    universe = build_universe(args.tickers)
    prices = _load_prices(args.prices) if args.prices else {}
    snapshots_by_year = _build_snapshots(universe, args.years)
    snapshots = sort_snapshots(list(snapshots_by_year.values()))

    if prices:
        for snapshot in snapshots:
            year = snapshot["year"]
            for ticker, ticker_prices in prices.items():
                prev = ticker_prices.get(year - 1)
                current = ticker_prices.get(year)
                snapshot["prices"][ticker] = (prev, current)
    else:
        for snapshot in snapshots:
            for ticker in snapshot["analyses"]:
                snapshot["prices"][ticker] = (1.0, 1.0)

    print_header(
        f"Backtest {args.strategy}: {len(snapshots)} snapshots, "
        f"top-{args.top}, rebalance cada {args.rebalance} anio(s)"
    )
    if not snapshots:
        print(
            f"  {yellow('Sin historico suficiente.')} Carga {MIN_YEARS}+ anios con "
            "'main.py load-data TICKER' antes de backtestear."
        )
        return

    result = run_backtest(
        snapshots,
        get_strategy(args.strategy),
        top_n=args.top,
        rebalance_every=args.rebalance,
    )

    metrics = [
        (
            "CAGR (media geometrica)",
            fmt_pct(result["cagr"]) if result["cagr"] is not None else dim("N/A"),
        ),
        (
            "Max drawdown",
            (
                red(fmt_pct(result["max_drawdown"]))
                if result["max_drawdown"] < 0
                else fmt_pct(result["max_drawdown"])
            ),
        ),
        (
            "Sharpe",
            f"{result['sharpe']:.2f}" if result["sharpe"] is not None else dim("N/A"),
        ),
        (
            "Win rate",
            (
                fmt_pct(result["win_rate"])
                if result["win_rate"] is not None
                else dim("N/A")
            ),
        ),
        ("Periodos", str(result["periods"])),
    ]
    print_table([("Metrica", 0), ("Valor", 0)], metrics)

    print(f"\n  {bold('Seleccion en el primer periodo:')}")
    if not result["selected_first_period"]:
        print(f"  {dim('sin candidatos rankeables en el primer periodo')}")
    for ticker in result["selected_first_period"]:
        analysis = snapshots[0]["analyses"].get(ticker)
        rank = analysis.get("rank_score") if analysis else None
        label = f"ranking {rank:.1f}" if rank is not None else "sin ranking"
        print(f"  - {green(ticker):<10} {label}")

    print()
    if not prices:
        print(dim("Sin --prices: retornos planos; solo mide la seleccion."))
    print(green("Listo."))
