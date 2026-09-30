"""Compute Greenblatt Magic Formula rankings for a universe (weekly job).

- **ROC** = ``EBIT / (max(current assets - current liabilities, 0) + net PPE)``
- **EY**  = ``EBIT / (market cap + total debt - cash)``

Companies are ranked independently by ROC and EY (1 = best); the combined
rank is the sum and the percentile is ``combined_rank / (2 * N)`` (lower is
better). The methodology reads the newest
``data/rankings/greenblatt_*.json``.

Usage::

    python -m scripts.compute_greenblatt_rankings --universe sp500
    python -m scripts.compute_greenblatt_rankings --universe all
    python -m scripts.compute_greenblatt_rankings --universe my_universe.csv

Idempotent: re-running the same day overwrites the same file with the same
bytes (the payload has no wall-clock timestamp).
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

from backend.analytics.ratios.greenblatt import earnings_yield, return_on_capital
from backend.app.cli import build_financial_repository
from backend.services.price_service import get_price_service

RANKINGS_DIR = PROJECT_ROOT / "data" / "rankings"
UNIVERSE_PATH = PROJECT_ROOT / "config" / "universe.csv"
NAMED_UNIVERSES = {"sp500", "nasdaq100", "russell2000", "european", "all"}


def load_universe(spec: str) -> list[str]:
    """Tickers from the master universe (named subset) or a custom CSV."""
    path = UNIVERSE_PATH if spec.lower() in NAMED_UNIVERSES else Path(spec)
    selected = spec.upper()
    # A custom CSV is taken whole; a named subset filters by source_index.
    include_all = spec.lower() not in NAMED_UNIVERSES or selected == "ALL"
    tickers: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            sources = {
                source.strip().upper()
                for source in (row.get("source_index") or "").split(",")
            }
            if include_all or selected in sources:
                ticker = (row.get("ticker") or "").strip().upper()
                if ticker:
                    tickers.add(ticker)
    return sorted(tickers)


def compute_rankings(tickers: list[str], repository, price_service) -> dict:
    """ROC/EY metrics plus ranks; rows missing either metric are excluded."""
    snapshots = price_service.get_market_snapshots(tickers)
    metrics: dict[str, dict] = {}
    for ticker in tickers:
        rows = [row for row in repository.get_best_available(ticker) if row is not None]
        if not rows:
            continue
        latest = rows[0]
        snapshot = snapshots.get(ticker) or {}
        roc = return_on_capital(latest)
        ey = earnings_yield(latest, snapshot.get("marketCap"))
        if roc is None or ey is None or roc <= 0 or ey <= 0:
            continue
        metrics[ticker] = {"roc": roc, "ey": ey, "fiscal_year": latest.fiscal_year}

    ranked_roc = sorted(metrics, key=lambda t: metrics[t]["roc"], reverse=True)
    ranked_ey = sorted(metrics, key=lambda t: metrics[t]["ey"], reverse=True)
    rank_roc = {ticker: index + 1 for index, ticker in enumerate(ranked_roc)}
    rank_ey = {ticker: index + 1 for index, ticker in enumerate(ranked_ey)}
    total = len(metrics)
    rankings = {}
    for ticker in sorted(metrics):
        combined = rank_roc[ticker] + rank_ey[ticker]
        rankings[ticker] = {
            "rank_roc": rank_roc[ticker],
            "rank_ey": rank_ey[ticker],
            "combined_rank": combined,
            "percentile": combined / (2.0 * total) if total else None,
            "roc": round(metrics[ticker]["roc"], 6),
            "earnings_yield": round(metrics[ticker]["ey"], 6),
            "fiscal_year": metrics[ticker]["fiscal_year"],
        }
    return {
        "date": datetime.now(UTC).date().isoformat(),
        "universe_size": total,
        "rankings": rankings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--universe",
        default="sp500",
        help="sp500|nasdaq100|russell2000|european|all or a custom CSV path",
    )
    parser.add_argument("--output-dir", default=str(RANKINGS_DIR))
    args = parser.parse_args(argv)

    tickers = load_universe(args.universe)
    print(f"universe: {len(tickers)} tickers ({args.universe})")
    if not tickers:
        print("empty universe; nothing to rank")
        return 1

    payload = compute_rankings(
        tickers, build_financial_repository(), get_price_service()
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"greenblatt_{payload['date']}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"ranked {payload['universe_size']} companies -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
