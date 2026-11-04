"""Backfill the legacy JSON financial store from Financial-DataBase.

The JSON store (``data/normalized/<TICKER>.json``) is only a fallback for when
Financial-DataBase is unreachable, but most of its files were last written by a
pipeline that stored null financial fields. This script replaces each ticker's
file with the best consistent history read from FDB, so the fallback is usable
instead of showing empty companies.

Usage:
    python -m scripts.backfill_json_store --universe sp500
    python -m scripts.backfill_json_store --tickers AAPL,MSFT --dry-run
"""

from __future__ import annotations

import argparse
import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("backfill_json_store")

DEFAULT_UNIVERSE = Path("config/universe.csv")
DEFAULT_OUT = Path("data/normalized")


@dataclass
class BackfillReport:
    written: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"written={len(self.written)} missing={len(self.missing)} "
            f"failed={len(self.failed)}"
        )


def load_tickers(path: Path, limit: int | None = None) -> list[str]:
    """Ticker column from the master-universe CSV: deduped, order preserved."""
    tickers: list[str] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            ticker = (row.get("ticker") or "").strip().upper()
            if ticker and ticker not in seen:
                seen.add(ticker)
                tickers.append(ticker)
    return tickers[:limit] if limit else tickers


def backfill(
    tickers: list[str],
    fdb_repo,
    json_repo,
    *,
    dry_run: bool = False,
    progress_every: int = 100,
) -> BackfillReport:
    """Replace each ticker's JSON history with the FDB best-available rows."""
    report = BackfillReport()
    for index, ticker in enumerate(tickers, 1):
        try:
            rows = fdb_repo.get_best_available(ticker)
        except Exception as exc:  # noqa: BLE001 — one ticker must not stop the run
            logger.error("%s: FDB read failed: %s", ticker, exc)
            report.failed[ticker] = str(exc)
            continue
        if not rows:
            report.missing.append(ticker)
        elif dry_run:
            report.written.append(ticker)
        else:
            json_repo.replace_ticker(ticker, rows)
            report.written.append(ticker)
        if progress_every and index % progress_every == 0:
            logger.info("progress %d/%d — %s", index, len(tickers), report.summary())
    return report


def _resolve_tickers(args) -> list[str]:
    if args.tickers:
        values = [part.strip().upper() for part in args.tickers.split(",")]
        return [value for value in dict.fromkeys(values) if value]
    return load_tickers(Path(args.universe), args.limit)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE))
    parser.add_argument("--tickers", default=None, help="Comma-separated tickers")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    from backend.repositories.financial_database_repository import (
        FinancialDatabaseRepository,
    )
    from backend.repositories.json_financial_repository import JsonFinancialRepository

    tickers = _resolve_tickers(args)
    if not tickers:
        logger.error("no tickers to backfill")
        return 2
    fdb_repo = FinancialDatabaseRepository()
    if not fdb_repo.available():
        logger.error("Financial-DataBase is not available")
        return 2

    json_repo = JsonFinancialRepository(args.out)
    report = backfill(tickers, fdb_repo, json_repo, dry_run=args.dry_run)
    logger.info("done — %s", report.summary())
    for ticker, reason in report.failed.items():
        logger.warning("failed %s: %s", ticker, reason)
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
