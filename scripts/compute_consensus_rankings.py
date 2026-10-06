"""Compute the consensus verdict matrix over a universe.

Usage::

    python -m scripts.compute_consensus_rankings --universe sp500
    python -m scripts.compute_consensus_rankings --universe all --limit 50 --date 2026-10-06

For each ticker: fundamentals are read from Financial-DataBase (sequential
reads, never parallelized), the eight book methodologies are evaluated with a
bounded ThreadPoolExecutor (default 4 workers) and the verdicts are
aggregated into ``data/consensus/consensus_<date>.json``. Rerunning the same
date overwrites the file cleanly. See ``docs/consensus_screener.md``.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.cli import build_financial_repository
from backend.methodologies.registry import discover
from backend.services.consensus_service import CONSENSUS_VERSION
from backend.services.ui_adapter import parse_universe_tickers, run_methodologies

DEFAULT_UNIVERSE_PATH = Path("config/universe.csv")
DEFAULT_OUTPUT_DIR = Path("data/consensus")
MAX_YEARS = 10
MAX_WORKERS = 4

#: The eight registered methodologies, in the canonical JSON order.
METHODOLOGY_KEYS = (
    "buffett_classic",
    "buffett_clark",
    "fisher_quantitative_subset",
    "graham",
    "graham_dodd",
    "greenblatt",
    "lynch_garp",
    "marks",
)

UNIVERSE_SELECTIONS = {
    "sp500": ["SP500"],
    "nasdaq100": ["NASDAQ100"],
}


def read_universe(
    source: str, path: Path = DEFAULT_UNIVERSE_PATH
) -> tuple[list[str], dict[str, str]]:
    """``(tickers, names)`` for a named subset, ``all`` or a CSV path."""
    if source.lower() == "all":
        text, selections = path.read_text(encoding="utf-8"), []
    elif source.lower() in UNIVERSE_SELECTIONS:
        text = path.read_text(encoding="utf-8")
        selections = UNIVERSE_SELECTIONS[source.lower()]
    else:
        custom = Path(source)
        text, selections = custom.read_text(encoding="utf-8"), []
    tickers = parse_universe_tickers(text, selections)
    names: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(text)):
        ticker = (row.get("ticker") or "").strip().upper()
        if ticker:
            names[ticker] = (row.get("company_name") or ticker).strip()
    return tickers, names


def build_company_consensus(ticker: str, name: str, view: Any) -> dict[str, Any]:
    """Pure aggregation: a methodologies view -> one JSON company row."""
    verdicts: dict[str, str] = {}
    category = "UNKNOWN"
    for detail in view.details:
        methodology = str(detail.get("methodology") or "")
        if methodology in METHODOLOGY_KEYS:
            verdicts[methodology] = str(detail.get("verdict") or "INSUFFICIENT_DATA")
        if methodology == "lynch_garp" and detail.get("category"):
            category = str(detail["category"])
    for key in METHODOLOGY_KEYS:  # deterministic schema: always eight keys
        verdicts.setdefault(key, "INSUFFICIENT_DATA")
    buy_count = sum(1 for verdict in verdicts.values() if verdict == "BUY")
    avoid_count = sum(1 for verdict in verdicts.values() if verdict == "AVOID")
    insufficient_count = sum(
        1 for verdict in verdicts.values() if verdict == "INSUFFICIENT_DATA"
    )
    return {
        "name": name,
        "verdicts": verdicts,
        "buy_count": buy_count,
        "avoid_count": avoid_count,
        "insufficient_count": insufficient_count,
        "consensus_score": buy_count - avoid_count,
        "lynch_category": category,
    }


def _rank_key(row: dict[str, Any]) -> tuple:
    return (
        -row["buy_count"],
        -row["consensus_score"],
        row["avoid_count"],
        row["name"],
    )


def print_summary(companies: dict[str, dict[str, Any]], seconds: float) -> None:
    """Duration, buy_count distribution and the top 10 by consensus."""
    distribution: dict[int, int] = {}
    for row in companies.values():
        bucket = row["buy_count"]
        distribution[bucket] = distribution.get(bucket, 0) + 1
    print(f"\ncomputed {len(companies)} companies in {seconds:.1f}s")
    print("buy_count distribution:")
    for buys in range(len(METHODOLOGY_KEYS) + 1):
        print(f"  {buys} BUYs: {distribution.get(buys, 0)}")
    print("\ntop 10 by consensus score:")
    for ticker, row in sorted(companies.items(), key=lambda item: _rank_key(item[1]))[
        :10
    ]:
        flag = (
            " (all INSUFFICIENT)"
            if row["insufficient_count"] == len(METHODOLOGY_KEYS)
            else ""
        )
        print(
            f"  {ticker:6s} buys={row['buy_count']} avoids={row['avoid_count']} "
            f"score={row['consensus_score']:+d} category={row['lynch_category']}{flag}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--universe",
        default="sp500",
        help="sp500 | nasdaq100 | all | path to a universe CSV",
    )
    parser.add_argument("--universe-path", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument("--date", default=None, help="output date (default: today)")
    parser.add_argument("--limit", type=int, default=None, help="first N tickers")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--workers", type=int, default=MAX_WORKERS, help="evaluation workers (max 4)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_date = args.date or datetime.now(UTC).date().isoformat()
    workers = max(1, min(args.workers, MAX_WORKERS))

    tickers, names = read_universe(args.universe, args.universe_path)
    if args.limit is not None:
        tickers = tickers[: max(args.limit, 0)]
    print(f"universe={args.universe} tickers={len(tickers)} date={output_date}")

    repository = build_financial_repository()
    discover()

    start = time.time()
    rows_by_ticker: dict[str, list] = {}
    for index, ticker in enumerate(tickers, 1):
        try:
            rows = [
                row
                for row in repository.get_best_available(ticker, max_years=MAX_YEARS)
                if row is not None
            ]
        except Exception:  # noqa: BLE001 — one bad read must not stop the run
            rows = []
        if rows:
            rows_by_ticker[ticker] = rows
        if index % 25 == 0 or index == len(tickers):
            print(f"  read {index}/{len(tickers)} tickers")

    companies: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(run_methodologies, ticker, rows, None, None): ticker
            for ticker, rows in rows_by_ticker.items()
        }
        for done, future in enumerate(as_completed(futures), 1):
            ticker = futures[future]
            view = future.result()
            companies[ticker] = build_company_consensus(
                ticker, names.get(ticker, ticker), view
            )
            if done % 25 == 0 or done == len(futures):
                print(f"  evaluated {done}/{len(futures)} tickers")

    payload = {
        "version": CONSENSUS_VERSION,
        "date": output_date,
        "universe": args.universe,
        "companies": {ticker: companies[ticker] for ticker in sorted(companies)},
    }
    output = args.output_dir / f"consensus_{output_date}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output}")
    print_summary(companies, time.time() - start)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
