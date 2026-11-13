"""CLI: backtest a strategy against historical yearly snapshots."""

import csv
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path

from backend.app.cli import build_financial_repository, build_universe
from backend.backtesting import get_strategy, run_backtest, sort_snapshots
from backend.intelligence.scoring_model import assess_investment
from backend.methodologies.base import is_positive
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
            "Rebuilds historical analyses from the repo and simulates a "
            "portfolio with rebalancing every N years. Use --prices "
            "TICKER,YEAR,PRICE per line for real returns, or --research-grade "
            "for point-in-time fundamentals, historical membership and costs."
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
        default=None,
        help=(
            "Max tickers for --methodology (PoC default 25; research mode "
            "uses the full historical universe unless set)"
        ),
    )
    p.add_argument("--years", type=int, default=10, help="Use the last N fiscal years")
    p.add_argument(
        "--top", type=int, default=5, help="Number of holdings per portfolio"
    )
    p.add_argument(
        "--rebalance",
        default="1",
        help=(
            "Strategy mode: rebalance every N years (default 1). Research "
            "mode: annual|quarterly|threshold (default annual)."
        ),
    )
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
        "--research-grade",
        action="store_true",
        help=(
            "Point-in-time fundamentals (FDB filing_date), historical S&P 500 "
            "membership, transaction costs, sizing cap and price snapshot. "
            "Requires Financial-DataBase 0.4.0+."
        ),
    )
    p.add_argument(
        "--legacy",
        action="store_true",
        help="Force the pre-0.34.0 PoC behaviour even if --research-grade is set.",
    )
    p.add_argument(
        "--pit-lag-days",
        type=int,
        default=45,
        help="Reporting lag after the calendar year end (default 45 days).",
    )
    p.add_argument(
        "--tc-bps",
        type=float,
        default=10.0,
        help="Transaction cost in basis points of one-way turnover (default 10).",
    )
    p.add_argument(
        "--tc-fixed",
        type=float,
        default=0.0,
        help="Fixed commission per changed name, in dollars (default 0).",
    )
    p.add_argument(
        "--initial-capital",
        type=float,
        default=100_000.0,
        help="Capital used to express fixed commissions as a return (default 100000).",
    )
    p.add_argument(
        "--rebalance-threshold",
        type=float,
        default=0.05,
        help="Drift threshold for --rebalance threshold (default 0.05).",
    )
    p.add_argument(
        "--sizing",
        choices=("tier", "equal"),
        default="tier",
        help="Research mode position sizing (default tier, capped by --max-weight).",
    )
    p.add_argument(
        "--max-weight",
        type=float,
        default=0.20,
        help="Per-name weight cap in research mode (default 0.20).",
    )
    p.add_argument(
        "--price-snapshot",
        default=None,
        help="Replay a saved research-grade price snapshot (JSON).",
    )
    p.add_argument(
        "--save-snapshot",
        nargs="?",
        const="",
        default=None,
        help=(
            "Save the prices used by a research-grade run. Optional path; "
            "default data/backtest_snapshots/<methodology>_<timestamp>.json."
        ),
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
            "  N/A: banks/insurers (not applicable). REITs are scored and "
            "flagged [REIT]. INSUFF: missing fundamentals "
            "for that year."
        )
    )


def _load_price_snapshot(path: str) -> dict[str, dict[str, float]]:
    """Load a research-grade snapshot: ``{ticker: {iso_date: price}}``."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    prices = payload.get("prices", payload) if isinstance(payload, dict) else {}
    return {
        str(ticker).upper(): {
            str(when): float(price) for when, price in (series or {}).items()
        }
        for ticker, series in prices.items()
    }


def _save_price_snapshot(result, path: str) -> Path:
    """Persist the prices used by a research-grade run for exact replay."""
    if not path:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = f"data/backtest_snapshots/{result.methodology}_{stamp}.json"
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "methodology": result.methodology,
        "config": result.to_dict()["config"],
        "prices": result.snapshot_out,
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


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
    if result.research_grade:
        complete = [item for item in result.per_year if item.complete]
        turnovers = [item.turnover for item in complete if item.turnover is not None]
        costs = [item.cost for item in complete if item.cost is not None]
        rows.append(
            [
                "Avg turnover",
                f"{statistics.fmean(turnovers):.1%}" if turnovers else dim("—"),
            ]
        )
        rows.append(
            [
                "Cost drag (sum)",
                f"{sum(costs):.2%}" if costs else dim("—"),
            ]
        )
    title = (
        "Performance (research-grade, costs applied)"
        if result.research_grade
        else "Performance (equal-weighted, cash if no signals)"
    )
    print_section(title)
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

    if result.research_grade:
        fixed = f" + ${result.tc_fixed:g}/trade" if result.tc_fixed else ""
        print(
            dim(
                f"  PIT: as-of = Dec-31+{result.pit_lag_days}d · "
                f"Sizing: {result.sizing} (cap {result.max_weight:.0%}) · "
                f"Rebalance: {result.rebalance} · TC: {result.tc_bps:g} bps{fixed}"
            )
        )
        coverage = (
            f"{result.pit_coverage:.0%}" if result.pit_coverage is not None else "n/a"
        )
        print(
            dim(
                f"  Universe: historical S&P 500 · PIT coverage {coverage} · "
                "Survivorship: not corrected"
            )
        )

    _render_year_verdicts(result)
    _render_performance(result)
    reit_signals = sum(
        1
        for record in result.records
        if "reit" in record.flags and is_positive(record.verdict)
    )
    if reit_signals:
        print(dim(f"  [REIT] signals included: {reit_signals}"))
    mixed_signals = sum(
        1 for record in result.records if "mixed_currency" in record.flags
    )
    if mixed_signals:
        print(dim(f"  [MIXED-CURRENCY] signals included: {mixed_signals}"))
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

    research = bool(getattr(args, "research_grade", False)) and not bool(
        getattr(args, "legacy", False)
    )
    if research and str(getattr(args, "universe", "sp500")).lower() not in {
        "sp500",
        "all",
    }:
        raise SystemExit(
            "error: --research-grade currently supports only --universe sp500"
        )
    custom = bool(getattr(args, "tickers", None))
    if custom:
        tickers = [t.upper() for t in getattr(args, "tickers", None) or []]
        universe_name = "custom"
        universe_total = len(tickers)
    elif research:
        # The service reads the historical membership per year.
        tickers = []
        universe_name = args.universe
        universe_total = None
    else:
        limit = getattr(args, "limit", None)
        limit = limit if limit is not None else 25
        tickers = _load_universe_subset(args.universe, limit)
        universe_name = args.universe
        universe_total = len(_universe_members(args.universe))
    if not tickers and not research:
        print(f"  {yellow('No tickers to backtest.')}")
        return

    sizing = getattr(args, "sizing", "tier")
    if getattr(args, "equal_weight", False):
        sizing = "equal"
    rebalance = str(getattr(args, "rebalance", "annual"))
    if research and (rebalance.isdigit() or rebalance == ""):
        rebalance = "annual"
    snapshot_path = getattr(args, "price_snapshot", None)
    snapshot = _load_price_snapshot(snapshot_path) if snapshot_path else None
    service = MethodologyBacktestService()
    results = []
    for raw in args.methodology:
        name, verdict_filter = parse_methodology_arg(raw)
        try:
            result = service.run(
                tickers,
                name,
                years=getattr(args, "years", 10),
                verdict_filter=verdict_filter,
                weighting="equal" if getattr(args, "equal_weight", False) else "tier",
                universe_name=universe_name,
                universe_total=universe_total,
                research_grade=research,
                pit_lag_days=getattr(args, "pit_lag_days", 45),
                tc_bps=getattr(args, "tc_bps", 10.0),
                tc_fixed=getattr(args, "tc_fixed", 0.0),
                initial_capital=getattr(args, "initial_capital", 100_000.0),
                rebalance=rebalance if research else "annual",
                rebalance_threshold=getattr(args, "rebalance_threshold", 0.05),
                sizing=sizing,
                max_weight=getattr(args, "max_weight", 0.20),
                price_snapshot=snapshot,
                use_historical_universe=not custom,
                universe_limit=(getattr(args, "limit", None) if not custom else None),
            )
            results.append(result)
            save_snapshot = getattr(args, "save_snapshot", None)
            if research and save_snapshot is not None:
                saved = _save_price_snapshot(result, save_snapshot)
                if not getattr(args, "json", False):
                    print(dim(f"  Price snapshot saved: {saved}"))
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
    try:
        rebalance_every = int(args.rebalance)
    except (TypeError, ValueError):
        raise SystemExit(
            "error: --rebalance must be an integer in strategy mode"
        ) from None
    if rebalance_every < 1:
        raise SystemExit("error: --rebalance must be >= 1 in strategy mode")
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
        rebalance_every=rebalance_every,
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
