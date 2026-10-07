import argparse
import os
import sys
import time

import pandas as pd

from backend.app.cli import (
    add_demo_argument,
    add_refresh_arguments,
    build_screener_service,
    refresh_analysis_inputs,
)
from backend.config.settings import get_output_dir
from backend.domain.value_objects.filter_criteria import FilterCriteria
from backend.services import cli_output
from cli.formatters import (
    bold,
    dim,
    fmt_dollar,
    fmt_pct,
    fmt_ratio,
    green,
    print_header,
    print_table,
    red,
    yellow,
)

_PCT_FIELDS = {"roe", "roic", "fcf_yield", "op_margin", "net_margin", "revenue_growth"}


def _pct(value: float | None) -> float | None:
    if value is None:
        return None
    if value >= 1:
        return value / 100.0
    return value


def _build_filters(args) -> list[FilterCriteria]:
    filters: list[FilterCriteria] = []

    simple_filters = {
        "pe_max": ("per", "lt", False),
        "pe_min": ("per", "gt", False),
        "pb_max": ("pb", "lt", False),
        "pb_min": ("pb", "gt", False),
        "debt_to_equity_max": ("debt_to_equity", "lt", False),
        "fcf_min": ("fcf", "gt", False),
        "market_cap_min": ("market_cap", "gt", False),
        "roe_min": ("roe", "gt", True),
        "roic_min": ("roic", "gt", True),
        "fcf_yield_min": ("fcf_yield", "gt", True),
        "op_margin_min": ("op_margin", "gt", True),
        "net_margin_min": ("net_margin", "gt", True),
        "ev_ebit_max": ("ev_ebit", "lt", False),
    }

    for attr, (field, op, is_pct) in simple_filters.items():
        val = getattr(args, attr, None)
        if val is not None:
            v = _pct(val) if is_pct else val
            if op == "lt":
                filters.append(FilterCriteria.lt(field, v))
            else:
                filters.append(FilterCriteria.gt(field, v))

    for raw in getattr(args, "filter", []) or []:
        try:
            parts = raw.split()
            field = parts[0]
            operator = parts[1]
            if operator == "between":
                low, high = float(parts[2]), float(parts[3])
                filters.append(FilterCriteria.between(field, low, high))
            elif operator == "<":
                filters.append(FilterCriteria.lt(field, float(parts[2])))
            elif operator == ">":
                filters.append(FilterCriteria.gt(field, float(parts[2])))
            elif operator == "==":
                filters.append(FilterCriteria.eq(field, parts[2]))
            elif operator == "<=":
                from backend.domain.value_objects.filter_criteria import FilterOperator

                filters.append(
                    FilterCriteria(
                        field=field, operator=FilterOperator.LTE, value=float(parts[2])
                    )
                )
            elif operator == ">=":
                from backend.domain.value_objects.filter_criteria import FilterOperator

                filters.append(
                    FilterCriteria(
                        field=field, operator=FilterOperator.GTE, value=float(parts[2])
                    )
                )
        except (IndexError, ValueError) as e:
            print(f"  {red('ERROR:')} Invalid filter: '{raw}' — {e}")
            sys.exit(1)

    if (
        args.pb_min is not None
        and args.pb_max is not None
        and args.pb_min > args.pb_max
    ):
        print(
            f"  {red('ERROR:')} pb-min ({args.pb_min}) cannot be greater "
            f"than pb-max ({args.pb_max})"
        )
        sys.exit(1)

    if (
        args.pe_min is not None
        and args.pe_max is not None
        and args.pe_min > args.pe_max
    ):
        print(
            f"  {red('ERROR:')} pe-min ({args.pe_min}) cannot be greater "
            f"than pe-max ({args.pe_max})"
        )
        sys.exit(1)

    return filters


def _show_search_results(service, query: str):
    print_header(f"Search: '{query}'")
    print("  Searching tickers...", end=" ")
    sys.stdout.flush()
    try:
        matches = service.search(query)
    except Exception as e:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
        print(f"\n  {red('ERROR:')} {e}")
        return

    print(f"{len(matches)} results\n")

    if not matches:
        print("  No results found.")
        return

    headers = [("Ticker", 0), ("Company", 0)]
    rows = []
    for t in matches:
        try:
            name = service._market.get_company_name(t)
        except Exception:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
            name = None
        rows.append([t, name or dim("N/A")])

    print_table(headers, rows)


_PRICE_BASED_FILTERS = {
    "per",
    "pb",
    "fcf_yield",
    "ev_ebit",
    "market_cap",
}


def _run_screener(args):
    service = build_screener_service()
    filters = _build_filters(args)

    tickers = None
    universe = getattr(args, "universe", None)
    if universe and universe.lower() != "demo":
        print(red(f"Unknown universe: {universe} (use 'demo' or --tickers)"))
        return
    if (universe and universe.lower() == "demo") or (
        getattr(args, "demo", False) and not args.tickers and not args.search
    ):
        # The offline bundle doubles as a named universe; a bare --demo
        # screen defaults to it instead of the configured universe.
        from backend.services.demo_mode import load_demo_prices

        tickers = sorted(load_demo_prices())
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]

    if args.search:
        print(f"  Searching '{args.search}'... ", end="")
        sys.stdout.flush()
        try:
            matches = service.search(args.search)
        except Exception as e:  # noqa: BLE001 — boundary catch-all (external libs/network raise many types)
            print(f"\n  {red('ERROR:')} {e}")
            return
        print(f"{len(matches)} results")
        if not matches:
            return
        tickers = matches

    if tickers is None:
        from backend.app.cli import load_universe

        universe = load_universe()
        if universe:
            tickers = universe

    if tickers:
        explicit = bool(args.tickers) or bool(args.search)
        refresh_analysis_inputs(
            tickers, args, fetch_prices=not args.no_prices, explicit=explicit
        )

    price_filters = [f for f in filters if f.field in _PRICE_BASED_FILTERS]
    if args.no_prices and price_filters:
        print(
            f"  {yellow('WARNING:')} --no-prices with valuation filters "
            f"({', '.join(f.field for f in price_filters)}). "
            "Without a real price, these companies will be discarded."
        )

    total_tickers = len(tickers) if tickers else "~150"
    filter_desc = ", ".join(str(f) for f in filters) if filters else "(no filters)"
    mode = "without real prices" if args.no_prices else "real-time prices"
    print(f"  Tickers: {total_tickers}  |  Filters: {filter_desc}  |  {mode}")
    print()

    start = time.time()

    with cli_output.progress(0, "Screening") as batch:

        def progress(current, total, ticker):
            """Rich bar on a terminal; silent when output is redirected."""
            batch.set_total(total)
            batch.set_description(f"Screening {ticker}")
            batch.update(current)

        results = service.screen(
            tickers=tickers,
            filters=filters,
            top_n=args.top,
            progress_callback=progress,
            no_prices=args.no_prices,
        )
    elapsed = time.time() - start

    print(f"\n\n  {green(str(len(results)))} results in {elapsed:.1f}s")

    if not results:
        print(f"\n  {yellow('No company passes the filters.')}")
        return

    headers = [
        ("Ticker", 0),
        ("Company", 0),
        ("Price", 1),
        ("PER", 1),
        ("P/B", 1),
        ("ROE", 1),
        ("ROIC", 1),
        ("FCF", 1),
        ("FCF Yield", 1),
        ("D/E", 1),
        ("Score", 1),
    ]

    rows = []
    for r in results:
        name_trunc = (r.name or "")[:20]
        price_s = fmt_dollar(r.price) if r.price else dim("N/A")
        per_s = fmt_ratio(r.per, 1) if r.per else dim("N/A")
        pb_s = fmt_ratio(r.pb, 2) if r.pb else dim("N/A")
        roe_s = fmt_pct(r.roe) if r.roe else dim("N/A")
        roic_s = fmt_pct(r.roic) if r.roic else dim("N/A")
        fcf_s = fmt_dollar(r.fcf) if r.fcf else dim("N/A")
        fcf_yield_s = fmt_pct(r.fcf_yield) if r.fcf_yield else dim("N/A")
        de_s = fmt_ratio(r.debt_to_equity, 2) if r.debt_to_equity else dim("N/A")
        score_s = f"{r.score:.4f}" if r.score else dim("N/A")

        if r.score and r.score > 0.7:
            score_s = green(score_s)
        elif r.score and r.score < 0.3:
            score_s = red(score_s)

        if r.per and r.per < 15:
            per_s = green(per_s)
        elif r.per and r.per > 30:
            per_s = red(per_s)

        rows.append(
            [
                r.ticker,
                name_trunc,
                price_s,
                per_s,
                pb_s,
                roe_s,
                roic_s,
                fcf_s,
                fcf_yield_s,
                de_s,
                score_s,
            ]
        )

    print_table(headers, rows)

    if args.save:
        path = os.path.join(get_output_dir(), "screener_resultados.csv")
        os.makedirs(get_output_dir(), exist_ok=True)
        pd.DataFrame(
            [
                {
                    "ticker": r.ticker,
                    "name": r.name,
                    "price": r.price,
                    "per": r.per,
                    "pb": r.pb,
                    "roe": r.roe,
                    "roic": r.roic,
                    "op_margin": r.operating_margin,
                    "net_margin": r.net_margin,
                    "fcf_yield": r.fcf_yield,
                    "ev_ebit": r.ev_ebit,
                    "debt_to_equity": r.debt_to_equity,
                    "fcf": r.fcf,
                    "score": r.score,
                }
                for r in results
            ]
        ).to_csv(path, index=False)
        print(f"  Results saved to {green(path)}")


def register(subparsers):
    p = subparsers.add_parser(
        "screener",
        help="Stock screener with fundamental filters",
        description=(
            "Finds companies that meet fundamental criteria. Two engines: "
            "market data (Yahoo/EDGAR) or the Buffett quality engine "
            "(use --filter in the format moat=STRONG min_score=80)."
        ),
        formatter_class=lambda prog: type(
            "HelpFormatter",
            (argparse.RawDescriptionHelpFormatter,),
            {"max_help_position": 36},
        )(prog),
    )
    p.add_argument(
        "--tickers", type=str, help="Comma-separated tickers (e.g.: AAPL,MSFT,GOOGL)"
    )
    p.add_argument(
        "--universe",
        type=str,
        help="Named universe: 'demo' uses the 8 tickers from the offline bundle",
    )
    p.add_argument("--search", type=str, help="Search by ticker or company name")
    p.add_argument(
        "--pe-max",
        "--per-max",
        dest="pe_max",
        type=float,
        metavar="N",
        help="Maximum PER (e.g.: 15)",
    )
    p.add_argument(
        "--pe-min",
        "--per-min",
        dest="pe_min",
        type=float,
        metavar="N",
        help="Minimum PER",
    )
    p.add_argument(
        "--ev-ebit-max", type=float, metavar="N", help="Maximum EV/EBIT (e.g.: 20)"
    )
    p.add_argument("--pb-max", type=float, metavar="N", help="Maximum P/B (e.g.: 1.5)")
    p.add_argument("--pb-min", type=float, metavar="N", help="Minimum P/B (e.g.: 1.0)")
    p.add_argument(
        "--no-prices",
        action="store_true",
        help="Do not fetch real-time prices (P/E, FCF yield and EV/EBIT may remain N/A)",
    )
    p.add_argument(
        "--roe-min", type=float, metavar="N", help="Minimum ROE in %% (e.g.: 15)"
    )
    p.add_argument(
        "--roic-min", type=float, metavar="N", help="Minimum ROIC in %% (e.g.: 10)"
    )
    p.add_argument(
        "--fcf-min", type=float, metavar="N", help="Minimum FCF in USD (e.g.: 1000000)"
    )
    p.add_argument(
        "--fcf-yield-min",
        type=float,
        metavar="N",
        help="Minimum FCF yield in %% (e.g.: 5)",
    )
    p.add_argument(
        "--market-cap-min", type=float, metavar="N", help="Minimum Market Cap in USD"
    )
    p.add_argument("--debt-to-equity-max", type=float, metavar="N", help="Maximum D/E")
    p.add_argument(
        "--op-margin-min",
        type=float,
        metavar="N",
        help="Minimum operating margin in %%",
    )
    p.add_argument(
        "--net-margin-min", type=float, metavar="N", help="Minimum net margin in %%"
    )
    p.add_argument(
        "--top",
        type=int,
        default=30,
        metavar="N",
        help="Max results (default: 30)",
    )
    p.add_argument(
        "--filter",
        action="append",
        default=[],
        metavar="'field < value'|'key=value'",
        help=(
            'Raw filter: "per < 15" (market engine) or "moat=STRONG", '
            '"min_score=80", "min_roic=0.12" (Buffett quality engine)'
        ),
    )
    p.add_argument("--save", action="store_true", help="Save results to CSV")
    add_refresh_arguments(p)
    add_demo_argument(p)
    p.set_defaults(func=_run)


def _parse_investment_filters(raw_filters: list[str]) -> dict:
    """Parse 'key=value' filters (e.g. moat=STRONG, min_score=80)."""
    criteria: dict = {}
    numeric_keys = {
        "min_market_cap",
        "max_market_cap",
        "min_revenue_growth",
        "min_roic",
        "max_debt_ratio",
        "min_buffett_score",
        "min_moat_score",
        "min_total_score",
        "min_margin_of_safety",
        "min_score",
        "max_debt",
    }
    for raw in raw_filters:
        if "=" not in raw:
            print(
                f"  {red('ERROR:')} '{raw}' is not a Buffett quality filter. "
                "Raw and equality filters cannot be mixed; use one engine or the other."
            )
            sys.exit(1)
        key, _, value = raw.partition("=")
        key = key.strip()
        value = value.strip()
        if key not in numeric_keys and key not in {
            "moat",
            "sector",
            "industry",
            "confidence",
        }:
            print(f"  {red('ERROR:')} Unknown filter '{key}'.")
            sys.exit(1)
        try:
            criteria[key] = float(value) if key in numeric_keys else value
        except ValueError:
            print(f"  {red('ERROR:')} Invalid value for '{key}': '{value}'")
            sys.exit(1)
    return criteria


def _run_investment_screener(args) -> None:
    from backend.app.cli import build_investment_screener, load_universe

    criteria = _parse_investment_filters(args.filter)
    universe = None
    if args.tickers:
        universe = [t.strip().upper() for t in args.tickers.split(",")]
    elif not args.search:
        universe = load_universe()

    if universe:
        refresh_analysis_inputs(
            universe,
            args,
            fetch_prices=not args.no_prices,
            explicit=bool(args.tickers),
        )

    mode = "" if args.no_prices else " (+ real-time prices)"
    print(f"  Engine: Buffett quality{mode}  |  Filters: {criteria or '(no filters)'}")
    if args.no_prices:
        print(f"  {yellow('WARNING:')} --no-prices: no real-time P/E or FCF yield.")
    print()

    service = build_investment_screener(universe, no_prices=args.no_prices)
    with cli_output.status("Screening with the Buffett engine..."):
        results = service.top_n(args.top, **criteria)
    print(f"\n  {green(str(len(results)))} results")

    if not results:
        print(f"\n  {yellow('No company passes the filters.')}")
        return

    headers = [
        ("Rank", 0),
        ("Ticker", 0),
        ("Score", 1),
        ("Ranking", 1),
        ("Moat", 0),
        ("Rating", 0),
        ("Price", 1),
        ("PER", 1),
        ("FCF Yield", 1),
        ("EV/EBIT", 1),
        ("Signal", 0),
    ]
    rows = []
    for r in results:
        metrics = r.metrics or {}
        price = metrics.get("price")
        per = metrics.get("per")
        fcf_yield = metrics.get("fcf_yield")
        ev_ebit = metrics.get("ev_ebit")
        rows.append(
            [
                str(r.rank),
                r.ticker,
                f"{r.total_score:.1f}",
                f"{r.rank_score:.1f}" if r.rank_score else dim("N/A"),
                r.moat,
                r.rating,
                fmt_dollar(price) if price is not None else dim("N/A"),
                fmt_ratio(per, 1) if per is not None else dim("N/A"),
                fmt_pct(fcf_yield) if fcf_yield is not None else dim("N/A"),
                fmt_ratio(ev_ebit, 1) if ev_ebit is not None else dim("N/A"),
                r.signal,
            ]
        )
    print_table(headers, rows)

    print(f"\n  {bold('Why?')}")
    for r in results[:10]:
        reasons = r.reasons[:3]
        print(f"  {green(str(r.rank)):>3}. {bold(r.ticker)} — {'; '.join(reasons)}")


def _run(args):
    uses_buffett = any("=" in f for f in args.filter)
    if uses_buffett:
        market_flags = [
            args.pe_max,
            args.pe_min,
            args.ev_ebit_max,
            args.pb_max,
            args.pb_min,
            args.roe_min,
            args.roic_min,
            args.fcf_yield_min,
            args.market_cap_min,
            args.debt_to_equity_max,
            args.op_margin_min,
            args.net_margin_min,
        ]
        if any(v is not None for v in market_flags):
            print(
                f"  {red('ERROR:')} Equality filters "
                "(--filter moat=STRONG) cannot be mixed with numeric "
                "filters (--pe-max, --roe-min, ...). Use only one engine."
            )
            sys.exit(1)
        _run_investment_screener(args)
    elif args.search:
        service = build_screener_service()
        _show_search_results(service, args.search)
    else:
        _run_screener(args)
