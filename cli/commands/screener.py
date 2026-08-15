import argparse
import os
import sys
import time
from typing import Optional

import pandas as pd

from backend.app.cli import build_screener_service
from backend.config.settings import get_output_dir
from backend.domain.value_objects.filter_criteria import FilterCriteria
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


def _pct(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if value >= 1:
        return value / 100.0
    return value


def _build_filters(args) -> list[FilterCriteria]:
    filters: list[FilterCriteria] = []

    simple_filters = {
        "per_max": ("per", "lt", False),
        "per_min": ("per", "gt", False),
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
            print(f"  {red('ERROR:')} Filtro invalido: '{raw}' — {e}")
            sys.exit(1)

    if (
        args.pb_min is not None
        and args.pb_max is not None
        and args.pb_min > args.pb_max
    ):
        print(
            f"  {red('ERROR:')} pb-min ({args.pb_min}) no puede ser mayor "
            f"que pb-max ({args.pb_max})"
        )
        sys.exit(1)

    return filters


def _show_search_results(service, query: str):
    print_header(f"Busqueda: '{query}'")
    print("  Buscando tickers...", end=" ")
    sys.stdout.flush()
    try:
        matches = service.search(query)
    except Exception as e:
        print(f"\n  {red('ERROR:')} {e}")
        return

    print(f"{len(matches)} resultados\n")

    if not matches:
        print("  No se encontraron resultados.")
        return

    headers = [("Ticker", 0), ("Empresa", 0)]
    rows = []
    for t in matches:
        try:
            name = service._market.get_company_name(t)
        except Exception:
            name = None
        rows.append([t, name or dim("N/A")])

    print_table(headers, rows)


def _run_screener(args):
    service = build_screener_service()
    filters = _build_filters(args)

    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]

    if args.search:
        print(f"  Buscando '{args.search}'... ", end="")
        sys.stdout.flush()
        try:
            matches = service.search(args.search)
        except Exception as e:
            print(f"\n  {red('ERROR:')} {e}")
            return
        print(f"{len(matches)} resultados")
        if not matches:
            return
        tickers = matches

    total_tickers = len(tickers) if tickers else "~150"
    filter_desc = ", ".join(str(f) for f in filters) if filters else "(sin filtros)"
    print(f"  Tickers: {total_tickers}  |  Filtros: {filter_desc}")
    print()

    start = time.time()

    def progress(current, total, ticker):
        pct = int(current / total * 100)
        bar = "#" * (pct // 5) + dim("·" * (20 - pct // 5))
        sys.stdout.write(f"\r    [{bar}] {current}/{total} ({pct:>2d}%) {ticker:<8}")
        sys.stdout.flush()

    results = service.screen(
        tickers=tickers,
        filters=filters,
        top_n=args.top,
        progress_callback=progress,
    )
    elapsed = time.time() - start

    print(f"\n\n  {green(str(len(results)))} resultados en {elapsed:.1f}s")

    if not results:
        print(f"\n  {yellow('Ninguna empresa cumple los filtros.')}")
        return

    headers = [
        ("Ticker", 0),
        ("Empresa", 0),
        ("Precio", 1),
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
        print(f"  Resultados guardados en {green(path)}")


def register(subparsers):
    p = subparsers.add_parser(
        "screener",
        help="Stock screener con filtros fundamentales",
        description=(
            "Busca empresas que cumplan criterios fundamentales. Dos motores: "
            "datos de mercado (Yahoo/EDGAR) o el motor de calidad Buffett "
            "(usa --filter en formato moat=STRONG min_score=80)."
        ),
        formatter_class=lambda prog: type(
            "HelpFormatter",
            (argparse.RawDescriptionHelpFormatter,),
            {"max_help_position": 36},
        )(prog),
    )
    p.add_argument(
        "--tickers", type=str, help="Tickers separados por coma (ej: AAPL,MSFT,GOOGL)"
    )
    p.add_argument("--search", type=str, help="Buscar por ticker o nombre de empresa")
    p.add_argument("--per-max", type=float, metavar="N", help="PER maximo (ej: 15)")
    p.add_argument("--per-min", type=float, metavar="N", help="PER minimo")
    p.add_argument("--pb-max", type=float, metavar="N", help="P/B maximo (ej: 1.5)")
    p.add_argument("--pb-min", type=float, metavar="N", help="P/B minimo (ej: 1.0)")
    p.add_argument(
        "--roe-min", type=float, metavar="N", help="ROE minimo en %% (ej: 15)"
    )
    p.add_argument(
        "--roic-min", type=float, metavar="N", help="ROIC minimo en %% (ej: 10)"
    )
    p.add_argument(
        "--fcf-min", type=float, metavar="N", help="FCF minimo en USD (ej: 1000000)"
    )
    p.add_argument(
        "--fcf-yield-min",
        type=float,
        metavar="N",
        help="FCF Yield minimo en %% (ej: 5)",
    )
    p.add_argument(
        "--market-cap-min", type=float, metavar="N", help="Market Cap minimo en USD"
    )
    p.add_argument("--debt-to-equity-max", type=float, metavar="N", help="D/E maximo")
    p.add_argument(
        "--op-margin-min", type=float, metavar="N", help="Margen operativo minimo en %%"
    )
    p.add_argument(
        "--net-margin-min", type=float, metavar="N", help="Margen neto minimo en %%"
    )
    p.add_argument(
        "--top",
        type=int,
        default=30,
        metavar="N",
        help="Maximo de resultados (default: 30)",
    )
    p.add_argument(
        "--filter",
        action="append",
        default=[],
        metavar="'campo < valor'|'clave=valor'",
        help=(
            'Filtro raw: "per < 15" (motor mercado) o "moat=STRONG", '
            '"min_score=80", "min_roic=0.12" (motor calidad Buffett)'
        ),
    )
    p.add_argument("--save", action="store_true", help="Guardar resultados en CSV")
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
                f"  {red('ERROR:')} '{raw}' no es un filtro de calidad Buffett. "
                "No se pueden mezclar filtros raw y de igualdad; usa uno u otro motor."
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
            print(f"  {red('ERROR:')} Filtro desconocido '{key}'.")
            sys.exit(1)
        try:
            criteria[key] = float(value) if key in numeric_keys else value
        except ValueError:
            print(f"  {red('ERROR:')} Valor invalido para '{key}': '{value}'")
            sys.exit(1)
    return criteria


def _run_investment_screener(args) -> None:
    from backend.app.cli import build_investment_screener

    criteria = _parse_investment_filters(args.filter)
    universe = None
    if args.tickers:
        universe = [t.strip().upper() for t in args.tickers.split(",")]

    print(f"  Motor: calidad Buffett  |  Filtros: {criteria or '(sin filtros)'}")
    print()

    service = build_investment_screener(universe)
    results = service.top_n(args.top, **criteria)
    print(f"\n  {green(str(len(results)))} resultados")

    if not results:
        print(f"\n  {yellow('Ninguna empresa cumple los filtros.')}")
        return

    headers = [
        ("Rank", 0),
        ("Ticker", 0),
        ("Score", 1),
        ("Ranking", 1),
        ("Moat", 0),
        ("Rating", 0),
        ("Senal", 0),
        ("Oportunidad", 0),
    ]
    rows = []
    for r in results:
        rows.append(
            [
                r.rank,
                r.ticker,
                f"{r.total_score:.1f}",
                f"{r.rank_score:.1f}" if r.rank_score else dim("N/A"),
                r.moat,
                r.rating,
                r.signal,
                r.opportunity_type if r.opportunity_type else dim("-"),
            ]
        )
    print_table(headers, rows)

    print(f"\n  {bold('Por que?')}")
    for r in results[:10]:
        reasons = r.reasons[:3]
        print(f"  {green(str(r.rank)):>3}. {bold(r.ticker)} — {'; '.join(reasons)}")


def _run(args):
    uses_buffett = any("=" in f for f in args.filter)
    if uses_buffett:
        market_flags = [
            args.per_max,
            args.per_min,
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
                f"  {red('ERROR:')} No se pueden mezclar filtros de igualdad "
                "(--filter moat=STRONG) con los filtros numericos "
                "(--per-max, --roe-min, ...). Usa solo un motor."
            )
            sys.exit(1)
        _run_investment_screener(args)
    elif args.search:
        service = build_screener_service()
        _show_search_results(service, args.search)
    else:
        _run_screener(args)
