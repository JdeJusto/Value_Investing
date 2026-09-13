#!/usr/bin/env python3
"""Daily fundamentals + valuation workflow.

1. (optional) Incrementally update SEC fundamentals in Financial-DataBase.
2. Screen a configurable universe with real-time prices (fetched ONLY for
   the universe, never persisted).
3. Evaluate alerts (BUY_SIGNAL / SELL_WARNING / TRIGGER_EVENT) against the
   previous day's state.
4. Write data/reports/daily_YYYY-MM-DD.md and persist the new state.

Flags:
  --dry-run    skip the SEC update AND skip writing any file (print report)
  --no-update  skip the SEC update but still screen + write report/state
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("daily_workflow")


def _load_universe(path: str) -> list[str]:
    """Tickers from a plain text file (one per line, '#' comments)."""
    with open(path, encoding="utf-8") as handle:
        tickers = [
            line.strip().upper()
            for line in handle
            if line.strip() and not line.lstrip().startswith("#")
        ]
    if not tickers:
        raise SystemExit(f"ERROR: no tickers in universe file '{path}'")
    return tickers


def _run_sec_update(fdb_dir: str, python_path: str, verbose: bool) -> str:
    """Run Financial-DataBase's incremental SEC update; never blocks the rest."""
    start = time.time()
    env = dict(os.environ)
    env.setdefault("SEC_USER_AGENT", os.getenv("SEC_EMAIL", "daily@value-investing.local"))
    env["DATA_RAW_DIR"] = str(Path(fdb_dir) / "data" / "raw")
    cmd = [
        python_path,
        "-m",
        "financial_database.cli",
        "sec",
        "update-incremental",
        "--max-age-hours",
        "24",
    ]
    logger.info("running SEC update: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            cwd=fdb_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        elapsed = time.time() - start
        tail = " ".join(
            (result.stdout or "").strip().splitlines()[-3:]
        ) or result.stderr.strip()
        if result.returncode == 0:
            return f"SEC update: ok ({elapsed:.0f}s) — {tail or 'no output'}"
        return f"SEC update: **failed** (rc={result.returncode}, {elapsed:.0f}s) — {tail}"
    except Exception as e:  # noqa: BLE001
        return f"SEC update: **error** — {e}"


def _run(args) -> None:
    from backend.app.cli import build_analysis_service, build_financial_repository
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
    from backend.services.price_service import get_price_service

    report_date = (
        date.fromisoformat(args.date) if args.date else datetime.now().date()
    )
    universe = _load_universe(args.universe)

    if args.dry_run:
        sec_update_status = "SEC update: skipped (dry-run)"
    elif args.no_update:
        sec_update_status = "SEC update: skipped (--no-update)"
    else:
        sec_update_status = _run_sec_update(
            args.fdb_dir, args.fdb_python, args.verbose
        )

    analysis_service = build_analysis_service()
    fdb_repo = build_financial_repository()
    cache: dict[str, dict | None] = {}

    def analyzer(ticker: str):
        if ticker not in cache:
            try:
                cache[ticker] = analysis_service.analyze(ticker)
            except Exception as e:  # noqa: BLE001
                logger.warning("analyze failed for %s: %s", ticker, e)
                cache[ticker] = None
        return cache[ticker]

    # Real-time price enrichment fetched only for the universe tickers.
    screener = ScreenerService(
        analyzer=analyzer,
        universe=universe,
        price_service=get_price_service(),
        no_prices=args.no_prices,
    )
    screened = screener.run()

    previous = (
        {}
        if args.dry_run
        else load_state(str(Path(args.out) / "daily_state.json"))
    )
    alerts = run_alerts(cache, previous)

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
    )
    body = build_markdown(report)

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
        default="config/universe.txt",
        help="Universe file (one ticker per line)",
    )
    p.add_argument(
        "--out",
        default="data/reports",
        help="Directory for reports and state (default: data/reports)",
    )
    p.add_argument("--date", default=None, help="Report date (YYYY-MM-DD)")
    p.add_argument(
        "--no-update", action="store_true", help="Skip the SEC incremental update"
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