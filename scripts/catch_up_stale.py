"""Targeted SEC catch-up for companies outside the analyzed universe.

The daily workflow only refreshes companies whose ticker is in the universe
file, so names that never made it into ``config/universe.csv`` (Russell 2000
companies, OTC/foreign listings, delisted issuers) keep going stale forever
even though the SEC data for them is one targeted ``sec sync <CIK>`` away.

This tool does exactly that and nothing else:

- it **selects** stale companies with one read-only query (see
  :meth:`backend.services.refresh_service.FdbGateway.stale_companies`),
  bounded by ``--limit`` and ordered by ``--priority``;
- it **syncs each one individually** through the Financial-DataBase CLI
  (``sec sync <CIK>``). There is no database-wide path here by design: a
  blanket ``update-all`` / ``update-incremental`` would hammer the SEC with
  thousands of requests and is never what this tool does;
- it runs the **SEC availability preflight** first (same module the daily
  workflow uses) and refuses to start when the SEC is answering 403/429;
- it honours ``--refresh-workers`` (default 2, the conservative value) and
  writes a per-company log line with its duration.

It is a manual tool. It is not part of the daily workflow and the systemd
timer never calls it.

Examples
--------
Plan only, no network::

    python -m scripts.catch_up_stale --limit 20 --dry-run

Sync the 20 companies whose newest filing is most recent::

    python -m scripts.catch_up_stale --limit 20 --priority recent_filings

Anchored to the 7-day staleness the daily workflow uses (the default
``--limit`` is 100, about 10 minutes at the measured 6 s per company)::

    python -m scripts.catch_up_stale --freshness-hours 168
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Allow `python -m scripts.catch_up_stale` from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.refresh_service import (  # noqa: E402
    FdbGateway,
    RefreshService,
    load_refresh_config,
)
from backend.services.sec_health import check_sec_availability  # noqa: E402

logger = logging.getLogger("catch_up_stale")

DEFAULT_LIMIT = 100
DEFAULT_WORKERS = 2
PRIORITIES = ("recent_filings", "alphabetical", "random")


def default_fdb_dir() -> str:
    """The sibling Financial-DataBase checkout, next to this repository.

    Derived from this file's location rather than hardcoded, so a clone
    anywhere works. Falls back to ~/Financial-DataBase.
    """
    repo_root = Path(__file__).resolve().parent.parent
    for candidate in (
        repo_root.parent / "Financial-DataBase",
        Path.home() / "Financial-DataBase",
    ):
        if candidate.is_dir():
            return str(candidate)
    return str(repo_root.parent / "Financial-DataBase")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.catch_up_stale",
        description=(
            "Targeted SEC catch-up for stale companies outside the analyzed "
            "universe. Syncs one CIK at a time; never a database-wide sweep."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=(
            f"maximum companies to sync in this run (default {DEFAULT_LIMIT}, "
            f"≈{DEFAULT_LIMIT * 6 // 60} min at the measured 6 s per company; "
            "raise it deliberately for a long catch-up campaign)"
        ),
    )
    parser.add_argument(
        "--priority",
        choices=PRIORITIES,
        default="recent_filings",
        help=(
            "selection order: recent_filings (newest filing first, default), "
            "alphabetical, random"
        ),
    )
    parser.add_argument(
        "--freshness-hours",
        type=int,
        default=168,
        help="staleness threshold in hours (default 168 = 7 days)",
    )
    parser.add_argument(
        "--refresh-workers",
        type=int,
        default=None,
        help="concurrent targeted syncs (default: config/refresh.yaml, 2)",
    )
    parser.add_argument(
        "--fdb-dir",
        default=default_fdb_dir(),
        help=(
            "Financial-DataBase checkout (used for its .venv python); "
            "defaults to the sibling directory next to this repository"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list what would be synced and exit without any network call",
    )
    parser.add_argument(
        "--show",
        type=int,
        default=20,
        help="how many rows to print (default 20; 0 prints all)",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s:%(name)s:%(message)s",
    )

    gateway = FdbGateway()
    if not gateway.available():
        print(
            "ERROR: Financial-DataBase is unreachable. Set "
            "FINANCIAL_DATABASE_URL to a reachable database.",
            file=sys.stderr,
        )
        return 2

    if args.limit <= 0:
        print("ERROR: --limit must be positive (a catch-up is always bounded).",
              file=sys.stderr)
        return 2

    config = load_refresh_config()
    if args.refresh_workers:
        config.refresh_workers = max(1, int(args.refresh_workers))
    workers = max(1, int(config.refresh_workers or DEFAULT_WORKERS))

    candidates = gateway.stale_companies(
        max_age_hours=args.freshness_hours,
        limit=args.limit,
        priority=args.priority,
    )

    print(
        f"stale companies (>{args.freshness_hours}h, active listing): "
        f"{len(candidates)} selected, priority={args.priority}, "
        f"max {args.limit}, workers {workers}"
    )
    if not candidates:
        print("nothing to do: no stale company matches the threshold.")
        return 0

    shown = candidates if args.show == 0 else candidates[: args.show]
    print(f"{'company_id':38} {'cik':>10}  {'filings':>7}  {'last sync':22} name")
    for row in shown:
        last_sync = str(row.get("last_synced_at") or "never")
        print(
            f"{row['company_id']:38} {row['cik']:>10}  "
            f"{int(row.get('filing_count') or 0):>7}  {last_sync:22} "
            f"{(row.get('legal_name') or '')[:40]}"
        )
    if len(candidates) > len(shown):
        print(f"... and {len(candidates) - len(shown)} more")

    if args.dry_run:
        print("\nDRY-RUN: no SEC request was made.")
        return 0

    # SEC preflight: refuse to launch a burst of doomed syncs.
    health = check_sec_availability()
    if not health.available:
        print(f"ERROR: SEC preflight failed: {health.reason}", file=sys.stderr)
        print("Nothing was synced. Fix SEC_USER_AGENT / wait, then retry.",
              file=sys.stderr)
        return 3

    if not os.environ.get("SEC_USER_AGENT", "").strip():
        print("ERROR: SEC_USER_AGENT is not set (see .env.example).",
              file=sys.stderr)
        return 2

    service = RefreshService(
        config=config,
        fdb_repo_path=str(Path(args.fdb_dir).resolve()),
    )

    print(f"\nsyncing {len(candidates)} companies, {workers} worker(s)…")
    started = time.time()
    done: list[str] = []
    failed: list[tuple[str, str]] = []

    def _one(row: dict) -> tuple[str, str, object]:
        t0 = time.time()
        return row["legal_name"], row["cik"], (service.sync_one(row["cik"]), time.time() - t0)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_one, row): row for row in candidates}
        for future in as_completed(futures):
            row = futures[future]
            name, cik, payload = future.result()
            status, elapsed = payload
            if status is True:
                done.append(name)
                print(f"  ok    {cik:>10}  {elapsed:6.1f}s  {name[:50]}")
            else:
                failed.append((cik, str(status)))
                print(f"  FAIL  {cik:>10}  {elapsed:6.1f}s  {name[:40]} — {status}")

    total = time.time() - started
    print(
        f"\ndone: {len(done)} synced, {len(failed)} failed in {total:.0f}s "
        f"({total / max(1, len(candidates)):.1f}s per company)"
    )
    if failed:
        print("failures:")
        for cik, reason in failed:
            print(f"  {cik}: {reason}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
