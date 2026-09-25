"""Source selection logic shared by repository implementations.

Prefer a single, consistent source per company; blend only when no source
covers enough history (consumers flag the result as MIXED / LOW
confidence).
"""

from __future__ import annotations

from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
)
from backend.providers.normalizers.quality import SOURCE_PRIORITY

# A single source covering at least this share of the stored years is used as-is.
FULL_COVERAGE_THRESHOLD = 0.8

# Rows below this quality are empty shells (no usable fundamentals);
# they must never count towards a source's coverage.
USABLE_QUALITY_THRESHOLD = 0.5


def _usable(record: NormalizedFinancials) -> bool:
    quality = record.data_quality_score
    if quality is not None:
        return quality >= USABLE_QUALITY_THRESHOLD
    # Rows without a score (hand-built records) must still carry core
    # fundamentals to count towards a source's coverage; an unscored empty
    # shell is not usable data, only a placeholder row.
    return record.revenue is not None or record.net_income is not None


def record_rank(record: NormalizedFinancials) -> tuple:
    """Higher is better: source priority first, then quality score."""
    return (
        record.data_source_priority or SOURCE_PRIORITY.get(record.source, 0),
        record.data_quality_score if record.data_quality_score is not None else -1,
    )


def best_of(records: list[NormalizedFinancials]) -> NormalizedFinancials:
    return max(records, key=record_rank)


def best_per_year(records: list[NormalizedFinancials]) -> list[NormalizedFinancials]:
    """Best record for each year (no blending within a year), year desc."""
    by_year: dict[int, list[NormalizedFinancials]] = {}
    for record in records:
        by_year.setdefault(record.fiscal_year, []).append(record)
    selected = [best_of(rows) for rows in by_year.values()]
    selected.sort(key=lambda r: r.fiscal_year, reverse=True)
    return selected


def choose_history(rows: list[NormalizedFinancials]) -> list[NormalizedFinancials]:
    """Pick the most consistent usable history from all stored records."""
    if not rows:
        return []
    total_years = len({r.fiscal_year for r in rows})
    by_source: dict[str, list[NormalizedFinancials]] = {}
    for record in rows:
        by_source.setdefault(record.source.value, []).append(record)

    ranked: list[tuple] = []
    for source, yearly in by_source.items():
        usable = [r for r in yearly if _usable(r)]
        coverage = len(usable) / total_years
        mean_quality = (
            sum(
                r.data_quality_score if r.data_quality_score is not None else 0.0
                for r in usable
            )
            / len(usable)
            if usable
            else 0.0
        )
        priority = max(
            (r.data_source_priority for r in yearly),
            default=SOURCE_PRIORITY.get(ProviderName(source), 0),
        )
        ranked.append((priority, coverage, mean_quality, source, usable))

    ranked.sort(
        key=lambda t: (t[1] >= FULL_COVERAGE_THRESHOLD, t[0], t[1], t[2]), reverse=True
    )
    _, best_coverage, _, _, best_yearly = ranked[0]

    if best_coverage >= FULL_COVERAGE_THRESHOLD:
        return sorted(best_yearly, key=lambda r: r.fiscal_year, reverse=True)

    # No single source covers enough history: blend the best usable
    # record per year and drop the empty shells entirely.
    usable = [r for r in rows if _usable(r)]
    if not usable:
        return []
    return best_per_year(usable)
