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
import time
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_UNIVERSE = PROJECT_ROOT / "config" / "universe.csv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "logs"
DEFAULT_SAMPLE_SIZE = 20
DEFAULT_SEED = 42
DEFAULT_THRESHOLD_PCT = 5.0
SEC_TIMEOUT_SECONDS = 15.0
# SEC asks for <= 10 requests/second; 0.12 s between calls keeps us under it.
SEC_MIN_INTERVAL_SECONDS = 0.12
COMPANYCONCEPT_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{tag}.json"
)
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

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

# Annual facts span a full year; the companyconcept endpoint also returns the
# quarterly facts from the same filing, so the duration filter is what keeps a
# Q4 figure from masquerading as the annual number.
ANNUAL_MIN_DAYS = 300
ANNUAL_MAX_DAYS = 400


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------
def _parse_date(value: Any) -> date | None:
    """Parse an ISO date (tolerating a trailing time component), else None."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _duration_days(start: Any, end: Any) -> int | None:
    """Number of days between two ISO dates, or None when either is missing."""
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if start_date is None or end_date is None:
        return None
    return (end_date - start_date).days


def concept_has_facts(concept: Mapping[str, Any] | None) -> bool:
    """True when a concept payload actually carries at least one fact.

    Both SEC endpoints normally return ``units: {"USD": [ ...facts... ]}``. The
    per-tag ``companyconcept`` endpoint, however, occasionally answers ``200``
    with an *empty envelope* — ``units: {"USD": {}}`` — for an issuer whose facts
    are all present in ``companyfacts`` (observed for Coca-Cola, 2026-10). An
    empty envelope means "no data from this endpoint", never "the filing has no
    value", so callers must not read it as a missing fact.
    """
    if not concept:
        return False
    for unit in (concept.get("units") or {}).values():
        if isinstance(unit, list) and unit:
            return True
    return False


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
    concept: dict | None, fiscal_year_end: date | None = None
) -> float | None:
    """Extract the annual (10-K, full-year) value from a companyconcept payload.

    Among the facts filed in a 10-K that span a full year, the one whose period
    end is closest to ``fiscal_year_end`` wins; ties break on the most recently
    filed fact. Returns None when the payload has no annual fact.
    """
    units = (concept or {}).get("units") or {}
    facts = units.get("USD")
    if not facts:
        for candidate in units.values():
            if candidate:
                facts = candidate
                break
    if not facts:
        return None

    best_value: float | None = None
    best_rank: tuple[int, str] | None = None
    for fact in facts:
        if str(fact.get("form") or "").upper() != "10-K":
            continue
        raw_value = fact.get("val")
        if raw_value is None:
            continue
        span = _duration_days(fact.get("start"), fact.get("end"))
        if span is not None and not (ANNUAL_MIN_DAYS <= span <= ANNUAL_MAX_DAYS):
            continue
        end = _parse_date(fact.get("end"))
        distance = abs((end - fiscal_year_end).days) if (end and fiscal_year_end) else 0
        filed = str(fact.get("filed") or "")
        if (
            best_rank is None
            or distance < best_rank[0]
            or (distance == best_rank[0] and filed > best_rank[1])
        ):
            best_value = float(raw_value)
            best_rank = (distance, filed)
    return best_value


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
class _SecJsonClient:
    """Shared SEC JSON plumbing: polite pacing, failure degrades to ``None``."""

    def __init__(
        self,
        user_agent: str,
        *,
        timeout: float = SEC_TIMEOUT_SECONDS,
        min_interval: float = SEC_MIN_INTERVAL_SECONDS,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self._user_agent = user_agent
        self._timeout = timeout
        self._min_interval = max(0.0, min_interval)
        self._opener = opener or urllib.request.urlopen
        self._last_request = 0.0

    def _get_json(self, url: str) -> dict | None:
        """GET one SEC JSON document, or None on any failure."""
        self._pace()
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self._user_agent, "Accept": "application/json"},
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                payload = response.read()
        except Exception:  # noqa: BLE001 — any SEC failure just skips the tag
            return None
        try:
            return json.loads(payload)
        except (TypeError, ValueError):
            return None

    def _pace(self) -> None:
        """Keep the request rate below SEC's 10 req/s guidance."""
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()


class SecConceptClient(_SecJsonClient):
    """Minimal SEC ``companyconcept`` client with request pacing.

    Every failure (HTTP error, timeout, malformed JSON) degrades to ``None`` so
    one bad tag never aborts the validation. A ``200`` with an empty envelope is
    *not* a failure here — use :func:`concept_has_facts` to tell no-data from
    no-facts.
    """

    def fetch(self, cik: str, tag: str) -> dict | None:
        """Fetch one concept for one CIK, or None on any failure.

        ``tag`` may name a taxonomy (``dei:EntityCommonStockSharesOutstanding``);
        the SEC endpoint defaults to ``us-gaap`` when it does not.
        """
        taxonomy, _, concept = tag.partition(":")
        if not concept:
            taxonomy, concept = "us-gaap", tag
        url = COMPANYCONCEPT_URL.format(
            cik=str(cik).zfill(10), taxonomy=taxonomy, tag=concept
        )
        return self._get_json(url)


class SecCompanyFactsClient(_SecJsonClient):
    """SEC ``companyfacts`` client: one request for every tag of a company.

    Used as the fallback when ``companyconcept`` returns an empty envelope for
    an issuer (see :func:`concept_has_facts`). The whole company document is
    several megabytes, so callers fetch it at most once per company.
    """

    def concepts(self, cik: str, taxonomy: str = "us-gaap") -> dict[str, dict] | None:
        """All ``taxonomy`` concepts for one CIK, as ``{tag: {"units": ...}}``."""
        url = COMPANYFACTS_URL.format(cik=str(cik).zfill(10))
        payload = self._get_json(url)
        if payload is None:
            return None
        facts = payload.get("facts") or {}
        entries = facts.get(taxonomy) or {}
        return {
            tag: {"units": (entry or {}).get("units") or {}}
            for tag, entry in entries.items()
        }


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
