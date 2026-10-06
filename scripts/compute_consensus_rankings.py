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
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.cli import build_financial_repository
from backend.methodologies.registry import discover
from backend.services.consensus_service import CONSENSUS_VERSION
from backend.services.price_service import _snapshot_price, get_price_service
from backend.services.ui_adapter import parse_universe_tickers, run_methodologies

logger = logging.getLogger(__name__)

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


def prefetch_prices(
    service: Any, tickers: list[str]
) -> tuple[dict[str, float], dict[str, float], bool]:
    """Batch price/market-cap snapshot for the universe (never persisted).

    Returns ``(prices, market_caps, available)``. The Yahoo preflight is
    probed first: when Yahoo is down the whole prefetch is skipped instead of
    hammering every ticker. Snapshot failures degrade to the existing
    per-ticker batch fetch; if that also fails the run continues without
    prices and the JSON records ``prices_available: false``.
    """
    probe = getattr(service, "yahoo_available", None)
    if callable(probe):
        try:
            health = probe(force=True)
        except Exception:  # noqa: BLE001 — a broken probe never fails the run
            health = None
        if health is not None and not getattr(health, "available", True):
            logger.warning(
                "Yahoo preflight unavailable (%s): skipping the price prefetch; "
                "consensus verdicts degrade to the no-price path",
                getattr(health, "reason", "unknown"),
            )
            return {}, {}, False

    snapshots: dict = {}
    fetch_snapshots = getattr(service, "get_market_snapshots", None)
    if callable(fetch_snapshots):
        try:
            snapshots = (
                fetch_snapshots(
                    tickers, batch_size=20, delay=0.1, workers=6, preflight=True
                )
                or {}
            )
        except Exception:
            logger.warning("market snapshot prefetch failed", exc_info=True)
            snapshots = {}

    prices: dict[str, float] = {}
    market_caps: dict[str, float] = {}
    for ticker, snapshot in snapshots.items():
        if not isinstance(snapshot, dict):
            continue
        price = _snapshot_price(snapshot)
        if price is None:
            continue
        key = str(ticker).upper()
        prices[key] = float(price)
        cap = snapshot.get("marketCap")
        if cap is not None:
            try:
                market_caps[key] = float(cap)
            except (TypeError, ValueError):
                pass

    if not prices:
        fetch_current = getattr(service, "get_current_prices", None)
        if callable(fetch_current):
            try:
                raw = fetch_current(tickers, batch_size=25, delay=0.5) or {}
            except Exception:  # noqa: BLE001 — no prices is a valid outcome
                raw = {}
            prices = {
                str(ticker).upper(): float(price)
                for ticker, price in raw.items()
                if price is not None
            }

    logger.info(
        "price prefetch: %d/%d prices, %d market caps",
        len(prices),
        len(tickers),
        len(market_caps),
    )
    return prices, market_caps, bool(prices)


def build_company_consensus(
    ticker: str,
    name: str,
    view: Any,
    *,
    price: float | None = None,
    prices_available: bool = False,
) -> dict[str, Any]:
    """Pure aggregation: a methodologies view -> one JSON company row."""
    verdicts: dict[str, str] = {}
    category = "UNKNOWN"
    for detail in view.details:
        methodology = str(detail.get("methodology") or "")
        if methodology in METHODOLOGY_KEYS:
            verdicts[methodology] = str(detail.get("verdict") or "INSUFFICIENT_DATA")
        if methodology == "lynch_garp":
            # Prefer the canonical enum key (metrics["lynch_category"]); the
            # detail's ``category`` is the human label fallback.
            metrics = detail.get("metrics") or {}
            category = str(
                metrics.get("lynch_category") or detail.get("category") or "UNKNOWN"
            )
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
        "price": price,
        "prices_available": prices_available,
    }


def write_report(output_dir: Path, output_date: str, payload: dict) -> Path:
    """Write (idempotently) ``consensus_<date>.json`` and return its path."""
    output = output_dir / f"consensus_{output_date}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output


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
    categorized = sum(
        1
        for row in companies.values()
        if row["lynch_category"] not in ("UNKNOWN", "Unclassified")
    )
    if companies:
        print(
            f"\nLynch category populated: {categorized}/{len(companies)} "
            f"({categorized / len(companies) * 100:.0f}%)"
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
    price_service = get_price_service()
    configure = getattr(price_service, "configure", None)
    if callable(configure):
        from backend.services.yahoo_health import check_yahoo_availability

        configure(health_fn=check_yahoo_availability)
    prices, market_caps, prices_available = prefetch_prices(price_service, tickers)
    if prices_available:
        print(
            f"prices: {len(prices)}/{len(tickers)} fetched "
            f"({len(market_caps)} market caps)"
        )
    else:
        print("prices: unavailable — evaluating without prices")

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
            pool.submit(
                run_methodologies,
                ticker,
                rows,
                prices.get(ticker),
                market_caps.get(ticker),
            ): ticker
            for ticker, rows in rows_by_ticker.items()
        }
        for done, future in enumerate(as_completed(futures), 1):
            ticker = futures[future]
            view = future.result()
            companies[ticker] = build_company_consensus(
                ticker,
                names.get(ticker, ticker),
                view,
                price=prices.get(ticker),
                prices_available=ticker in prices,
            )
            if done % 25 == 0 or done == len(futures):
                print(f"  evaluated {done}/{len(futures)} tickers")

    payload = {
        "version": CONSENSUS_VERSION,
        "date": output_date,
        "universe": args.universe,
        "prices_available": prices_available,
        "prices_snapshot": {ticker: prices[ticker] for ticker in sorted(prices)},
        "companies": {ticker: companies[ticker] for ticker in sorted(companies)},
    }
    output = write_report(args.output_dir, output_date, payload)
    print(f"wrote {output}")
    print_summary(companies, time.time() - start)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
