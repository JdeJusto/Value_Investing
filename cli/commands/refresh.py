"""`refresh` — refresh facts and/or on-demand prices for one ticker."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

from backend.services.ticker_refresh_service import refresh_ticker
from cli import theme


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "refresh",
        help="Refresh SEC facts and/or on-demand prices for one ticker",
        description=(
            "Targeted single-company refresh: SEC facts via the existing "
            "RefreshService and the current Yahoo price on demand. Prices are "
            "never persisted to Financial-DataBase."
        ),
    )
    parser.add_argument("ticker", help="Ticker (e.g. AAPL)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--facts-only",
        action="store_true",
        help="Only refresh SEC facts",
    )
    group.add_argument(
        "--prices-only",
        action="store_true",
        help="Only fetch the current Yahoo price (not persisted)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Machine-readable result",
    )
    parser.set_defaults(func=_run)


def _exit_code(result, facts: bool, prices: bool) -> int:
    if facts and prices:
        if result.facts_synced and result.prices_synced:
            return 0
        if result.facts_synced or result.prices_synced:
            return 1
        return 2
    ok = result.facts_synced if facts else result.prices_synced
    return 0 if ok else 2


def run(args) -> int:
    if getattr(args, "facts_only", False) and getattr(args, "prices_only", False):
        print(
            "error: use at most one of --facts-only / --prices-only",
            file=sys.stderr,
        )
        return 2

    facts = not getattr(args, "prices_only", False)
    prices = not getattr(args, "facts_only", False)
    ticker = str(args.ticker).strip().upper()

    if not getattr(args, "json", False):
        theme.print_header(f"Refresh · {ticker}")
        domains = " ".join(
            name for name, enabled in (("facts", facts), ("prices", prices)) if enabled
        )
        print(f"Refreshing {domains}...")

    result = refresh_ticker(ticker, facts=facts, prices=prices)

    if getattr(args, "json", False):
        print(json.dumps(asdict(result), indent=2))
    else:
        if facts:
            detail = f" — {result.facts_error}" if result.facts_error else ""
            print(f"Facts:  {'OK' if result.facts_synced else 'FAIL'}{detail}")
        if prices:
            detail = f" — {result.prices_error}" if result.prices_error else ""
            print(f"Prices: {'OK' if result.prices_synced else 'FAIL'}{detail}")
        print(f"Duration: {result.duration_seconds:.2f}s")
        if prices:
            print(
                theme.dim(
                    "Prices are fetched from Yahoo on-demand; not persisted to FDB."
                )
            )

    return _exit_code(result, facts, prices)


def _run(args) -> None:
    raise SystemExit(run(args))
