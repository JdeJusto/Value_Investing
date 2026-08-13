"""Data completeness and quality scoring for normalized records.

Purely functional helpers used by the normalizers and the repository
selection logic. No I/O, no providers.
"""

from __future__ import annotations

from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
)

# Fields any usable annual record must expose to power core valuation.
REQUIRED_FIELDS: tuple[str, ...] = (
    "revenue",
    "net_income",
    "total_assets",
    "shares_outstanding",
)

# Metrics that make a record materially better when present.
DERIVED_METRICS: tuple[str, ...] = ("free_cash_flow", "ebitda")

# Provider reliability: how trustworthy the source itself is.
SOURCE_RELIABILITY: dict[ProviderName, float] = {
    ProviderName.YAHOO: 1.0,
    ProviderName.EDGAR: 0.8,
}

# Provider preference for source selection (higher wins).
SOURCE_PRIORITY: dict[ProviderName, int] = {
    ProviderName.YAHOO: 2,
    ProviderName.EDGAR: 1,
}

# Score composition weights.
WEIGHT_COMPLETENESS = 0.5
WEIGHT_RELIABILITY = 0.3
WEIGHT_DERIVED = 0.2


def compute_completeness(financials: NormalizedFinancials) -> float:
    """Fraction of required fields actually present in the record (0-1)."""
    if not financials:
        return 0.0
    present = sum(
        1 for fname in REQUIRED_FIELDS if getattr(financials, fname, None) is not None
    )
    return present / len(REQUIRED_FIELDS)


def compute_quality_score(financials: NormalizedFinancials) -> float:
    """Overall quality in [0, 1]: completeness + source reliability + derived metrics."""
    completeness = compute_completeness(financials)
    reliability = SOURCE_RELIABILITY.get(financials.source, 0.5)
    derived_presence = sum(
        1 for m in DERIVED_METRICS if getattr(financials, m, None) is not None
    ) / len(DERIVED_METRICS)
    return round(
        WEIGHT_COMPLETENESS * completeness
        + WEIGHT_RELIABILITY * reliability
        + WEIGHT_DERIVED * derived_presence,
        4,
    )


def apply_quality_metrics(financials: NormalizedFinancials) -> NormalizedFinancials:
    """Populate the quality fields of a record in place."""
    financials.data_completeness = round(compute_completeness(financials), 4)
    financials.is_complete = financials.data_completeness == 1.0
    financials.data_source_priority = SOURCE_PRIORITY.get(financials.source, 0)
    financials.data_quality_score = compute_quality_score(financials)
    return financials
