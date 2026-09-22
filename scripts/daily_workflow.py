#!/usr/bin/env python3
"""Daily fundamentals + valuation workflow.

1. (optional) Targeted SEC refresh in Financial-DataBase — only the analyzed
   tickers are checked for staleness and only the stale ones are synced
   (per-CIK `sec sync`); the full universe is never synced wholesale.
2. Screen a configurable universe (default config/universe.csv) with
   real-time prices (fetched in batches ONLY for the analyzed tickers,
   never persisted).
3. Evaluate alerts (BUY_SIGNAL / SELL_WARNING / TRIGGER_EVENT) against the
   previous day's state.
4. Write data/reports/daily_YYYY-MM-DD.md and persist the new state.

Flags:
  --dry-run         estimate staleness (read-only, no sync) and print the
                    report without writing any file
  --no-update       skip the SEC refresh but still screen + write report/state
  --limit N         analyze only the first N tickers of the universe
  --refresh         force a targeted SEC refresh of the analyzed tickers
  --no-refresh      skip the targeted SEC refresh entirely
  --freshness-hours override the freshness threshold (default: 168)
"""

import argparse
import csv
import logging
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("daily_workflow")


def _load_universe(path: str) -> list[str]:
    """Tickers from a CSV (ticker,cik,company_name,source_index) universe file.

    A plain text file (one ticker per line, '#' comments) is still accepted
    for backward compatibility.
    """
    with open(path, encoding="utf-8") as handle:
        first = handle.readline().strip()
    if first and "," in first:
        with open(path, encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames and "ticker" in reader.fieldnames:
                tickers = [
                    row["ticker"].strip().upper()
                    for row in reader
                    if row.get("ticker", "").strip()
                ]
                if tickers:
                    return tickers
    with open(path, encoding="utf-8") as handle:
        tickers = [
            line.strip().upper()
            for line in handle
            if line.strip() and not line.lstrip().startswith("#")
        ]
    if not tickers:
        raise SystemExit(f"ERROR: no tickers in universe file '{path}'")
    return tickers


def _run_targeted_refresh(universe: list[str], args) -> str:
    """Targeted per-CIK SEC refresh of ONLY the analyzed tickers.

    Replaces the old blanket ``sec update-incremental`` (which scanned the
    whole ~8k-company Financial-DataBase): the on-demand refresh service
    resolves each analyzed ticker's CIK and syncs just the stale companies
    of this universe, degrading gracefully per company. In dry-run mode it
    only estimates staleness (read-only), it never syncs.
    """
    from backend.services.refresh_service import RefreshService

    start = time.time()
    force = getattr(args, "refresh", False)
    no_refresh = getattr(args, "no_refresh", False)
    freshness_hours = getattr(args, "freshness_hours", None)
    service = RefreshService(fdb_repo_path=str(Path(args.fdb_dir).resolve()))

    if args.dry_run:
        stale, fresh, unknown = service.check_freshness(
            list(universe), max_age_hours=freshness_hours
        )
        elapsed = time.time() - start
        return (
            f"SEC refresh (dry-run estimate): {len(stale)} stale of "
            f"{len(universe)} analyzed · {len(fresh)} fresh · "
            f"{len(unknown)} unmapped ({elapsed:.0f}s)"
        )

    result = service.ensure_fresh_and_prices(
        list(universe),
        force=force,
        max_age_hours=freshness_hours,
        skip_refresh=no_refresh or None,
        fetch_prices=False,  # the workflow prefetches prices separately below
    )
    elapsed = time.time() - start

    parts = [f"{len(result.refreshed)} refreshed", f"{len(result.skipped)} fresh/skipped"]
    if result.failed:
        parts.append(f"{len(result.failed)} failed")
    parts.append(f"{elapsed:.0f}s")
    status = "SEC refresh (targeted): " + " · ".join(parts)

    if result.failed:
        for ticker, reason in result.failed[:10]:
            logger.warning("refresh failed %s: %s", ticker, reason)
        if len(result.failed) > 10:
            logger.warning("... and %d more refresh failures", len(result.failed) - 10)
    for note in result.notes:
        logger.warning("refresh note: %s", note)

    return status


def _run(args) -> None:
    from backend.app.cli import (
        build_analysis_service,
        build_financial_repository,
    )
    from backend.providers.snapshot import SnapshotMarketProvider
    from backend.screener.screener_service import ScreenerService
    from backend.services.daily_report_service import (
        DailyReport,
        alert_to_dict,
        build_markdown,
        load_state,
        render_alerts,
        save_state,
        trim_state,
    )
    from backend.services.price_service import (
        PRICE_FAILURE_DELISTED,
        PRICE_FAILURE_GLITCH,
        PRICE_FAILURE_MAPPING,
        PRICE_FAILURE_UNKNOWN,
        get_price_service,
    )

    report_date = (
        date.fromisoformat(args.date) if args.date else datetime.now().date()
    )
    start_time = time.time()
    universe = _load_universe(args.universe)
    if args.limit:
        universe = universe[: args.limit]
        logger.info("constrained to first %d tickers of the universe", args.limit)
    logger.info("universe loaded: %d tickers", len(universe))

    # Phase timing — a lightweight wall-clock trace of the workflow so runs
    # can be benchmarked and regressions spotted (refresh / prices / analysis
    # / alerts / report). Cost is negligible.
    timings: dict[str, float] = {}
    tick = time.time()

    # Targeted SEC refresh of ONLY the analyzed tickers (stale companies via
    # per-CIK `sec sync`). Dry-run computes a read-only staleness estimate;
    # --no-update skips the refresh but still screens + writes.
    if args.no_update:
        sec_update_status = "SEC refresh: skipped (--no-update)"
    else:
        sec_update_status = _run_targeted_refresh(universe, args)
    timings["refresh"] = time.time() - tick
    tick = time.time()

    fdb_repo = build_financial_repository()
    price_service = get_price_service()
    cache: dict[str, dict | None] = {}

    # One Yahoo quote-summary (.info) request per ticker carries price, market
    # cap, enterprise value, beta and shares — prefetched once here so the
    # parallel analysis below runs with *zero* further network calls. With
    # --no-prices the provider is empty and all market fields degrade to
    # N/A (truly network-free).
    if args.no_prices:
        market_provider = SnapshotMarketProvider({})
        price_failures: dict[str, str] = {}
    else:
        # Quote-summary bursts are far more tolerant than history() bursts: a
        # 100-ticker probe saw 0 failures at 4 and 6 workers, while history()
        # throttled at 3+. Still cap at min(workers, 4) and keep the paced,
        # batched fetch so transient errors are absorbed by the retry-once.
        snapshot_workers = min(args.workers, 4)
        logger.info(
            "prefetching market snapshots (.info) for %d tickers "
            "(batch=%d, delay=%.2fs, workers=%d)",
            len(universe),
            args.batch_size,
            args.batch_delay,
            snapshot_workers,
        )
        snapshots = price_service.get_market_snapshots(
            list(universe),
            batch_size=args.batch_size,
            delay=args.batch_delay,
            workers=snapshot_workers,
        )
        unavailable = [t for t, s in snapshots.items() if s is None]
        price_failures = _classify_price_failures(
            unavailable, price_service, fdb_repo
        )
        market_provider = SnapshotMarketProvider(snapshots)
    timings["prices"] = time.time() - tick
    tick = time.time()

    analysis_service = build_analysis_service(market_provider=market_provider)

    def analyzer(ticker: str):
        if ticker not in cache:
            try:
                cache[ticker] = analysis_service.analyze(ticker)
            except Exception as e:  # noqa: BLE001
                logger.warning("analyze failed for %s: %s", ticker, e)
                cache[ticker] = None
        return cache[ticker]

    # Real-time price enrichment served from the warm cache above, fetched
    # only for the analyzed universe.
    screener = ScreenerService(
        analyzer=analyzer,
        universe=universe,
        price_service=price_service,
        no_prices=args.no_prices,
        workers=args.workers,
    )
    screened = screener.run()
    logger.info("screened %d of %d tickers", len(screened), len(universe))
    timings["analysis"] = time.time() - tick
    tick = time.time()

    previous = (
        {}
        if args.dry_run
        else load_state(str(Path(args.out) / "daily_state.json"))
    )
    alerts = run_alerts(cache, previous)
    timings["alerts"] = time.time() - tick
    tick = time.time()

    def name_resolver(ticker: str) -> str | None:
        getter = getattr(fdb_repo, "get_company_name", None)
        if not getter:
            return None
        try:
            return getter(ticker)
        except Exception:  # noqa: BLE001 — name must never break the report
            return None

    rows = [_row_of(item, name_resolver) for item in screened[: args.top]]
    missing = sorted(tick for tick in universe if cache.get(tick) is None)

    price_notes = []
    if args.no_prices:
        price_notes.append("prices not fetched (--no-prices); valuation may be N/A")
    else:
        unavailable = [
            item.ticker for item in screened if not (item.metrics or {})
        ]
        if unavailable:
            price_notes.append(
                f"real-time price unavailable for: {', '.join(unavailable)}"
            )
        # Categorized price-fetch failures: glitches surface as warnings and
        # mapping gaps as errors in the report; delisted/unknown tickers are
        # skipped silently (INFO only) so a known-dead symbol never clutters
        # the daily report.
        glitches = sorted(
            t for t, c in price_failures.items()
            if c == PRICE_FAILURE_GLITCH
        )
        mapping_gaps = sorted(
            t for t, c in price_failures.items()
            if c == PRICE_FAILURE_MAPPING
        )
        undetermined = sorted(
            t for t, c in price_failures.items()
            if c not in (
                PRICE_FAILURE_GLITCH, PRICE_FAILURE_MAPPING, PRICE_FAILURE_DELISTED
            )
        )
        if glitches:
            price_notes.append(
                "Yahoo quote glitch (transient; analyzed with market fields N/A): "
                + ", ".join(glitches)
            )
        if mapping_gaps:
            price_notes.append(
                "ERROR — ticker not mapped to a listed company "
                "(universe/mapping gap): " + ", ".join(mapping_gaps)
            )
        if undetermined:
            price_notes.append(
                "no market data and listing state undetermined: "
                + ", ".join(undetermined)
            )

    report = DailyReport(
        report_date=report_date,
        universe_size=len(universe),
        screened_count=len(screened),
        sec_update=sec_update_status,
        prices_mode="no-prices" if args.no_prices else "real-time",
        rows=rows,
        alerts=[alert_to_dict(a) for a in alerts],
        missing=missing,
        price_notes=price_notes,
        runtime_seconds=time.time() - start_time,
    )
    body = build_markdown(report)
    timings["report"] = time.time() - tick
    timings["total"] = time.time() - start_time
    for name, elapsed in timings.items():
        logger.info("[timing] %s: %.1fs", name, elapsed)

    if args.dry_run:
        print("=== DRY-RUN — no files written ===")
        print(body)
        return

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"daily_{report_date.isoformat()}.md"
    report_path.write_text(body, encoding="utf-8")
    print(f"Report written: {report_path}")

    state_path = out_dir / "daily_state.json"
    save_state(str(state_path), trim_state(cache))
    print(f"State written: {state_path}")

    print(f"Timings: {_format_timings(timings)}")

    print(sec_update_status)
    print(f"Universe: {len(universe)} | Passed screen: {len(screened)}")
    if alerts:
        print("\nAlerts:")
        for line in render_alerts(alerts):
            print(line)
    else:
        print("No alerts.")


def run_alerts(analyses: dict, previous: dict) -> list:
    """Evaluate the alert engine over the cached analyses."""
    from backend.alerts import run

    return run(analyses, previous or None)


def _classify_price_failures(
    unavailable: list[str],
    price_service,
    fdb_repo,
) -> dict[str, str]:
    """Categorize failed quote fetches and route them by severity.

    Returns ``{TICKER: category}`` and logs each failure once:

    - ``delisted``/``unknown`` — INFO only (silently skipped in the report);
    - ``yahoo_glitch``        — WARNING (transient; company is still screened
      with market fields N/A);
    - ``mapping``             — ERROR (universe ticker cannot be resolved to
      a listed company).

    Classification re-probes Yahoo per failed ticker (the failure itself is
    ambiguous — chart-endpoint rate limits trigger false ``possibly
    delisted`` noise on very liquid names), so it is parallelized with a
    small worker pool when more than one symbol failed.
    """
    from concurrent.futures import ThreadPoolExecutor

    known = getattr(fdb_repo, "has_active_listing", None)
    known_ticker = known if callable(known) else None

    failures: dict[str, str] = {}
    if not unavailable:
        return failures

    def _one(ticker: str) -> tuple[str, str]:
        return ticker, price_service.classify_price_failure(
            ticker, known_ticker=known_ticker
        )

    if len(unavailable) > 1:
        workers = min(4, len(unavailable))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for ticker, category in pool.map(_one, unavailable):
                failures[ticker] = category
    else:
        ticker = unavailable[0]
        failures[ticker] = _one(ticker)[1]

    for ticker in unavailable:
        category = failures[ticker]
        if category == PRICE_FAILURE_MAPPING:
            logger.error(
                "%s: ticker cannot be mapped to a listed company "
                "(universe/mapping gap)",
                ticker,
            )
        elif category == PRICE_FAILURE_GLITCH:
            logger.warning(
                "%s: transient Yahoo quote glitch (data available on retry)",
                ticker,
            )
        else:  # delisted / unknown — silently skipped, INFO only
            logger.info("skipping %s: no market data (%s)", ticker, category)
    return failures


def _format_timings(timings: dict[str, float]) -> str:
    """Compact wall-clock summary: `refresh 12s · prices 34s · analysis 210s ...`."""
    order = ("refresh", "prices", "analysis", "alerts", "report", "total")
    parts = []
    for name in order:
        if name in timings:
            parts.append(f"{name} {timings[name]:.0f}s")
    return " · ".join(parts)


def _row_of(item, name_resolver=None) -> dict:
    metrics = item.metrics or {}
    return {
        "rank": item.rank,
        "ticker": item.ticker,
        "name": ordered_name_of(item)
        if name_resolver is None
        else name_resolver(item.ticker),
        "rating": item.rating,
        "total_score": item.total_score or 0.0,
        "rank_score": item.rank_score or 0.0,
        "price": metrics.get("price"),
        "per": metrics.get("per"),
        "fcf_yield": metrics.get("fcf_yield"),
        "ev_ebit": metrics.get("ev_ebit"),
        "signal": item.signal,
    }


def ordered_name_of(item):
    """Company name when available, otherwise a simple placeholder."""
    try:
        from backend.adapters.database.repositories.company_repository import (
            CompanyRepository,
        )

        company = CompanyRepository().find_by_ticker(item.ticker)
        if company and company.name:
            return company.name
    except Exception:  # noqa: BLE001
        pass
    return None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="daily_workflow.py")
    p.add_argument(
        "--universe",
        default="config/universe.csv",
        help="Universe file — CSV (ticker,cik,company_name,source_index) or "
        "plain text (default: config/universe.csv)",
    )
    p.add_argument(
        "--out",
        default="data/reports",
        help="Directory for reports and state (default: data/reports)",
    )
    p.add_argument("--date", default=None, help="Report date (YYYY-MM-DD)")
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Analyze only the first N tickers of the universe",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="Price-fetch batch size (default: 25)",
    )
    p.add_argument(
        "--batch-delay",
        type=float,
        default=0.2,
        help="Seconds to pause between price-fetch batches (default: 0.2)",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=int(os.getenv("WORKFLOW_WORKERS", "1")),
        help="Parallel workers for price prefetch and analysis "
        "(default: 1; override with WORKFLOW_WORKERS)",
    )
    p.add_argument(
        "--no-update", action="store_true", help="Skip the SEC refresh but still screen + write"
    )
    refresh_group = p.add_mutually_exclusive_group()
    refresh_group.add_argument(
        "--refresh",
        action="store_true",
        help="Force a targeted SEC refresh of the analyzed tickers even when fresh",
    )
    refresh_group.add_argument(
        "--no-refresh",
        action="store_true",
        help="Skip the targeted SEC refresh entirely (stale companies stay stale)",
    )
    p.add_argument(
        "--freshness-hours",
        type=int,
        default=None,
        help="Override the freshness threshold (hours) for the targeted SEC refresh "
        "(default: 168)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip the SEC update and write nothing; print the report",
    )
    p.add_argument(
        "--no-prices",
        action="store_true",
        help="Do not fetch real-time prices (valuation may be N/A)",
    )
    p.add_argument("--top", type=int, default=20, help="Top rows in the table")
    p.add_argument(
        "--fdb-dir",
        default=os.getenv("FDB_DIR", "../Financial-DataBase"),
        help="Financial-DataBase repo directory",
    )
    p.add_argument(
        "--fdb-python",
        default=None,
        help="Python of the Financial-DataBase venv (default: <fdb-dir>/.venv/bin/python)",
    )
    p.add_argument("--verbose", action="store_true")
    return p


def main() -> None:
    args = build_parser().parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    if args.fdb_python is None:
        args.fdb_python = str(Path(args.fdb_dir) / ".venv" / "bin" / "python")
    try:
        _run(args)
    except KeyboardInterrupt:
        print("Interrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()