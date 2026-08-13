"""Intelligence layer: Buffett-style investment decision support.

Transforms normalized financials into interpretable, deterministic
scoring (Buffett filter, moat detection, composite rating) without any
dependency on data providers.
"""

from backend.intelligence.buffett_engine import buffett_filter
from backend.intelligence.moat_analysis import analyze_moat, classify_moat
from backend.intelligence.quality_metrics import compute_quality_metrics
from backend.intelligence.scoring_model import assess_investment, composite_score

__all__ = [
    "assess_investment",
    "buffett_filter",
    "analyze_moat",
    "classify_moat",
    "compute_quality_metrics",
    "composite_score",
]
