"""Backtest the book methodologies over the last N fiscal years (PoC).

Usage::

    python -m scripts.backtest_methodologies --methodology graham --years 5
    python -m scripts.backtest_methodologies --all --years 10 --limit 50
    python -m scripts.backtest_methodologies --tickers AAPL,MSFT --all

The calculation is documented in ``docs/backtesting_design.md``. Results are
written to ``data/backtest/`` (git-ignored) and printed as a table. Prices are
fetched on demand and never persisted.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.methodology_backtest_service import (
    MethodologyBacktestService,
)

DEFAULT_UNIVERSE = PROJECT_ROOT / "config" / "universe.csv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data" / "backtest"
NAMED_UNIVERSES = {"sp500", "nasdaq100", "russell2000", "european", "all"}


def universe_members(spec: str) -> list[str]:
    """Every ticker in a named universe subset (before the PoC size cap)."""
    selected = spec.upper()
    include_all = spec.lower() not in NAMED_UNIVERSES or selected == "ALL"
    tickers: list[str] = []
    with DEFAULT_UNIVERSE.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            sources = {
                source.strip().upper()
                for source in (row.get("source_index") or "").split(",")
            }
            if include_all or selected in sources:
                ticker = (row.get("ticker") or "").strip().upper()
                if ticker:
                    tickers.append(ticker)
    return sorted(set(tickers))


def load_universe(spec: str, limit: int | None = None) -> list[str]:
    """Evenly spaced deterministic sample of a named universe."""
    return _spread(universe_members(spec), limit)


def _spread(tickers: list[str], limit: int | None) -> list[str]:
    """Evenly spaced deterministic sample (avoids the alphabetical bias)."""
    if not limit or limit >= len(tickers):
        return tickers
    step = len(tickers) / limit
    return [tickers[int(index * step)] for index in range(limit)]


def _format_pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def parse_methodology_arg(value: str) -> tuple[str, str | None]:
    """Parse ``'graham:BUY'`` into ``('graham', 'BUY')``."""
    if ":" in value:
        name, verdict = value.split(":", 1)
        return name.strip().lower(), verdict.strip().upper()
    return value.strip().lower(), None


def _print_table(results) -> None:
    header = (
        f"{'Methodology':<28} {'Years':>5} {'Signals':>7} {'CAGR':>8} "
        f"{'Opp set':>8} {'SPY':>8} {'Hit':>6} {'Sharpe':>7}"
    )
    print(header)
    print("-" * len(header))
    for result in results:
        print(
            f"{result.methodology:<28} {len(result.complete_years):>5} "
            f"{result.buy_signals:>7} {_format_pct(result.annualized_return):>8} "
            f"{_format_pct(result.opportunity_set_annualized):>8} "
            f"{_format_pct(result.spy_annualized):>8} "
            f"{_format_pct(result.hit_rate):>6} "
            f"{(result.sharpe if result.sharpe is not None else float('nan')):>7.2f}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--methodology",
        action="append",
        default=None,
        help="Methodology to backtest (repeatable). Omit with --all.",
    )
    parser.add_argument(
        "--all", action="store_true", help="Backtest every eligible methodology"
    )
    parser.add_argument(
        "--years", type=int, default=10, help="Fiscal years (default 10)"
    )
    parser.add_argument(
        "--universe",
        default="sp500",
        help="sp500|nasdaq100|russell2000|european|all (default sp500)",
    )
    parser.add_argument(
        "--limit", type=int, default=25, help="Max tickers (default 25 for the PoC)"
    )
    parser.add_argument("--tickers", default=None, help="Comma-separated tickers")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args(argv)

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        universe_name = "custom"
        universe_total = len(tickers)
    else:
        tickers = load_universe(args.universe, limit=args.limit)
        universe_name = args.universe
        universe_total = len(universe_members(args.universe))
    if not tickers:
        print("empty universe; nothing to backtest")
        return 1

    service = MethodologyBacktestService()
    raw_names = (
        service.available_methodologies() if args.all else (args.methodology or [])
    )
    if not raw_names:
        parser.error("pass --methodology NAME[:VERDICT] or --all")
    results = []
    for raw in raw_names:
        name, verdict_filter = parse_methodology_arg(raw)
        try:
            results.append(
                service.run(
                    tickers,
                    name,
                    years=args.years,
                    verdict_filter=verdict_filter,
                    universe_name=universe_name,
                    universe_total=universe_total,
                )
            )
        except ValueError as exc:
            print(f"skipped {raw}: {exc}")
    payload = {
        "generated": datetime.now(UTC).date().isoformat(),
        "universe": args.universe,
        "tickers": tickers,
        "years": args.years,
        "results": [result.to_dict() for result in results],
    }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"backtest_{payload['generated']}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        evaluated = results[0].evaluated if results else 0
        print(
            f"{universe_name.upper()} · sample {len(tickers)}/{universe_total} · "
            f"{args.years} years · {evaluated} evaluated"
        )
        _print_table(results)
        print(f"\n{path}")
        print(
            "PoC, not research-grade: no dividends, no survivorship correction, "
            "Greenblatt excluded (point-in-time ranking). YTD years excluded "
            "from CAGR."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
