#!/usr/bin/env python3
"""Recurring data-sample validation against SEC EDGAR.

Selects a reproducible sample of S&P 500 tickers from ``config/universe.csv``,
reads each company's latest completed fiscal year from Financial-DataBase
**read-only** (this script never writes to any database) and compares five
fundamentals with the same figures fetched *directly* from SEC EDGAR's
``companyconcept`` API. Yahoo Finance is consulted as an optional third source.

A field is flagged when the relative difference exceeds ``--threshold``
(default 5%). Reports are written to
``logs/validation_<YYYY-MM-DD>.{log,json}``.

Usage::

    python -m scripts.validate_data_sample --sample 20
    python -m scripts.validate_data_sample --sample 20 --out logs/

Exit codes:
    0  no discrepancies
    1  at least one field differs by more than the threshold
    2  the script could not run (no database, no network / no SEC contact)
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import os
import random
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.sec_facts_client import (
    SEC_TIMEOUT_SECONDS,
    SecFactsClient,
    annual_facts,
    concept_has_facts,
)
from backend.services.sec_facts_client import (
    parse_date as _parse_date,
)

#: Names this module re-exports: callers (and the tests) reach the shared client
#: and its helpers through the validation script, as they always have.
__all__ = [
    "SEC_TIMEOUT_SECONDS",
    "SecCompanyFactsClient",
    "SecConceptClient",
    "SecFactsClient",
    "annual_fact",
    "annual_facts",
    "concept_has_facts",
]

DEFAULT_UNIVERSE = PROJECT_ROOT / "config" / "universe.csv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "logs"
DEFAULT_SAMPLE_SIZE = 20
DEFAULT_SEED = 42
DEFAULT_THRESHOLD_PCT = 5.0

# (metric, ordered SEC us-gaap tags). First tag that yields an annual fact wins.
METRICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "revenue",
        (
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
        ),
    ),
    (
        "net_income",
        (
            "NetIncomeLoss",
            "NetIncomeLossAvailableToCommonStockholdersBasic",
        ),
    ),
    ("total_assets", ("Assets",)),
    ("total_liabilities", ("Liabilities",)),
    (
        "operating_cash_flow",
        (
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ),
    ),
)


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------
def pct_difference(db_value: float | None, ext_value: float | None) -> float | None:
    """Relative difference (in %) of ``db_value`` against ``ext_value``.

    Returns None — i.e. "skip" — when either side is missing or ``ext_value``
    is zero (a relative difference against zero is undefined).
    """
    if db_value is None or ext_value is None:
        return None
    denominator = abs(float(ext_value))
    if denominator == 0:
        return None
    return abs(float(db_value) - float(ext_value)) / denominator * 100.0


def compare_metric(
    db_value: float | None,
    ext_value: float | None,
    threshold: float = DEFAULT_THRESHOLD_PCT,
) -> dict[str, Any]:
    """Compare one metric, returning db/ext values, the difference and a flag."""
    diff = pct_difference(db_value, ext_value)
    return {
        "db": db_value,
        "ext": ext_value,
        "diff_pct": diff,
        "flagged": diff is not None and diff > threshold,
        "skipped": diff is None,
    }


def annual_fact(
    concept: Mapping[str, Any] | None, fiscal_year_end: date | None = None
) -> float | None:
    """The annual (10-K / 10-K/A, full-year) value in a concept payload.

    Delegates to the shared parser in :mod:`backend.services.sec_facts_client`
    so the validation and the audit read the same filing the same way: among the
    full-year facts, the one whose period end is closest to ``fiscal_year_end``
    wins; ties break on the most recently filed fact. ``None`` when the payload
    carries no annual fact.
    """
    facts = annual_facts(concept, fiscal_year_end)
    return facts[0].value if facts else None


# ---------------------------------------------------------------------------
# universe sampling
# ---------------------------------------------------------------------------
def load_sp500_universe(path: Path | str = DEFAULT_UNIVERSE) -> list[tuple[str, str]]:
    """Return sorted ``(ticker, cik)`` pairs sourced from the S&P 500.

    The master universe marks provenance in the ``source_index`` column; only
    rows whose index set includes ``SP500`` are eligible, so the sample lands
    on large liquid names that both SEC and Yahoo cover.
    """
    path = Path(path)
    if not path.exists():
        return []
    pairs: list[tuple[str, str]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            ticker = (row.get("ticker") or "").strip().upper()
            cik = (row.get("cik") or "").strip()
            sources = (row.get("source_index") or "").split(",")
            if ticker and cik and any(s.strip() == "SP500" for s in sources):
                pairs.append((ticker, cik))
    return sorted(set(pairs))


def choose_sample(
    universe: Sequence[tuple[str, str]],
    size: int = DEFAULT_SAMPLE_SIZE,
    seed: int = DEFAULT_SEED,
) -> list[tuple[str, str]]:
    """Deterministic sample of ``size`` entries (same seed -> same sample)."""
    if size <= 0 or size >= len(universe):
        return list(universe)
    return random.Random(seed).sample(list(universe), size)


# ---------------------------------------------------------------------------
# SEC EDGAR client
# ---------------------------------------------------------------------------
# The transport, the ``companyfacts`` fallback and the fact parser all live in
# :mod:`backend.services.sec_facts_client`, shared with the audit script. These
# names are kept for the validation's own callers.
SecConceptClient = SecFactsClient
SecCompanyFactsClient = SecFactsClient


def _match_yahoo_index(provider: Any, ticker: str, fiscal_year_end: date | None) -> int:
    """Index of Yahoo's column whose period end matches ``fiscal_year_end``."""
    if fiscal_year_end is None:
        return 0
    try:
        entries = provider.get_fiscal_year_end_dates(ticker)
    except Exception:  # noqa: BLE001 — an unavailable provider is just "no data"
        return 0
    for index, entry in enumerate(entries):
        if _parse_date(entry.get("end_date")) == fiscal_year_end:
            return index
    return 0


def default_yahoo_fetcher(
    ticker: str,
    fiscal_year: int,
    fiscal_year_end: date | None = None,
) -> dict[str, float | None]:
    """Best-effort Yahoo figures for the five metrics (empty on failure).

    Yahoo is the optional source; a missing value is never an error. The
    fiscal-year column is matched on the period end when Yahoo exposes it, so
    the comparison anchors on the same statement the DB uses.
    """
    from backend.providers.yahoo.provider import YahooFinanceProvider

    provider = YahooFinanceProvider()
    index = _match_yahoo_index(provider, ticker, fiscal_year_end)
    financials = provider.get_financials(ticker, index)
    if financials is None:
        return {}
    return {
        "revenue": getattr(financials, "revenue", None),
        "net_income": getattr(financials, "net_income", None),
        "total_assets": getattr(financials, "total_assets", None),
        "total_liabilities": getattr(financials, "total_liabilities", None),
        "operating_cash_flow": getattr(financials, "operating_cash_flow", None),
    }


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def validate_sample(
    sample: Iterable[tuple[str, str]],
    *,
    repo: Any,
    sec_fetcher: Callable[[str, str], dict | None],
    yahoo_fetcher: Callable[[str, int, date | None], dict | None] | None = None,
    threshold: float = DEFAULT_THRESHOLD_PCT,
    metrics: Sequence[tuple[str, tuple[str, ...]]] = METRICS,
    seed: int = DEFAULT_SEED,
    sample_size: int | None = None,
) -> dict[str, Any]:
    """Compare the DB fundamentals against SEC (and optionally Yahoo).

    ``repo`` is used **read-only**: only ``get_latest_completed_fiscal_year``,
    ``get_fiscal_year_end_date`` and ``get_by_year`` are ever called.
    """
    rows: list[dict[str, Any]] = []
    flagged_fields: list[dict[str, Any]] = []
    summary = {
        "tickers": 0,
        "compared": 0,
        "skipped": 0,
        "flagged": 0,
        "no_data": 0,
        "sec_tickers": 0,
    }
    sample_list = list(sample)

    for ticker, cik in sample_list:
        row: dict[str, Any] = {
            "ticker": ticker,
            "cik": cik,
            "fiscal_year": None,
            "fiscal_year_end": None,
            "error": None,
            "metrics": {},
        }
        try:
            fiscal_year = repo.get_latest_completed_fiscal_year(ticker)
            if fiscal_year is None:
                row["error"] = "no completed fiscal year"
                summary["no_data"] += 1
                rows.append(row)
                continue
            fiscal_year_end = repo.get_fiscal_year_end_date(ticker, fiscal_year)
            financials = repo.get_by_year(ticker, fiscal_year)
            if financials is None:
                row["error"] = "no fundamentals"
                summary["no_data"] += 1
                rows.append(row)
                continue

            row["fiscal_year"] = fiscal_year
            row["fiscal_year_end"] = (
                fiscal_year_end.isoformat() if fiscal_year_end else None
            )

            db_values = {
                metric: getattr(financials, metric, None) for metric, _ in metrics
            }
            sec_values: dict[str, float | None] = {}
            for metric, tags in metrics:
                sec_values[metric] = sec_metric_value(
                    cik, tags, sec_fetcher=sec_fetcher, fiscal_year_end=fiscal_year_end
                )
            if any(value is not None for value in sec_values.values()):
                summary["sec_tickers"] += 1

            yahoo_values: dict[str, float | None] = {}
            if yahoo_fetcher is not None:
                try:
                    yahoo_values = (
                        yahoo_fetcher(ticker, fiscal_year, fiscal_year_end) or {}
                    )
                except Exception:  # noqa: BLE001 — Yahoo is optional
                    yahoo_values = {}

            for metric, _tags in metrics:
                db_value = db_values.get(metric)
                check = compare_metric(db_value, sec_values.get(metric), threshold)
                yahoo_value = yahoo_values.get(metric)
                yahoo_diff = pct_difference(db_value, yahoo_value)
                check["yahoo"] = yahoo_value
                check["yahoo_diff_pct"] = yahoo_diff
                check["yahoo_flagged"] = (
                    yahoo_diff is not None and yahoo_diff > threshold
                )
                row["metrics"][metric] = check

                if check["skipped"]:
                    summary["skipped"] += 1
                else:
                    summary["compared"] += 1
                if check["flagged"]:
                    summary["flagged"] += 1
                    flagged_fields.append(
                        {
                            "ticker": ticker,
                            "metric": metric,
                            "source": "sec_edgar",
                            "db": db_value,
                            "ext": check["ext"],
                            "diff_pct": check["diff_pct"],
                        }
                    )
                if check["yahoo_flagged"]:
                    summary["flagged"] += 1
                    flagged_fields.append(
                        {
                            "ticker": ticker,
                            "metric": metric,
                            "source": "yahoo_finance",
                            "db": db_value,
                            "ext": yahoo_value,
                            "diff_pct": yahoo_diff,
                        }
                    )
            summary["tickers"] += 1
        except Exception as exc:  # noqa: BLE001 — one bad ticker must not abort
            row["error"] = f"{type(exc).__name__}: {exc}"
            summary["no_data"] += 1
        rows.append(row)

    sources = ["financial_database", "sec_edgar"]
    if yahoo_fetcher is not None:
        sources.append("yahoo_finance")

    return {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sample_size": len(sample_list) if sample_size is None else sample_size,
        "seed": seed,
        "threshold_pct": threshold,
        "sources": sources,
        "tickers": rows,
        "summary": summary,
        "flagged_fields": flagged_fields,
    }


def sec_metric_value(
    cik: str,
    tags: Iterable[str],
    *,
    sec_fetcher: Callable[[str, str], dict | None],
    fiscal_year_end: date | None,
) -> float | None:
    """First annual value among the ordered tags, or None when none has data."""
    for tag in tags:
        concept = sec_fetcher(cik, tag)
        if concept:
            value = annual_fact(concept, fiscal_year_end)
            if value is not None:
                return value
    return None


# ---------------------------------------------------------------------------
# report rendering / writing
# ---------------------------------------------------------------------------
def _format_quantity(value: Any) -> str:
    """Render a quantity: numbers get thousands separators, missing -> N/A."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:,.0f}"
    return "N/A" if value is None else str(value)


def format_report(report: dict[str, Any]) -> str:
    """Render the human-readable report (the ``.log`` payload)."""
    lines = [
        f"Validation report {report['generated_at']}",
        (
            f"Sample: {report['sample_size']} (seed {report['seed']}), "
            f"threshold {report['threshold_pct']:.1f}%"
        ),
        f"Sources: {', '.join(report['sources'])}",
        "",
    ]
    for row in report["tickers"]:
        header = f"{row['ticker']} (CIK {row['cik']})"
        if row["fiscal_year"]:
            header += f" FY{row['fiscal_year']}"
        if row["fiscal_year_end"]:
            header += f" (end {row['fiscal_year_end']})"
        lines.append(header)
        if row["error"]:
            lines.append(f"  ERROR: {row['error']}")
            continue
        for metric, check in row["metrics"].items():
            diff = check["diff_pct"]
            diff_text = f"{diff:.2f}%" if diff is not None else "skipped"
            marker = "  <-- FLAGGED" if check["flagged"] else ""
            lines.append(
                f"  {metric:<20} db={_format_quantity(check['db'])} "
                f"sec={_format_quantity(check['ext'])} diff={diff_text}{marker}"
            )
        lines.append("")

    lines.append("Flagged fields:")
    if not report.get("flagged_fields"):
        lines.append("  (none)")
    for item in report.get("flagged_fields", []):
        lines.append(
            f"  {item['ticker']:<6} {item['metric']:<20} {item['source']:<14} "
            f"db={_format_quantity(item['db'])} ext={_format_quantity(item['ext'])} "
            f"diff={item['diff_pct']:.2f}%"
        )
    summary = report["summary"]
    lines.append("")
    lines.append(
        "Summary: "
        f"tickers={summary['tickers']} "
        f"compared={summary['compared']} "
        f"skipped={summary['skipped']} "
        f"flagged={summary['flagged']} "
        f"no_data={summary['no_data']}"
    )
    return "\n".join(lines) + "\n"


def write_reports(
    report: dict[str, Any],
    out_dir: Path | str = DEFAULT_OUT_DIR,
    *,
    when: date | None = None,
) -> tuple[Path, Path]:
    """Write the ``.log`` and ``.json`` reports; returns their paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    day = (when or datetime.now(UTC).date()).isoformat()
    log_path = out_dir / f"validation_{day}.log"
    json_path = out_dir / f"validation_{day}.json"
    log_path.write_text(format_report(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return log_path, json_path


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recurring data-sample validation against SEC EDGAR."
    )
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE))
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD_PCT)
    parser.add_argument("--timeout", type=float, default=SEC_TIMEOUT_SECONDS)
    parser.add_argument(
        "--no-yahoo",
        action="store_true",
        help="compare against SEC EDGAR only (skip Yahoo Finance)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the validation and return the process exit code."""
    args = _parse_args(argv)
    with contextlib.suppress(Exception):  # dotenv is optional; env may already be set
        from dotenv import load_dotenv

        load_dotenv()

    from backend.repositories.financial_database_repository import (
        FinancialDatabaseRepository,
    )

    repo = FinancialDatabaseRepository()
    if not repo.available():
        print("error: Financial-DataBase is not reachable", file=sys.stderr)
        return 2

    universe = load_sp500_universe(args.universe)
    if not universe:
        print(f"error: no S&P 500 tickers found in {args.universe}", file=sys.stderr)
        return 2
    sample = choose_sample(universe, args.sample, args.seed)

    user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if not user_agent:
        print("error: SEC_USER_AGENT is not set", file=sys.stderr)
        return 2

    client = SecConceptClient(user_agent, timeout=args.timeout)
    yahoo_fetcher = None if args.no_yahoo else default_yahoo_fetcher

    report = validate_sample(
        sample,
        repo=repo,
        sec_fetcher=client.fetch,
        yahoo_fetcher=yahoo_fetcher,
        threshold=args.threshold,
        seed=args.seed,
        sample_size=len(sample),
    )
    log_path, json_path = write_reports(report, args.out)
    print(format_report(report), end="")
    print(f"wrote {log_path} and {json_path}")

    if report["summary"]["sec_tickers"] == 0:
        print("error: SEC EDGAR could not be reached for any ticker", file=sys.stderr)
        return 2
    return 1 if report["summary"]["flagged"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
