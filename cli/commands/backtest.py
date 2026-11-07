"""CLI: backtest a strategy against historical yearly snapshots."""

import csv
import json
from pathlib import Path

from backend.app.cli import build_financial_repository, build_universe
from backend.backtesting import get_strategy, run_backtest, sort_snapshots
from backend.intelligence.scoring_model import assess_investment
from cli.formatters import (
    bold,
    dim,
    fmt_pct,
    green,
    print_header,
    print_section,
    print_table,
    red,
    yellow,
)

MIN_YEARS = 3


def register(subparsers):
    p = subparsers.add_parser(
        "backtest",
        help="Backtesting over yearly snapshots (deterministic)",
        description=(
            "Rebuilds historical analyses from the repo and simulates an "
            "equal-weighted portfolio with rebalancing every N years. "
            "Use --prices TICKER,YEAR,PRICE per line for real returns."
        ),
    )
    p.add_argument(
        "--strategy",
        choices=("buffett", "momentum"),
        default="buffett",
        help="Selection strategy (default: buffett)",
    )
    p.add_argument(
        "--methodology",
        action="append",
        default=None,
        help=(
            "Backtest a book methodology by name (graham, graham_dodd, "
            "buffett_classic, fisher_quantitative_subset, lynch_garp, marks). "
            "Repeatable; greenblatt is excluded (point-in-time ranking)."
        ),
    )
    p.add_argument(
        "--universe",
        default="sp500",
        help="Universe subset for --methodology (default sp500)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Max tickers for --methodology (default 25, PoC)",
    )
    p.add_argument("--years", type=int, default=10, help="Use the last N fiscal years")
    p.add_argument(
        "--top", type=int, default=5, help="Number of holdings per portfolio"
    )
    p.add_argument("--rebalance", type=int, default=1, help="Rebalance every N years")
    p.add_argument(
        "--prices",
        default=None,
        help="File with historical prices: 'TICKER,YEAR,PRICE' per line",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print the result payload as JSON (methodology or strategy mode)",
    )
    p.add_argument(
        "--equal-weight",
        action="store_true",
        help=(
            "Legacy: equal-weight every positive signal instead of the "
            "STRONG 60 / BUY 30 / WEAK 10 tier weighting"
        ),
    )
    p.add_argument(
        "tickers",
        type=str,
        nargs="*",
        help="Tickers to include (optional: loaded universe)",
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


def _universe_members(spec: str) -> list[str]:
    """Every ticker in a named universe subset (before the PoC size cap)."""
    path = Path(__file__).resolve().parents[2] / "config" / "universe.csv"
    selected = spec.upper()
    include_all = spec.lower() in {"", "all"} or selected == "ALL"
    tickers: list[str] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                sources = {
                    source.strip().upper()
                    for source in (row.get("source_index") or "").split(",")
                }
                if include_all or selected in sources:
                    ticker = (row.get("ticker") or "").strip().upper()
                    if ticker:
                        tickers.append(ticker)
    except OSError:
        return []
    return sorted(set(tickers))


def _load_universe_subset(spec: str, limit: int) -> list[str]:
    """Evenly spaced deterministic sample of a named universe (PoC size cap)."""
    unique = _universe_members(spec)
    if not limit or limit >= len(unique):
        return unique
    step = len(unique) / max(int(limit), 1)
    return [unique[int(index * step)] for index in range(int(limit))]


def parse_methodology_arg(value: str) -> tuple[str, str | None]:
    """Parse ``'graham:BUY'`` into ``('graham', 'BUY')``."""
    if ":" in value:
        name, verdict = value.split(":", 1)
        return name.strip().lower(), verdict.strip().upper()
    return value.strip().lower(), None


def _pct_or_dash(value: float | None) -> str:
    return fmt_pct(value) if value is not None else dim("—")


def _ratio_or_dash(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else dim("—")


def _rule_label(rule_id: str) -> str:
    """Short human label from a rule id (``graham.criterion_6_pe`` -> pe)."""
    return rule_id.rsplit(".", 1)[-1].replace("criterion_", "").replace("_", " ")


def _render_year_verdicts(result) -> None:
    from backend.services.methodology_backtest_service import VERDICT_ORDER

    print_section("Verdicts by year")
    rows = []
    for item in result.per_year:
        label = str(item.year) + ("" if item.complete else " (YTD)")
        rows.append(
            [label] + [str(item.verdicts.get(verdict, 0)) for verdict in VERDICT_ORDER]
        )
    print_table(
        [
            ("Year", 0),
            ("STRONG", 1),
            ("BUY", 1),
            ("WEAK", 1),
            ("WATCH", 1),
            ("HOLD", 1),
            ("AVOID", 1),
            ("N/A", 1),
            ("INS", 1),
        ],
        rows,
    )
    print(
        dim(
            "  N/A: banks/REITs (not applicable). INSUFF: missing fundamentals "
            "for that year."
        )
    )


def _render_performance(result) -> None:
    complete = result.complete_years
    if complete:
        window = f"{min(complete)}-{max(complete)} ({len(complete)}y)"
    else:
        window = "no complete years"
    weighting = result.weighting
    weighting_label = (
        "tier (STRONG 60 / BUY 30 / WEAK 10)"
        if weighting == "tier"
        else "equal (legacy)"
    )
    rows = [
        ["Weighting", weighting_label],
        ["Complete years", window],
        [
            "Portfolio CAGR",
            _pct_or_dash(result.annualized_return)
            + ("" if result.invested_years else "  (all cash)"),
        ],
        ["Opportunity set CAGR", _pct_or_dash(result.opportunity_set_annualized)],
        ["SPY CAGR", _pct_or_dash(result.spy_annualized)],
        ["Alpha vs opportunity set", _pct_or_dash(result.alpha_vs_opportunity_set)],
        ["Alpha vs SPY", _pct_or_dash(result.alpha_vs_spy)],
        [
            "Portfolio Sharpe",
            _ratio_or_dash(result.sharpe)
            + ("" if result.sharpe is not None else "  (no invested years)"),
        ],
        ["Opportunity set Sharpe", _ratio_or_dash(result.opportunity_set_sharpe)],
        ["SPY Sharpe", _ratio_or_dash(result.spy_sharpe)],
    ]
    print_section("Performance (equal-weighted, cash if no signals)")
    print_table([("Metric", 0), ("Value", 0)], rows)
    print(
        dim(
            "  Opportunity set = equal-weighted every priced ticker in the "
            "sample. SPY = SPDR S&P 500 ETF at fiscal-year ends."
        )
    )


def _render_no_buy(result) -> None:
    reason = result.no_buy_reason
    label = (
        "positive" if result.selected_verdict == "POSITIVE" else result.selected_verdict
    )
    print_section(f"Why no {label} signals")
    if reason["rules"]:
        print(f"  {bold('Rules (all must pass):')}")
        for rule in reason["rules"]:
            print(f"    • {rule['name']}")
    closest = reason["closest"]
    if closest:
        print(f"\n  {bold('Closest across evaluated ticker-years:')}")
        for index, record in enumerate(closest, 1):
            failed = ", ".join(_rule_label(rule) for rule in record["failed"]) or "—"
            print(
                f"    {index}. {record['ticker']} {record['year']}  "
                f"failed: {failed} "
                f"({record['n_failed']} of {len(reason['rules']) or '?'} rules)"
            )
    counts = reason["counts"]
    print(
        dim(
            f"  Ticker-years with <3 failed rules: {counts['lt3_failed']}; "
            f"<5 failed rules: {counts['lt5_failed']}."
        )
    )


def _render_methodology(result) -> None:
    universe_total = result.universe_total or result.sample_size
    name = result.universe_name.upper()
    complete = result.complete_years
    span = (
        f"{min(complete)}-{max(complete)} ({len(complete)}y CAGR)"
        if complete
        else "no complete years"
    )
    ytd = [str(item.year) for item in result.per_year if not item.complete]
    filter_label = (
        ""
        if result.selected_verdict in ("BUY", "POSITIVE")
        else f":{result.selected_verdict}"
    )
    header = (
        f"Backtest · {result.methodology}{filter_label}"
        + f" · {name} · sample {result.sample_size}/{universe_total} · {span} · "
        f"{result.evaluated} evaluated"
    )
    if ytd:
        header += f" · + {'/'.join(ytd)} YTD"
    print_header(header)

    if not result.buy_signals:
        label = (
            "positive"
            if result.selected_verdict == "POSITIVE"
            else result.selected_verdict
        )
        print(
            f"  {yellow(f'0 {label} set, nothing to compute')} "
            f"— every complete year is cash."
        )
        print()

    _render_year_verdicts(result)
    _render_performance(result)
    if not result.buy_signals:
        _render_no_buy(result)

    if result.skipped:
        print_section("Skipped tickers")
        for item in result.skipped:
            print(f"  • {item['ticker']}: {item['reason']}")

    print()
    for note in result.notes:
        print(dim(f"  {note}"))


def _run_methodology_backtest(args) -> None:
    from backend.services.methodology_backtest_service import (
        MethodologyBacktestService,
    )

    custom = bool(args.tickers)
    if custom:
        tickers = [t.upper() for t in args.tickers]
        universe_name = "custom"
        universe_total = len(tickers)
    else:
        tickers = _load_universe_subset(args.universe, args.limit)
        universe_name = args.universe
        universe_total = len(_universe_members(args.universe))
    if not tickers:
        print(f"  {yellow('No tickers to backtest.')}")
        return

    service = MethodologyBacktestService()
    results = []
    for raw in args.methodology:
        name, verdict_filter = parse_methodology_arg(raw)
        try:
            results.append(
                service.run(
                    tickers,
                    name,
                    years=args.years,
                    verdict_filter=verdict_filter,
                    weighting="equal"
                    if getattr(args, "equal_weight", False)
                    else "tier",
                    universe_name=universe_name,
                    universe_total=universe_total,
                )
            )
        except ValueError as exc:
            print(f"  {red('SKIPPED')} {raw}: {exc}")
    if not results:
        return

    if getattr(args, "json", False):
        payload = [result.to_dict() for result in results]
        print(
            json.dumps(
                payload[0] if len(payload) == 1 else payload,
                indent=2,
                default=str,
            )
        )
        return

    if len(results) == 1:
        _render_methodology(results[0])
        return

    # Several methodologies: one summary row each, no repeated year blocks.
    print_header(
        f"Backtest · {', '.join(r.methodology for r in results)} · "
        f"{universe_name.upper()} · sample {len(tickers)}/{universe_total}"
    )
    rows = [
        [
            result.methodology,
            str(len(result.complete_years)),
            str(result.buy_signals),
            _pct_or_dash(result.annualized_return),
            _pct_or_dash(result.opportunity_set_annualized),
            _pct_or_dash(result.spy_annualized),
            _pct_or_dash(result.hit_rate),
            _ratio_or_dash(result.sharpe),
        ]
        for result in results
    ]
    print_table(
        [
            ("Methodology", 0),
            ("Years", 1),
            ("Signals", 1),
            ("CAGR", 1),
            ("Opp set", 1),
            ("SPY", 1),
            ("Hit", 1),
            ("Sharpe", 1),
        ],
        rows,
    )
    print()
    for note in results[0].notes:
        print(dim(f"  {note}"))


def _run(args):
    if getattr(args, "methodology", None):
        _run_methodology_backtest(args)
        return
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
                prev = ticker_prices.get(year - 1) if year is not None else None
                current = ticker_prices.get(year)
                snapshot["prices"][ticker] = (prev, current)
    else:
        for snapshot in snapshots:
            for ticker in snapshot["analyses"]:
                snapshot["prices"][ticker] = (1.0, 1.0)

    print_header(
        f"Backtest {args.strategy}: {len(snapshots)} snapshots, "
        f"top-{args.top}, rebalancing every {args.rebalance} year(s)"
    )
    if not snapshots:
        print(
            f"  {yellow('Not enough history.')} Load {MIN_YEARS}+ years with "
            "'main.py load-data TICKER' before backtesting."
        )
        return

    result = run_backtest(
        snapshots,
        get_strategy(args.strategy),
        top_n=args.top,
        rebalance_every=args.rebalance,
    )

    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, default=str))
        return

    metrics = [
        (
            "CAGR (geometric mean)",
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
        ("Periods", str(result["periods"])),
    ]
    print_table([("Metric", 0), ("Value", 0)], metrics)

    print(f"\n  {bold('Selection in the first period:')}")
    if not result["selected_first_period"]:
        print(f"  {dim('no rankable candidates in the first period')}")
    for ticker in result["selected_first_period"]:
        analysis = snapshots[0]["analyses"].get(ticker)
        rank = analysis.get("rank_score") if analysis else None
        label = f"ranking {rank:.1f}" if rank is not None else "unranked"
        print(f"  - {green(ticker):<10} {label}")

    print()
    if not prices:
        print(dim("Without --prices: flat returns; it only measures selection."))
    print(green("Done."))
