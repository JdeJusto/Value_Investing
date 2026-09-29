#!/usr/bin/env python3
"""Merge the per-index universe CSVs into the master ``config/universe.csv``.

Inputs (run the fetch scripts first):

  config/universe_sp500_nasdaq.csv  — scripts/fetch_universe.py
  config/universe_russell2000.csv   — scripts/fetch_russell2000.py
  config/universe_european.csv      — scripts/fetch_european_indices.py

Merge rules:

- Include S&P 500 + Nasdaq-100 (as fetched), ALL Russell 2000, and only
  European companies with ``has_sec_filings=true`` (SEC EDGAR filers).
- Deduplicate by ticker (case-insensitive) and by CIK; a company listed in
  several indices keeps a comma-separated ``source_index``.
- Drop rows without a CIK: no CIK ⇔ no EDGAR fundamentals available, so the
  ticker cannot be analyzed by this project.

Output columns match the historical format:
``ticker,cik,company_name,source_index``.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.universe_common import EUROPEAN_INDEXES

# Canonical source_index ordering (unknown tokens appended alphabetically).
_CANON = ["SP500", "NASDAQ100", "Russell2000"] + sorted(EUROPEAN_INDEXES)


def _sort_sources(sources: set[str]) -> list[str]:
    return [c for c in _CANON if c in sources] + sorted(sources - set(_CANON))


def _read_universe_csv(
    path: str, european_sec_only: bool = False
) -> list[dict]:
    """Rows from a per-index universe CSV as normalized dicts."""
    rows: list[dict] = []
    with open(path, encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            if not raw.get("ticker") or not raw.get("ticker").strip():
                continue
            if not raw.get("cik"):
                continue  # never analyzable downstream
            if european_sec_only and raw.get("has_sec_filings", "").strip().lower() != "true":
                continue
            sources = {
                s.strip()
                for s in raw.get("source_index", "").split(",")
                if s.strip()
            }
            if "BOTH" in sources:
                sources = (sources - {"BOTH"}) | {"SP500", "NASDAQ100"}
            rows.append(
                {
                    "ticker": raw["ticker"].strip().upper(),
                    "cik": raw["cik"].strip(),
                    "name": (raw.get("company_name") or "").strip(),
                    "sources": sources,
                }
            )
    return rows


def merge_sources(source_chunks: list[list[dict]]) -> list[dict]:
    """Order-preserving merge; dedupes by ticker then by CIK."""
    by_ticker: dict[str, dict] = {}
    order: list[str] = []
    for chunk in source_chunks:
        for row in chunk:
            tick = row["ticker"]
            if not tick or not row["cik"]:
                continue
            if tick in by_ticker:
                by_ticker[tick]["sources"] |= row["sources"]
                by_ticker[tick]["name"] = (
                    by_ticker[tick]["name"] or row["name"]
                )
                continue
            by_ticker[tick] = {
                "ticker": tick,
                "cik": row["cik"],
                "name": row["name"],
                "sources": set(row["sources"]),
            }
            order.append(tick)

    # CIK duplicates (share classes / alternate symbols): merge sources into
    # the first occurrence and drop the later row.
    first_cik: dict[str, str] = {}
    merged: list[dict] = []
    for tick in order:
        row = by_ticker[tick]
        cik = row["cik"].lstrip("0") or "0"
        if cik in first_cik and first_cik[cik] != tick:
            by_ticker[first_cik[cik]]["sources"] |= row["sources"]
            continue
        first_cik.setdefault(cik, tick)
        merged.append(row)
    return merged


def build_universe(
    output: str = "config/universe.csv",
    sp500_file: str = "config/universe_sp500_nasdaq.csv",
    russell_file: str = "config/universe_russell2000.csv",
    european_file: str = "config/universe_european.csv",
) -> dict:
    """Merge all per-index CSVs into the master file. Returns stats."""
    missing = [p for p in (sp500_file, russell_file, european_file)
               if not Path(p).exists()]
    if missing:
        raise SystemExit(
            "ERROR: missing universe source files: "
            + ", ".join(missing)
            + ". Run scripts/fetch_universe.py, scripts/fetch_russell2000.py "
            "and scripts/fetch_european_indices.py first."
        )

    sp500_rows = _read_universe_csv(sp500_file)
    russell_rows = _read_universe_csv(russell_file)
    european_rows = _read_universe_csv(european_file, european_sec_only=True)

    merged = merge_sources([sp500_rows, russell_rows, european_rows])

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ticker", "cik", "company_name", "source_index"],
        )
        writer.writeheader()
        for row in merged:
            writer.writerow(
                {
                    "ticker": row["ticker"],
                    "cik": row["cik"],
                    "company_name": row["name"],
                    "source_index": ",".join(_sort_sources(row["sources"])),
                }
            )

    per_source: dict[str, int] = {}
    for row in merged:
        for token in row["sources"]:
            per_source[token] = per_source.get(token, 0) + 1

    return {
        "total": len(merged),
        "per_source": per_source,
        "sp500_nasdaq_input": len(sp500_rows),
        "russell_input": len(russell_rows),
        "european_with_sec_input": len(european_rows),
        "output": str(path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="build_universe.py")
    parser.add_argument(
        "--output",
        default="config/universe.csv",
        help="Master universe path (default: config/universe.csv)",
    )
    parser.add_argument(
        "--sp500-file",
        default="config/universe_sp500_nasdaq.csv",
    )
    parser.add_argument(
        "--russell-file",
        default="config/universe_russell2000.csv",
    )
    parser.add_argument(
        "--european-file",
        default="config/universe_european.csv",
    )
    args = parser.parse_args()

    stats = build_universe(
        args.output,
        sp500_file=args.sp500_file,
        russell_file=args.russell_file,
        european_file=args.european_file,
    )
    print(f"Master universe written: {stats['output']}")
    print(f"  total tickers (after dedup): {stats['total']}")
    print("  per source index:")
    for source, count in sorted(stats["per_source"].items()):
        print(f"    {source}: {count}")
    print(
        f"  inputs: SP500+NASDAQ100 {stats['sp500_nasdaq_input']} · "
        f"Russell2000 {stats['russell_input']} · "
        f"European w/ SEC {stats['european_with_sec_input']}"
    )


if __name__ == "__main__":
    main()