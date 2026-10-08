"""Consensus endpoints — snapshot, ranking, by-category, disagreement.

All four routes read the consensus JSON computed by
``scripts.compute_consensus_rankings`` through :class:`ConsensusService`;
nothing is recomputed here. A snapshot older than
:data:`~backend.services.consensus_service.STALE_AFTER_DAYS` is served with
a ``meta.warning`` instead of being hidden.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends

from backend.api.auth import require_api_key
from backend.api.deps import get_consensus_service
from backend.api.responses import ApiError, ok
from backend.services.consensus_service import (
    STALE_AFTER_DAYS,
    CompanyConsensus,
    ConsensusReport,
    ConsensusService,
)

router = APIRouter(prefix="/api/v1", tags=["consensus"])

CACHE_TTL_SECONDS = 3600
MAX_TOP = 100
MAX_PER_CATEGORY = 100
VALID_SORTS = ("score", "buys", "avoids")

_RECOMPUTE_HINT = (
    "run: python -m scripts.compute_consensus_rankings --universe <universe>"
)


def _load_report(service: ConsensusService, date_str: str | None) -> ConsensusReport:
    """Latest (or dated) consensus snapshot, or the standard 503."""
    if date_str:
        report = service.load_by_date(date_str)
        message = (
            f"No consensus snapshot for {date_str}. "
            f"Available snapshots live in the consensus data directory; {_RECOMPUTE_HINT}."
        )
    else:
        report = service.load_latest()
        message = f"No consensus snapshot found. {_RECOMPUTE_HINT}."
    if report is None:
        raise ApiError(503, "CONSENSUS_NOT_AVAILABLE", message)
    return report


def _stale_warning(report: ConsensusReport) -> str | None:
    """Message when the snapshot is older than the staleness threshold."""
    try:
        report_date = date.fromisoformat(report.date)
    except ValueError:
        return f"Consensus snapshot has an invalid date: {report.date!r}"
    age = (datetime.now(UTC).date() - report_date).days
    if age > STALE_AFTER_DAYS:
        return (
            f"Consensus snapshot is {age} days old (computed {report.date}); "
            f"{_RECOMPUTE_HINT}."
        )
    return None


def _envelope(data: dict, report: ConsensusReport) -> dict:
    payload = ok(data, source="consensus_json", cache_ttl=CACHE_TTL_SECONDS)
    warning = _stale_warning(report)
    if warning:
        payload["meta"]["warning"] = warning
    return payload


def _company_payload(company: CompanyConsensus) -> dict[str, Any]:
    """One CompanyConsensus as JSON-safe primitives."""
    return {
        "ticker": company.ticker,
        "name": company.name,
        "category": company.lynch_category,
        "consensus_score": company.consensus_score,
        "buy_count": company.buy_count,
        "avoid_count": company.avoid_count,
        "insufficient_count": company.insufficient_count,
        "na_count": company.na_count,
        "price": company.price,
        "verdicts": dict(company.verdicts),
        "verdict_string": "/".join(company.verdicts.values()),
    }


def _buy_distribution(report: ConsensusReport) -> dict[str, int]:
    """Companies per BUY count, bucketed ``0``..``3`` and ``4+``."""
    buckets = {str(n): 0 for n in range(4)}
    buckets["4+"] = 0
    for company in report.companies:
        key = str(company.buy_count) if company.buy_count <= 3 else "4+"
        buckets[key] += 1
    return buckets


@router.get("/consensus", dependencies=[Depends(require_api_key)])
def get_consensus(
    date: str | None = None,
    service: ConsensusService = Depends(get_consensus_service),
) -> dict[str, Any]:
    """Latest consensus snapshot summary (or a specific ``?date=YYYY-MM-DD``).

    ``na_count`` counts companies where every methodology abstained by design
    (financial companies); those are excluded from the rankings.
    """
    report = _load_report(service, date)
    data = {
        "date": report.date,
        "universe": report.universe,
        "version": report.version,
        "count": len(report.companies),
        "prices_available": report.prices_available,
        "na_count": sum(1 for c in report.companies if c.is_not_applicable),
        "buy_distribution": _buy_distribution(report),
        "categories": _category_counts(report),
    }
    return _envelope(data, report)


def _category_counts(report: ConsensusReport) -> dict[str, int]:
    counts: dict[str, int] = {}
    for company in report.companies:
        counts[company.lynch_category] = counts.get(company.lynch_category, 0) + 1
    return counts


@router.get("/consensus/ranking", dependencies=[Depends(require_api_key)])
def get_ranking(
    date: str | None = None,
    top: int = 20,
    by: str = "score",
    service: ConsensusService = Depends(get_consensus_service),
) -> dict[str, Any]:
    """Top-N rankable companies by ``score``, ``buys`` or ``avoids``.

    ``buys`` is the canonical consensus ranking (most BUYs first, then
    score); ``score`` sorts by the stored consensus score; ``avoids``
    surfaces the strongest AVOID camps. ``top`` is capped at
    :data:`MAX_TOP`; companies with no real verdict (data holes, all-N/A)
    are excluded by the service.
    """
    sort_key = (by or "").strip().lower()
    if sort_key not in VALID_SORTS:
        raise ApiError(
            400,
            "INVALID_SORT",
            f"Unknown sort {by!r}. Valid: {', '.join(VALID_SORTS)}.",
        )
    if top < 1:
        raise ApiError(400, "INVALID_FILTER", "top must be >= 1")
    effective_top = min(top, MAX_TOP)

    report = _load_report(service, date)
    if sort_key == "buys":
        companies = service.top_by_consensus(effective_top)
    else:
        all_ranked = service.top_by_consensus(len(report.companies))
        if sort_key == "score":
            all_ranked.sort(key=lambda c: (-c.consensus_score, -c.buy_count, c.ticker))
        else:  # avoids
            all_ranked.sort(key=lambda c: (-c.avoid_count, -c.buy_count, c.ticker))
        companies = all_ranked[:effective_top]

    data = {
        "date": report.date,
        "universe": report.universe,
        "by": sort_key,
        "top": effective_top,
        "rows": [_company_payload(c) for c in companies],
    }
    return _envelope(data, report)


@router.get("/consensus/by-category", dependencies=[Depends(require_api_key)])
def get_by_category(
    date: str | None = None,
    per_category: int = 5,
    service: ConsensusService = Depends(get_consensus_service),
) -> dict[str, Any]:
    """Top ``per_category`` companies for each of the six Lynch buckets."""
    if per_category < 1:
        raise ApiError(400, "INVALID_FILTER", "per_category must be >= 1")
    effective = min(per_category, MAX_PER_CATEGORY)

    report = _load_report(service, date)
    groups = service.best_per_lynch_category(effective)
    data = {
        "date": report.date,
        "universe": report.universe,
        "per_category": effective,
        "categories": {
            category: [_company_payload(c) for c in companies]
            for category, companies in groups.items()
        },
    }
    return _envelope(data, report)


@router.get("/consensus/disagreement", dependencies=[Depends(require_api_key)])
def get_disagreement(
    date: str | None = None,
    min_buy: int = 3,
    max_buy: int = 4,
    service: ConsensusService = Depends(get_consensus_service),
) -> dict[str, Any]:
    """Companies in the disagreement zone: a strong BUY camp and a strong
    AVOID camp at once.

    The BUY camp is the ``min_buy..max_buy`` range; the avoid side uses the
    consensus service's own definition (3..5 AVOID verdicts), so the result
    is exactly ``ConsensusService.disagreement_zone``.
    """
    if min_buy < 0 or max_buy < min_buy:
        raise ApiError(
            400,
            "INVALID_FILTER",
            "min_buy must be >= 0 and max_buy >= min_buy",
        )
    report = _load_report(service, date)
    companies = service.disagreement_zone(min_buy=min_buy, max_buy=max_buy)
    data = {
        "date": report.date,
        "universe": report.universe,
        "min_buy": min_buy,
        "max_buy": max_buy,
        "count": len(companies),
        "rows": [_company_payload(c) for c in companies],
    }
    return _envelope(data, report)
