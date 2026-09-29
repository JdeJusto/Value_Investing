"""Backtesting package: strategies, simulator and engine."""

from backend.backtesting.engine import (
    run_backtest,
    snapshot_year,
    sort_snapshots,
)
from backend.backtesting.strategy import (
    STRATEGIES,
    buffett_strategy,
    fundamental_momentum_scores,
    get_strategy,
    momentum_strategy,
)

__all__ = [
    "STRATEGIES",
    "buffett_strategy",
    "fundamental_momentum_scores",
    "get_strategy",
    "momentum_strategy",
    "run_backtest",
    "snapshot_year",
    "sort_snapshots",
]
