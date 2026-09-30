#!/usr/bin/env python3
"""Cross-check the master universe against Financial-DataBase.

For every ticker in ``config/universe.csv`` this resolves the CIK through
Financial-DataBase's ``company_identifiers`` table and reports coverage:

- how many tickers resolve (they are analyzable — SEC fundamentals exist),
- how many do not (listed with their CIK from the universe file, capped
  output), and the overall coverage percentage.

The daily workflow must not be pointed at a universe whose coverage drops
below ``--threshold`` (default 80%) without a human review: those tickers
would screen with no fundamentals.

Models the gate used by CI: exit code 0 when coverage >= threshold,
1 otherwise.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_rows(universe_path: str) -> list[dict]:
    with open(universe_path, encoding="utf-8") as handle:
        return [
            {
                "ticker": r["ticker"].strip().upper(),
                "cik": (r.get("cik") or "").strip(),
                "source_index": (r.get("source_index") or "").strip(),
            }
            for r in csv.DictReader(handle)
            if r.get("ticker") and r["ticker"].strip()
        ]


def validate_universe(
    universe_path: str = "config/universe.csv",
    repo=None,
    threshold: float = 80.0,
    max_unresolved: int = 100,
) -> bool:
    """Return True when FDB coverage is at/above ``threshold``."""
    from scripts.universe_common import EUROPEAN_INDEXES

    rows = load_rows(universe_path)
    if not rows:
        raise SystemExit(f"ERROR: no rows in universe file {universe_path}")

    european = set(EUROPEAN_INDEXES) | {"European"}
    if repo is None:
        from backend.repositories.financial_database_repository import (
            FinancialDatabaseRepository,
        )

        repo = FinancialDatabaseRepository()

    resolved: list[dict] = []
    unresolved: list[dict] = []
    for row in rows:
        cik = None
        try:
            cik = repo.get_cik(row["ticker"])
        except Exception:  # noqa: BLE001 — never fail the whole check
            cik = None
        (resolved if cik else unresolved).append(row)

    total = len(rows)
    coverage = len(resolved) / total * 100.0

    print(f"Universe: {universe_path}")
    print(f"  total tickers    : {total}")
    print(f"  resolved in FDB  : {len(resolved)}")
    print(f"  unresolved       : {len(unresolved)}")
    print(f"  coverage         : {coverage:.1f}% (threshold {threshold:.0f}%)")

    print("\n  per source index (a row can appear in several buckets):")
    resolved_tickers = {r["ticker"] for r in resolved}
    buckets: dict[str, list] = {}
    for row in rows:
        toks = {
            ("European" if t in european else t) for t in _sources(row["source_index"])
        }
        for s in toks:
            buckets.setdefault(s, []).append(row)
    for source, group in sorted(buckets.items()):
        n_resolved = sum(1 for r in group if r["ticker"] in resolved_tickers)
        print(f"    {source}: {len(group)} total, {n_resolved} resolved")

    if unresolved:
        print(f"\n  unresolved tickers (capped at {max_unresolved}):")
        for row in unresolved[:max_unresolved]:
            print(
                f"    {row['ticker']:8s} cik={row['cik'] or '(none)':12s} "
                f"source={row['source_index']}"
            )
        if len(unresolved) > max_unresolved:
            print(f"    … and {len(unresolved) - max_unresolved} more")

    ok = coverage >= threshold
    print(f"\nResult: {'PASS' if ok else 'FAIL'} — {coverage:.1f}% >= {threshold:.0f}%")
    return ok


def _sources(source_index: str) -> set[str]:
    return {s.strip() for s in source_index.split(",") if s.strip()}


def main() -> None:
    parser = argparse.ArgumentParser(prog="validate_universe_against_fdb.py")
    parser.add_argument(
        "--universe",
        default="config/universe.csv",
        help="Master universe CSV (default: config/universe.csv)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=80.0,
        help="Minimum FDB coverage in percent (default: 80)",
    )
    parser.add_argument(
        "--max-unresolved",
        type=int,
        default=100,
        help="How many unresolved tickers to print (default: 100)",
    )
    args = parser.parse_args()

    ok = validate_universe(
        args.universe,
        threshold=args.threshold,
        max_unresolved=args.max_unresolved,
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
