"""Flexible screening criteria applied to analytics/intelligence outputs.

A result to be screened is the dict produced by
``CompanyAnalysisService.analyze`` (optionally enriched with sector and
industry by the caller). Filters never touch providers.
"""

from dataclasses import dataclass, field
from typing import Optional

MOAT_TYPES = ("STRONG", "MODERATE", "WEAK", "NONE")


@dataclass(frozen=True)
class ScreenCriteria:
    """All documented filters. None means "no restriction"."""

    min_market_cap: Optional[float] = None
    max_market_cap: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    min_revenue_growth: Optional[float] = None
    min_roic: Optional[float] = None
    max_debt_ratio: Optional[float] = None
    min_buffett_score: Optional[float] = None
    min_moat_score: Optional[float] = None
    moat: Optional[str] = None
    min_total_score: Optional[float] = None
    min_margin_of_safety: Optional[float] = None
    confidence: Optional[str] = None
    tickers: set[str] = field(default_factory=set)


def _moat_type_of(item: dict) -> str:
    return (item.get("moat_analysis") or {}).get("moat_type", "NONE")


def matches(item: dict, criteria: ScreenCriteria) -> bool:
    """True when the analysis result satisfies every active filter."""
    if criteria.min_market_cap is not None:
        cap = item.get("market_cap")
        if cap is None or cap < criteria.min_market_cap:
            return False
    if criteria.max_market_cap is not None:
        cap = item.get("market_cap")
        if cap is None or cap > criteria.max_market_cap:
            return False

    if criteria.sector and item.get("sector") != criteria.sector:
        return False
    if criteria.industry and item.get("industry") != criteria.industry:
        return False

    if criteria.min_revenue_growth is not None:
        growth = (item.get("quality_metrics") or {}).get("revenue_cagr")
        if growth is None or growth < criteria.min_revenue_growth:
            return False

    if criteria.min_roic is not None:
        roic = (item.get("quality_metrics") or {}).get("roic_mean")
        if roic is None or roic < criteria.min_roic:
            return False

    if criteria.max_debt_ratio is not None:
        debt = (item.get("quality_metrics") or {}).get("debt_to_equity")
        if debt is None or debt > criteria.max_debt_ratio:
            return False

    if criteria.min_buffett_score is not None:
        buffett = item.get("buffett_score")
        if buffett is None or buffett < criteria.min_buffett_score:
            return False

    if criteria.min_moat_score is not None:
        moat_score = (item.get("moat_analysis") or {}).get("moat_score")
        if moat_score is None or moat_score < criteria.min_moat_score:
            return False

    if criteria.moat is not None:
        desired = criteria.moat.upper()
        if desired not in MOAT_TYPES:
            return False
        rank = MOAT_TYPES.index(desired)
        actual = MOAT_TYPES.index(_moat_type_of(item))
        if actual > rank:
            return False

    if criteria.min_total_score is not None:
        total = (item.get("composite_score") or {}).get("total_score")
        if total is None or total < criteria.min_total_score:
            return False

    if criteria.min_margin_of_safety is not None:
        margin = item.get("dcf_margin_of_safety")
        if margin is None or margin < criteria.min_margin_of_safety:
            return False

    if criteria.confidence is not None:
        confidence = (item.get("composite_score") or {}).get("confidence")
        levels = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
        want = levels.get(criteria.confidence.upper(), 0)
        if confidence is None or levels.get(confidence, 0) < want:
            return False

    if criteria.tickers and item.get("ticker") not in criteria.tickers:
        return False

    return True


def from_kwargs(**kwargs) -> ScreenCriteria:
    """Build criteria from caller keywords (e.g. moat='STRONG', min_score=80)."""
    aliases = {"min_score": "min_total_score", "max_debt": "max_debt_ratio"}
    filtered = {}
    for key, value in kwargs.items():
        key = aliases.get(key, key)
        if key in ScreenCriteria.__dataclass_fields__ and value is not None:
            filtered[key] = value
    return ScreenCriteria(**filtered)
