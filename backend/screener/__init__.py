"""Screener layer: filter, rank, signal and opportunity detection.

Consumes only analytics/intelligence outputs and never calls providers.
"""

from backend.screener.filters import ScreenCriteria, from_kwargs, matches
from backend.screener.opportunity_engine import (
    best_opportunity,
    detect_opportunities,
)
from backend.screener.ranking_engine import rank_score, ranking_reasons
from backend.screener.screener_service import ScreenedCompany, ScreenerService
from backend.screener.signals import generate_signal

__all__ = [
    "ScreenCriteria",
    "ScreenedCompany",
    "ScreenerService",
    "best_opportunity",
    "detect_opportunities",
    "from_kwargs",
    "generate_signal",
    "matches",
    "rank_score",
    "ranking_reasons",
]
