"""Backtesting engine: turns historical analyses into performance metrics."""

from typing import Callable, Optional

from backend.backtesting.simulator import simulate
from backend.backtesting.strategy import Strategy

RebalanceHook = Callable[[list[dict], str], None]


def run_backtest(
    snapshots: list[dict],
    strategy: Strategy,
    top_n: int = 5,
    rebalance_every: int = 1,
) -> dict:
    """Execute the backtest and return headline metrics."""
    if not snapshots:
        raise ValueError("no snapshots to backtest")
    result = simulate(snapshots, strategy, top_n, rebalance_every)
    result["strategy"] = getattr(strategy, "__name__", "custom")
    result["top_n"] = top_n
    result["rebalance_every"] = rebalance_every
    return result


def snapshot_year(snapshot: dict) -> Optional[int]:
    return snapshot.get("year")


def sort_snapshots(snapshots: list[dict]) -> list[dict]:
    return sorted(
        snapshots,
        key=lambda s: (snapshot_year(s) is not None, snapshot_year(s) or 0),
    )
