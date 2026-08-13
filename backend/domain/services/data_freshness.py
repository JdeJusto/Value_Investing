"""Data freshness policy (pure domain, no storage or network)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.domain.value_objects.financials_normalized import NormalizedFinancials

# A record older than this is considered stale regardless of quality.
STALE_AFTER_DAYS = 90
# A record with a quality score below this is considered stale regardless of age.
MIN_QUALITY_SCORE = 0.7


def is_stale(financials: NormalizedFinancials) -> bool:
    """A record needs refresh when it is too old OR its quality is too low."""
    if financials.loaded_at is None:
        return True

    stale_by_age = financials.loaded_at < datetime.now(timezone.utc) - timedelta(
        days=STALE_AFTER_DAYS
    )
    stale_by_quality = (
        financials.data_quality_score is not None
        and financials.data_quality_score < MIN_QUALITY_SCORE
    )
    return stale_by_age or stale_by_quality


def needs_refresh(financials: list[NormalizedFinancials]) -> bool:
    """True when any record in the history requires a refresh.

    An empty history always requires a refresh (there is nothing to analyze).
    """
    if not financials:
        return True
    return any(is_stale(record) for record in financials)


def days_since_loaded(financials: NormalizedFinancials) -> Optional[int]:
    """Age in days of a record, None when no load timestamp is stored."""
    if financials.loaded_at is None:
        return None
    return (datetime.now(timezone.utc) - financials.loaded_at).days
