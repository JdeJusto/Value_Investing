#!/usr/bin/env python3
"""Build the weekly peer-stats artifact behind the scorecard's peer column.

Usage::

    python -m scripts.build_peer_stats                    # weekly full run
    python -m scripts.build_peer_stats --level industry   # industry files only
    python -m scripts.build_peer_stats --level sector     # sector files only
    python -m scripts.build_peer_stats --limit 20         # debug
    python -m scripts.build_peer_stats --no-prices        # offline (fundamentals)

For every ticker in the master universe the script computes the metrics the
scorecard compares against peers — using the *same* analytics the scorecard
uses (``_Metrics`` over :class:`FinancialInsightsService` plus the
``PerCalculator``/``FcfYieldCalculator``) — then writes one file per peer
group::

    data/peer_stats/industry_consumer-electronics.json
    data/peer_stats/sector_technology.json
    data/peer_stats/_index.json

Design rules (``docs/scorecard_design.md`` §5):

- **Grouping:** industry first, sector as the fallback bucket. A bucket with
  fewer than :data:`~backend.analytics.peer_stats.MIN_GROUP_COMPANIES` members
  that actually produced a metric is **skipped** (recorded in ``_index.json``,
  never written), so no comparison is ever shown against a thin group.
- **Deterministic:** same universe + same fundamentals + same market caps +
  same ``--as-of`` produce byte-identical files (no clock beyond ``--as-of``,
  sorted keys, six-decimal rounding, deterministic value sampling).
- **Read-only:** fundamentals come from Financial-DataBase read-only; market
  caps come from :class:`PriceService` (Yahoo, in-memory only). **Prices are
  never persisted** by this script.
- The artifact is a local build product: ``data/peer_stats/`` is git-ignored.

Percentile lookups read the stored sorted ``values`` array, so the scorecard
never recomputes a distribution — see
:class:`backend.services.peer_stats_service.PeerStatsService`.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.analytics.peer_stats import (
    METRIC_UNITS,
    MIN_GROUP_COMPANIES,
    summarize,
)
from backend.analytics.ratios.margins import FcfYieldCalculator
from backend.analytics.ratios.per import PerCalculator
from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
)
from backend.services.financial_insights_service import (
    FinancialInsightsService,
)
from backend.services.financials_view_service import FinancialsViewService
from backend.services.scorecard_service import HISTORY_YEARS, _Metrics

DEFAULT_UNIVERSE = ROOT / "config" / "universe.csv"
DEFAULT_OUT_DIR = ROOT / "data" / "peer_stats"

#: The two grouping levels, coarse-to-fine in the order they are resolved at
#: read time (industry wins, sector is the fallback).
LEVELS: tuple[str, ...] = ("industry", "sector")


# ---------------------------------------------------------------------------
# artifact data
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PeerCompany:
    """One company's peer-comparable metrics (``None`` values excluded)."""

    ticker: str
    sector: str | None
    industry: str | None
    metrics: dict[str, float] = field(default_factory=dict)


def _slugify(name: str) -> str:
    """``"Consumer Electronics"`` -> ``"consumer-electronics"``."""
    out: list[str] = []
    for char in str(name).strip().lower():
        if char.isalnum():
            out.append(char)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-") or "unknown"


def _group_name(company: PeerCompany, level: str) -> str | None:
    value = company.industry if level == "industry" else company.sector
    return (value or "").strip() or None


def _group(companies: Iterable[PeerCompany], level: str) -> dict[str, list]:
    groups: dict[str, list[PeerCompany]] = {}
    for company in companies:
        name = _group_name(company, level)
        if name is None:
            continue
        groups.setdefault(name, []).append(company)
    return {name: members for name, members in groups.items() if members}


def peer_artifact(
    level: str,
    name: str,
    members: Sequence[PeerCompany],
    *,
    generated_at: str,
) -> dict[str, Any]:
    """One group's artifact payload (the exact shape written to disk)."""
    contributing = [company for company in members if company.metrics]
    metrics: dict[str, dict[str, Any]] = {}
    for metric in sorted(METRIC_UNITS):
        values = [
            float(company.metrics[metric])
            for company in contributing
            if company.metrics.get(metric) is not None
        ]
        if not values:
            continue
        entry = summarize(values)
        entry["unit"] = METRIC_UNITS[metric]
        metrics[metric] = entry
    return {
        "level": level,
        "group": name,
        "slug": _slugify(name),
        "company_count": len(contributing),
        "generated_at": generated_at,
        "metrics": metrics,
    }


def build_artifacts(
    companies: Sequence[PeerCompany],
    *,
    generated_at: str,
    out_dir: Path | str = DEFAULT_OUT_DIR,
    levels: Sequence[str] = LEVELS,
) -> dict[str, Any]:
    """Write one file per qualifying peer group plus ``_index.json``.

    Returns a summary ``{"written": [...], "skipped": [...], "index": str}``.
    Groups below :data:`MIN_GROUP_COMPANIES` contributing companies are
    skipped (recorded, never written). Deterministic: the files depend only on
    ``companies``, ``levels`` and ``generated_at``.
    """
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)

    written: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for level in levels:
        for name, members in sorted(_group(companies, level).items()):
            contributing = sum(1 for company in members if company.metrics)
            if contributing < MIN_GROUP_COMPANIES:
                skipped.append(
                    {"level": level, "group": name, "company_count": contributing}
                )
                continue
            payload = peer_artifact(level, name, members, generated_at=generated_at)
            filename = f"{level}_{payload['slug']}.json"
            _write_json(directory / filename, payload)
            written.append(
                {
                    "level": level,
                    "group": name,
                    "file": filename,
                    "company_count": payload["company_count"],
                    "metrics": sorted(payload["metrics"]),
                }
            )

    index = {"generated_at": generated_at, "groups": written, "skipped": skipped}
    _write_json(directory / "_index.json", index)
    return {
        "written": written,
        "skipped": skipped,
        "index": str(directory / "_index.json"),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Sorted-key, 2-space JSON with a trailing newline (byte-stable)."""
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# metric extraction (the scorecard's own analytics)
# ---------------------------------------------------------------------------
def metrics_for(
    insights: Any,
    rows: Sequence[NormalizedFinancials],
    market_cap: float | None,
) -> dict[str, float]:
    """The peer-comparable metrics for one company.

    Uses the scorecard's ``_Metrics`` accessor, so ``net_margin``, ``roe`` and
    ``revenue_cagr_5y`` are the very values the scorecard scores, and
    ``pe_ratio``/``fcf_yield`` come from the same calculators. ``pb_ratio``
    (which the scorecard does not score) is ``market_cap / book equity``.

    Negative or missing inputs are dropped: a loss-making company has no
    meaningful P/E, and a negative-equity one has no meaningful P/B.
    """
    metrics = _Metrics(insights)
    values: dict[str, float] = {}

    cagr = metrics.cagr("revenue")
    if cagr is not None:
        values["revenue_cagr_5y"] = cagr / 100.0
    net_margin = metrics.latest("net_margin")
    if net_margin is not None:
        values["net_margin"] = net_margin
    roe = metrics.latest("roe")
    if roe is not None:
        values["roe"] = roe

    net_income = metrics.latest("net_income")
    per = PerCalculator().calculate(market_cap=market_cap, net_income=net_income)
    if per is not None and per > 0:
        values["pe_ratio"] = per

    fcf_yield = FcfYieldCalculator().calculate(
        free_cash_flow=metrics.latest("free_cash_flow", "fcf"), market_cap=market_cap
    )
    if fcf_yield is not None:
        values["fcf_yield"] = fcf_yield

    equity = rows[0].stockholders_equity if rows else None
    if market_cap and equity and equity > 0:
        values["pb_ratio"] = market_cap / equity
    return values


def collect_companies(
    tickers: Sequence[str],
    *,
    repo: Any,
    market_caps: dict[str, float] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> list[PeerCompany]:
    """Read FDB fundamentals for ``tickers`` and extract their peer metrics."""
    caps = market_caps or {}
    view = FinancialsViewService(repo)
    companies: list[PeerCompany] = []
    total = len(tickers)
    for position, ticker in enumerate(tickers, start=1):
        symbol = str(ticker).strip().upper()
        try:
            rows = list(repo.get_best_available(symbol, max_years=HISTORY_YEARS) or [])
        except Exception:  # noqa: BLE001 — one bad ticker never stops the build
            rows = []
        if progress is not None:
            progress(position, total, symbol)
        if not rows:
            continue
        rows.sort(key=lambda row: row.fiscal_year, reverse=True)
        try:
            facts = view.fetch_facts(symbol, "FY", HISTORY_YEARS)
        except Exception:  # noqa: BLE001 — degrade to "no metrics" for this ticker
            facts = []
        metrics = metrics_for(
            FinancialInsightsService(facts, symbol, symbol).build(),
            rows,
            caps.get(symbol),
        )
        companies.append(
            PeerCompany(
                ticker=symbol,
                sector=rows[0].sector,
                industry=rows[0].industry,
                metrics=metrics,
            )
        )
    return companies


# ---------------------------------------------------------------------------
# market caps (never persisted)
# ---------------------------------------------------------------------------
def prefetch_market_caps(tickers: Sequence[str]) -> dict[str, float]:
    """Current market caps from Yahoo via :class:`PriceService`.

    Never persisted: the in-memory cache is the only store. A Yahoo outage
    degrades to ``{}`` — the run then writes the fundamentals-only metrics.
    """
    from backend.services.price_service import PriceService

    service = PriceService()
    probe = getattr(service, "yahoo_available", None)
    if callable(probe):
        try:
            health = probe(force=True)
        except Exception:  # noqa: BLE001 — a broken probe never fails the build
            health = None
        if health is not None and not getattr(health, "available", True):
            print("  Yahoo unavailable: skipping market caps (no P/E, P/B, FCF yield)")
            return {}
    snapshots: dict = {}
    try:
        snapshots = (
            service.get_market_snapshots(
                list(tickers), batch_size=20, delay=0.1, workers=6, preflight=True
            )
            or {}
        )
    except Exception:  # noqa: BLE001 — no prices is a valid outcome
        snapshots = {}
    caps: dict[str, float] = {}
    for ticker, snapshot in snapshots.items():
        if not isinstance(snapshot, dict):
            continue
        cap = snapshot.get("marketCap")
        if cap is None:
            continue
        try:
            caps[str(ticker).upper()] = float(cap)
        except (TypeError, ValueError):
            continue
    return caps


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def load_universe(path: str | Path) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        rows = [
            (row.get("ticker") or "").strip().upper() for row in csv.DictReader(handle)
        ]
    seen: set[str] = set()
    tickers: list[str] = []
    for ticker in rows:
        if ticker and ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)
    return tickers


def _parse_as_of(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_peer_stats.py",
        description="Build the weekly peer-stats artifact for the scorecard.",
    )
    parser.add_argument(
        "--universe",
        default=str(DEFAULT_UNIVERSE),
        help="Universe CSV to iterate (default: config/universe.csv)",
    )
    parser.add_argument(
        "--level",
        choices=("both", *LEVELS),
        default="both",
        help="Which grouping levels to write (default: both)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Debug: process at most N tickers (default: 0 = all)",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="Artifact directory (default: data/peer_stats)",
    )
    parser.add_argument(
        "--no-prices",
        action="store_true",
        help="Skip Yahoo market caps (P/E, P/B and FCF yield are then omitted)",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="ISO timestamp stamped into the artifact (default: now, UTC)",
    )
    args = parser.parse_args(argv)

    levels = LEVELS if args.level == "both" else (args.level,)
    generated_at = _iso(_parse_as_of(args.as_of))
    tickers = load_universe(args.universe)
    if args.limit > 0:
        tickers = tickers[: args.limit]
    if not tickers:
        print(f"ERROR: no tickers in {args.universe}", file=sys.stderr)
        return 1

    print(f"Peer stats: {len(tickers)} tickers from {args.universe}")
    from backend.repositories.financial_database_repository import (
        FinancialDatabaseRepository,
    )

    repo = FinancialDatabaseRepository()
    if not repo.available():
        print("ERROR: Financial-DataBase is not reachable", file=sys.stderr)
        return 1

    caps: dict[str, float] = {}
    if not args.no_prices:
        print("  fetching market caps (Yahoo, not persisted)…")
        caps = prefetch_market_caps(tickers)
        print(f"  {len(caps)}/{len(tickers)} market caps")

    def progress(position: int, total: int, ticker: str) -> None:
        if position % 200 == 0 or position == total:
            print(f"  {position}/{total} {ticker}")

    companies = collect_companies(
        tickers, repo=repo, market_caps=caps, progress=progress
    )
    summary = build_artifacts(
        companies,
        generated_at=generated_at,
        out_dir=args.out_dir,
        levels=levels,
    )
    print(
        f"Written: {len(summary['written'])} group files, "
        f"skipped: {len(summary['skipped'])} (fewer than {MIN_GROUP_COMPANIES})"
    )
    for item in summary["written"]:
        print(
            f"  {item['level']:8s} {item['group']} "
            f"({item['company_count']} companies) -> {item['file']}"
        )
    print(f"Index: {summary['index']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
