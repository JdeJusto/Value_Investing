#!/usr/bin/env python3
"""Daily fundamentals + valuation workflow.

1. (optional) Targeted SEC refresh in Financial-DataBase — only the analyzed
   tickers are checked for staleness and only the stale ones are synced
   (per-CIK `sec sync`); the full universe is never synced wholesale. A
   per-run cap (--max-refresh, default 200) defers the least-recent
   companies to later runs.
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
  --universe        named subset (sp500, nasdaq100, sp500,nasdaq100,
                    russell2000, european, all) or a path to a universe file
  --max-refresh N   cap the number of stale companies SEC-synced per run
                    (default 200; the most-recently-synced are prioritized)
  --resume          resume an interrupted run from the per-run checkpoint
                    (data/reports/daily_run_state.json; default). Completed
                    tickers are not refreshed again and transient refresh
                    failures are retried; the report/analysis is recomputed
                    for the whole universe.
  --no-resume       archive any previous run state and start a fresh run
  --run-id ID       resume a specific run id (live state or archived copy)
  --refresh         force a targeted SEC refresh of the analyzed tickers
  --no-refresh      skip the targeted SEC refresh entirely
  --freshness-hours override the freshness threshold (default: 168)

Interruptions (SIGTERM/SIGINT) finish the current ticker, flush the run
state atomically and exit 0; a SIGKILL/power loss leaves the last flushed
state, which the next run resumes. See docs/runbook_daily.md.
"""

import argparse
import csv
import logging
import os
import signal
import sys
import time
import threading
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

from backend.services.price_service import (
    PRICE_FAILURE_DELISTED,
    PRICE_FAILURE_GLITCH,
    PRICE_FAILURE_MAPPING,
    get_price_service,
)
from backend.services.run_state import (
    RUN_STATE_FILENAME,
    RunState,
    is_transient_failure,
    options_fingerprint,
)

load_dotenv()

logger = logging.getLogger("daily_workflow")

# Master universe produced by scripts/build_universe.py. Named --universe
# subsets (sp500 / nasdaq100 / russell2000 / european / all) are filtered
# from this file by the source_index column.
MASTER_UNIVERSE = "config/universe.csv"
MAX_REFRESH_DEFAULT = 200
# Quote-summary prefetch tolerates higher concurrency than history() bursts
# (a 100-ticker probe saw 0 failures up to 6 workers).
SNAPSHOT_WORKERS_CAP = 6
NAMED_UNIVERSE_TOKENS = frozenset({"sp500", "nasdaq100", "russell2000", "european"})
# source_index tokens naming European indices (--universe european).
EUROPEAN_INDEX_SOURCES = frozenset(
    {"FTSE100", "DAX40", "CAC40", "IBEX35", "FTSE_MIB", "AEX", "SMI", "OMXS30", "OMXC25"}
)


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


def _row_sources(source_index: str) -> set[str]:
    """source_index column -> set of index tokens (legacy BOTH expanded)."""
    sources = {s.strip() for s in source_index.split(",") if s.strip()}
    if "BOTH" in sources:
        sources = (sources - {"BOTH"}) | {"SP500", "NASDAQ100"}
    return sources


def resolve_universe(
    spec: str, master_path: str = MASTER_UNIVERSE
) -> list[str]:
    """Resolve a ``--universe`` value into a ticker list.

    ``spec`` may be a file path (existing behaviour — the file is loaded
    verbatim) or one of the named subsets:

      sp500              only rows whose source_index contains SP500
      nasdaq100          only rows whose source_index contains NASDAQ100
      sp500,nasdaq100    the union (default — the classic ~500 universe)
      russell2000        only Russell 2000 rows
      european           only SEC-filing European companies
      all                every row of the master file

    Named subsets are filtered from the master universe file
    (config/universe.csv, built by scripts/build_universe.py) by their
    source_index column, preserving file order.
    """
    if spec and os.path.isfile(spec):
        return _load_universe(spec)

    tokens = {t.strip().lower() for t in spec.split(",") if t.strip()} if spec else set()
    if not tokens or "all" in tokens:
        if not os.path.isfile(master_path):
            raise SystemExit(
                f"ERROR: master universe file not found: {master_path}. "
                "Run scripts/build_universe.py (after the fetch scripts)."
            )
        return _load_universe(master_path)

    invalid = tokens - NAMED_UNIVERSE_TOKENS
    if invalid:
        raise SystemExit(
            f"ERROR: unknown --universe subset(s): {', '.join(sorted(invalid))}. "
            f"Valid subsets: {', '.join(sorted(NAMED_UNIVERSE_TOKENS))}, all, "
            "or a path to a universe file."
        )
    if not os.path.isfile(master_path):
        raise SystemExit(
            f"ERROR: master universe file not found: {master_path}. "
            "Run scripts/build_universe.py (after the fetch scripts)."
        )

    tickers: list[str] = []
    seen: set[str] = set()
    with open(master_path, encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ticker = (row.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            sources = _row_sources(row.get("source_index") or "")
            matched = (
                ("sp500" in tokens and "SP500" in sources)
                or ("nasdaq100" in tokens and "NASDAQ100" in sources)
                or ("russell2000" in tokens and "Russell2000" in sources)
                or ("european" in tokens and bool(sources & EUROPEAN_INDEX_SOURCES))
            )
            if matched and ticker not in seen:
                seen.add(ticker)
                tickers.append(ticker)
    if not tickers:
        raise SystemExit(
            f"ERROR: no tickers matched --universe {spec!r} in {master_path}"
        )
    return tickers


def _run_targeted_refresh(
    universe: list[str],
    args,
    *,
    skip: set[str] | None = None,
    progress_cb=None,
    metrics=None,
) -> str:
    """Targeted per-CIK SEC refresh of ONLY the analyzed tickers.

    Replaces the old blanket ``sec update-incremental`` (which scanned the
    whole ~8k-company Financial-DataBase): the on-demand refresh service
    resolves each analyzed ticker's CIK and syncs just the stale companies
    of this universe, degrading gracefully per company. In dry-run mode it
    only estimates staleness (read-only), it never syncs.

    ``skip`` excludes tickers a resumed run must not refresh again
    (completed in a previous run, or permanent data failures); transient
    failures are not skipped, so they get another chance.
    ``progress_cb`` is forwarded to the refresh service for checkpointing.
    """
    from backend.services.refresh_service import (
        RefreshService,
        load_refresh_config,
    )

    start = time.time()
    force = getattr(args, "refresh", False)
    no_refresh = getattr(args, "no_refresh", False)
    freshness_hours = getattr(args, "freshness_hours", None)
    max_refresh = getattr(args, "max_refresh", None)
    refresh_workers = getattr(args, "refresh_workers", None)
    config = load_refresh_config()
    if refresh_workers:
        config.refresh_workers = max(1, int(refresh_workers))
    service = RefreshService(
        config=config,
        fdb_repo_path=str(Path(args.fdb_dir).resolve()),
        metrics=metrics,
    )

    skip = skip or set()
    eligible = [t for t in universe if t not in skip]

    if args.dry_run:
        stale, fresh, unknown = service.check_freshness(
            eligible, max_age_hours=freshness_hours
        )
        elapsed = time.time() - start
        return (
            f"SEC refresh (dry-run estimate): {len(stale)} stale of "
            f"{len(eligible)} analyzed · {len(fresh)} fresh · "
            f"{len(unknown)} unmapped ({elapsed:.0f}s)"
        )

    # Cap: with more stale companies than --max-refresh, refresh only those
    # with the most recent filings and defer the rest to the next run. The
    # cap never applies to an explicit --refresh (force).
    pool = list(eligible)
    deferred: list[str] = []
    stale_count = 0
    fresh_list: list[str] = []
    unknown_list: list[str] = []
    if max_refresh is not None and not force:
        stale_ranked, fresh_list, unknown_list = service.staleness_ranked(
            eligible, max_age_hours=freshness_hours
        )
        stale_count = len(stale_ranked)
        if stale_count > max_refresh:
            pool = stale_ranked[:max_refresh]
            deferred = stale_ranked[max_refresh:]
            logger.info(
                "refresh cap: %d stale > max-refresh %d — refreshing the %d "
                "most-recently-synced and deferring %d to the next run",
                stale_count, max_refresh, len(pool), len(deferred),
            )

    result = service.ensure_fresh_and_prices(
        list(pool),
        force=force,
        max_age_hours=freshness_hours,
        skip_refresh=no_refresh or None,
        fetch_prices=False,  # the workflow prefetches prices separately below
        progress_cb=progress_cb,
    )
    elapsed = time.time() - start

    if max_refresh is not None and not force:
        parts = []
        parts.append(f"{len(result.refreshed)} refreshed")
        if result.failed:
            parts.append(f"{len(result.failed)} failed")
        parts.append(f"{stale_count} stale")
        # staleness_ranked returns LISTS (fresh / unknown); the status line
        # must report their counts, not the ticker lists.
        parts.append(f"{len(fresh_list)} fresh")
        if unknown_list:
            parts.append(f"{len(unknown_list)} unmapped")
        if deferred:
            parts.append(f"{len(deferred)} deferred (--max-refresh)")
        parts.append(f"{elapsed:.0f}s")
    else:
        parts = [f"{len(result.refreshed)} refreshed", f"{len(result.skipped)} fresh/skipped"]
        if result.failed:
            parts.append(f"{len(result.failed)} failed")
        parts.append(f"{elapsed:.0f}s")
    if getattr(result, "sec_skipped_reason", None):
        parts.append("SEC unavailable — refresh skipped")
    status = "SEC refresh (targeted): " + " · ".join(parts)

    if result.failed:
        for ticker, reason in result.failed[:10]:
            logger.warning("refresh failed %s: %s", ticker, reason)
        if len(result.failed) > 10:
            logger.warning("... and %d more refresh failures", len(result.failed) - 10)
    for note in result.notes:
        logger.warning("refresh note: %s", note)

    return status


def _open_run_state(args, universe: list[str]):
    """Create, load or archive the per-run checkpoint for this invocation.

    Returns ``None`` for --dry-run, which must not touch disk. Explicit
    ``--run-id`` resumes the stored run (live state or archive) even if the
    current options differ; otherwise a stored run with the same universe
    and options is continued, and anything else is archived first.
    """
    if args.dry_run:
        return None

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / RUN_STATE_FILENAME
    options = options_fingerprint(args)
    target_id = getattr(args, "run_id", None)

    if target_id:
        state = RunState.find(out_dir, target_id)
        if state is None:
            raise SystemExit(
                f"ERROR: no run state for --run-id {target_id!r} in {out_dir} "
                "(looked for the live state and the archive)"
            )
        if not state.matches(universe_spec=args.universe, options=options):
            logger.warning(
                "--run-id %s: stored universe/options differ from this "
                "invocation — resuming the stored run anyway (explicit request)",
                target_id,
            )
        logger.info(
            "resuming run %s: stage=%s completed=%d/%d failed=%d",
            state.run_id,
            state.current_stage,
            len(state.completed),
            state.total_tickers,
            len(state.failed),
        )
        return state

    state = RunState.load(path) if path.exists() else None

    if state is not None and not args.resume:
        archived = state.archive()
        logger.info("--no-resume: archived run %s to %s", state.run_id, archived.name)
        state = None

    if state is not None and not state.matches(
        universe_spec=args.universe, options=options
    ):
        archived = state.archive()
        logger.warning(
            "previous run %s has a different universe/options — archived to "
            "%s; starting fresh",
            state.run_id,
            archived.name,
        )
        state = None

    if state is None:
        state = RunState.create(
            path,
            universe_spec=args.universe,
            options=options,
            total_tickers=len(universe),
        )
        logger.info(
            "new run %s (%d tickers, universe=%s)",
            state.run_id,
            len(universe),
            args.universe,
        )
        return state

    logger.info(
        "resume: run %s stage=%s completed=%d/%d failed=%d — continuing",
        state.run_id,
        state.current_stage,
        len(state.completed),
        state.total_tickers,
        len(state.failed),
    )
    return state


def _resume_skip_set(run_state) -> set[str]:
    """Tickers a resumed run must NOT refresh again.

    ``completed`` (already analyzed end-to-end) plus refresh failures with a
    permanent (data) reason. Transient refresh failures are deliberately not
    included: a resume is exactly when they get retried.
    """
    if run_state is None:
        return set()
    permanent_refresh = {
        ticker
        for ticker, reason in run_state.failed.items()
        if reason.startswith("refresh:") and not is_transient_failure(reason)
    }
    return run_state.completed_set | permanent_refresh


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

    report_date = (
        date.fromisoformat(args.date) if args.date else datetime.now().date()
    )
    start_time = time.time()
    universe = resolve_universe(args.universe)
    if args.limit:
        universe = universe[: args.limit]
        logger.info("constrained to first %d tickers of the universe", args.limit)
    logger.info("universe loaded: %d tickers", len(universe))

    # Robust background running: the per-run checkpoint
    # (data/reports/daily_run_state.json) is updated after every completed
    # ticker so an interrupted run — SIGTERM, crash, power loss — resumes
    # without redoing finished work. --resume is the default; --no-resume
    # archives the previous state and starts fresh.
    stop_event = threading.Event()
    run_state = _open_run_state(args, universe)
    resume_skip = _resume_skip_set(run_state)
    if resume_skip:
        logger.info(
            "resume: %d tickers excluded from the refresh pool "
            "(completed or permanent refresh failures)",
            len(resume_skip),
        )

    def _shutdown_requested() -> bool:
        return stop_event.is_set()

    def _clean_shutdown() -> bool:
        """Flush the checkpoint and stop cleanly when a signal asked for it."""
        if not _shutdown_requested():
            return False
        if run_state is not None:
            run_state.save()
            logger.warning(
                "shutdown requested — state saved (run %s, %d completed, "
                "stage %s); resume with --resume",
                run_state.run_id,
                len(run_state.completed),
                run_state.current_stage,
            )
            print(
                f"Shutdown requested: state saved (run {run_state.run_id}); "
                "resume with --resume"
            )
        return True

    if run_state is not None:

        def _on_signal(signum, _frame):
            if not stop_event.is_set():
                logger.warning(
                    "received %s — finishing the current ticker, then saving state",
                    signal.Signals(signum).name,
                )
            stop_event.set()

        signal.signal(signal.SIGTERM, _on_signal)
        signal.signal(signal.SIGINT, _on_signal)

    # Phase timing — a lightweight wall-clock trace of the workflow so runs
    # can be benchmarked and regressions spotted (refresh / prices / analysis
    # / alerts / report). Cost is negligible.
    timings: dict[str, float] = {}
    tick = time.time()

    fdb_repo = build_financial_repository()
    price_service = get_price_service()
    cache: dict[str, dict | None] = {}

    # Run telemetry: per-company SEC sync counts/retries/throttling and
    # per-attempt Yahoo counters (backend/services/network_metrics.py). They
    # end up in the run state and the report; nothing else reads them.
    from backend.services.network_metrics import NetworkMetrics
    from backend.services.yahoo_health import check_yahoo_availability

    network_metrics = NetworkMetrics()
    if price_service is not None:
        # Wire the Yahoo preflight + telemetry into the shared price service
        # (get_price_service() is a process-level singleton), so both the batch
        # prefetch and the single-price calls of the analysis are covered.
        price_service.configure(metrics=network_metrics, health_fn=check_yahoo_availability)

    # Fundamentals cache: skips the per-ticker database read (the ~96 % of the
    # analysis cost) when neither the company's facts nor the analysis version
    # changed. Price-derived metrics are always recomputed from the live
    # snapshot below, so a cache hit can never serve stale market data.
    from backend.services.analysis_cache import AnalysisCache

    analysis_cache = AnalysisCache(repository=fdb_repo, enabled=not args.no_cache)
    if not args.no_cache:
        logger.info(
            "fundamentals cache: %s (version %s)",
            analysis_cache.directory,
            analysis_cache.version,
        )

    # One Yahoo quote-summary (.info) request per ticker carries price, market
    # cap, enterprise value, beta and shares — prefetched once here so the
    # parallel analysis below runs with *zero* further network calls. With
    # --no-prices the provider is empty and all market fields degrade to
    # N/A (truly network-free).
    #
    # Overlap: snapshot prices do NOT depend on the SEC sync, so the prefetch
    # runs in a background thread *while* the targeted refresh runs and the
    # Yahoo phase is hidden under the sync phase (the longest stage). The
    # thread's own duration is still reported as ``prices`` so timings stay
    # honest; ``prices_critical`` is how much of it actually blocked the run.
    prefetch_thread: threading.Thread | None = None
    prefetch_result: dict = {}

    def _do_prefetch() -> None:
        t0 = time.time()
        try:
            snapshot_workers = min(args.workers, SNAPSHOT_WORKERS_CAP)
            logger.info(
                "prefetching market snapshots (.info) for %d tickers "
                "(batch=%d, delay=%.2fs, workers=%d) [overlapped with refresh]",
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
            prefetch_result["snapshots"] = snapshots
            unavailable = [t for t, s in snapshots.items() if s is None]
            prefetch_result["provider"] = SnapshotMarketProvider(snapshots)
            prefetch_result["failures"] = _classify_price_failures(
                unavailable, price_service, fdb_repo
            )
        except BaseException as exc:  # noqa: BLE001 — re-raised on join
            prefetch_result["exc"] = exc
        finally:
            prefetch_result["elapsed"] = time.time() - t0

    if not args.no_prices:
        prefetch_thread = threading.Thread(target=_do_prefetch, daemon=True)
        prefetch_thread.start()

    # Targeted SEC refresh of ONLY the analyzed tickers (stale companies via
    # per-CIK `sec sync`). Dry-run computes a read-only staleness estimate;
    # --no-update skips the refresh but still screens + writes. The snapshot
    # prefetch above runs concurrently because prices are independent of it.
    if args.no_update:
        sec_update_status = "SEC refresh: skipped (--no-update)"
    else:

        def _refresh_progress(ticker: str, status) -> None:
            """Checkpoint each attempted sync (transient failures retried
            by the next resumed run)."""
            if run_state is None:
                return
            run_state.note_progress("refresh", ticker)
            if status is not True:
                run_state.add_failed(ticker, f"refresh: {status}")

        sec_update_status = _run_targeted_refresh(
            universe,
            args,
            skip=resume_skip,
            progress_cb=_refresh_progress if run_state is not None else None,
            metrics=network_metrics,
        )
    timings["refresh"] = time.time() - tick
    tick = time.time()
    if run_state is not None:
        # Telemetry as soon as the refresh stage is over, so a long run shows
        # the SEC numbers in the checkpoint without waiting for the report.
        run_state.note_network(network_metrics.snapshot())

    if prefetch_thread is not None:
        prefetch_thread.join()
        if "exc" in prefetch_result:
            raise prefetch_result["exc"]
        market_provider = prefetch_result.get(
            "provider", SnapshotMarketProvider({})
        )
        price_failures = prefetch_result.get("failures", {})
        timings["prices"] = prefetch_result.get("elapsed", 0.0)
        # wall time that blocked the run after the refresh (≈0 when the
        # prefetch finished during the sync phase)
        timings["prices_critical"] = time.time() - tick
    else:
        market_provider = SnapshotMarketProvider({})
        price_failures = {}
        timings["prices"] = 0.0
    tick = time.time()

    if run_state is not None:
        snapshots = prefetch_result.get("snapshots") or {}
        run_state.set_stage("prices")
        run_state.set_prices_fetched(sum(1 for value in snapshots.values() if value))
        run_state.note_network(network_metrics.snapshot())
    if _clean_shutdown():
        return
    if run_state is not None:
        run_state.set_stage("analysis")

    analysis_service = build_analysis_service(
        market_provider=market_provider, analysis_cache=analysis_cache
    )

    # Thread-safe progress counter: logs every 100 analyzed tickers so large
    # universes stay visibly alive during the analysis phase.
    _progress_lock = threading.Lock()
    _progress = {"done": 0}

    def analyzer(ticker: str):
        if _shutdown_requested():
            # Signal received: do not start new work. In-flight tickers
            # finish normally and the checkpoint keeps everything already
            # done, so the next run resumes here.
            return cache.get(ticker)
        if ticker not in cache:
            try:
                result = analysis_service.analyze(ticker)
            except Exception as e:  # noqa: BLE001
                logger.warning("analyze failed for %s: %s", ticker, e)
                result = None
                if run_state is not None:
                    run_state.add_failed(ticker, f"analysis: {e}")
            else:
                if run_state is not None:
                    if result is None:
                        run_state.add_failed(ticker, "analysis: no data")
                    else:
                        run_state.add_completed(ticker)
            cache[ticker] = result
            if run_state is not None:
                run_state.note_progress("analysis", ticker)
            with _progress_lock:
                _progress["done"] += 1
                done = _progress["done"]
            if done % 100 == 0:
                logger.info(
                    "analysis progress: %d / %d tickers", done, len(universe)
                )
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
    logger.info("fundamentals cache: %s", analysis_cache.stats)
    timings["analysis"] = time.time() - tick
    tick = time.time()

    if _clean_shutdown():
        return

    previous = (
        {}
        if args.dry_run
        else load_state(str(Path(args.out) / "daily_state.json"))
    )
    alerts = run_alerts(cache, previous)
    if run_state is not None:
        run_state.set_alerts_generated(len(alerts))
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

    network_snapshot = network_metrics.snapshot()
    logger.info("network: %s", network_metrics.summary())

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
        network=network_snapshot,
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

    if run_state is not None:
        run_state.set_stage("report")

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

    if run_state is not None:
        run_state.note_network(network_snapshot)
        archived = run_state.complete()
        print(f"Run state archived: {archived}")


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
        default="sp500",
        help="Universe to screen: a named subset (sp500, nasdaq100, "
        "sp500,nasdaq100, russell2000, european, all — filtered from "
        "config/universe.csv) or a path to a universe file "
        "(default: sp500)",
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
        default=int(os.getenv("WORKFLOW_WORKERS", "4")),
        help="Parallel workers for price prefetch and analysis "
        "(default: 4; override with WORKFLOW_WORKERS)",
    )
    p.add_argument(
        "--refresh-workers",
        type=int,
        default=None,
        help="Concurrent targeted SEC syncs during refresh "
        "(default: config/refresh.yaml refresh_workers, 2)",
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
        "--max-refresh",
        type=int,
        default=MAX_REFRESH_DEFAULT,
        help=f"Cap stale companies SEC-synced per run, most-recent-synced "
        f"first (default: {MAX_REFRESH_DEFAULT}; ignored with --refresh/force)",
    )
    resume_group = p.add_mutually_exclusive_group()
    resume_group.add_argument(
        "--resume",
        dest="resume",
        action="store_true",
        default=True,
        help="Resume an interrupted run from data/reports/daily_run_state.json "
        "(default): completed tickers are not refreshed again and transient "
        "refresh failures are retried",
    )
    resume_group.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="Archive any previous run state and start a fresh run",
    )
    p.add_argument(
        "--run-id",
        default=None,
        help="Resume the specific run id (live state or archived copy)",
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
    p.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore the fundamentals cache (data/cache/analysis) and re-read "
        "every company's financials from Financial-DataBase",
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