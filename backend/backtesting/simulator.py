"""Deterministic portfolio simulator over yearly snapshots.

Every snapshot carries the analysis results (used for selection) and
the prices at period start/end (used for returns). The portfolio is
rebalanced every ``rebalance_every`` snapshots into an equal-weighted
selection, and returns compound into an equity curve.
"""

from typing import Optional

from backend.backtesting.strategy import Strategy

RISK_FREE_RATE = 0.0


def _period_return(snapshot: dict, selected: list[str]) -> float:
    """Equal-weighted return of ``selected`` within one snapshot."""
    value = 0.0
    count = 0
    for ticker in selected:
        prices = snapshot.get("prices") or {}
        pair = prices.get(ticker)
        if not pair or pair[0] is None or pair[1] is None or pair[0] == 0:
            continue
        value += pair[1] / pair[0] - 1.0
        count += 1
    if count == 0:
        return 0.0
    return value / count


def equity_curve(
    snapshots: list[dict], strategy: Strategy, top_n: int, rebalance_every: int
) -> list[float]:
    """Compounded portfolio value per snapshot, starting at 1.0."""
    curve: list[float] = [1.0]
    value = 1.0
    for index, snapshot in enumerate(snapshots):
        if index % max(rebalance_every, 1) == 0:
            analyses = snapshot.get("analyses") or {}
            selected = strategy(analyses, top_n)
        snapshot["_selected"] = selected
        value *= 1.0 + _period_return(snapshot, selected)
        curve.append(value)
    return curve


def cagr(curve: list[float]) -> Optional[float]:
    if len(curve) < 2 or curve[0] <= 0:
        return None
    periods = len(curve) - 1
    return (curve[-1] / curve[0]) ** (1.0 / periods) - 1.0


def _period_returns(curve: list[float]) -> list[float]:
    return [curve[i] / curve[i - 1] - 1.0 for i in range(1, len(curve))]


def max_drawdown(curve: list[float]) -> float:
    peak = curve[0] if curve else 0.0
    worst = 0.0
    for value in curve:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst


def sharpe(returns: list[float], risk_free: float = RISK_FREE_RATE) -> Optional[float]:
    """Annualized Sharpe from per-period returns."""
    if len(returns) < 2:
        return None
    excess = [r - risk_free for r in returns]
    mean = sum(excess) / len(excess)
    variance = sum((e - mean) ** 2 for e in excess) / len(excess)
    if variance == 0:
        return None
    return mean / (variance**0.5)


def win_rate(returns: list[float]) -> Optional[float]:
    if not returns:
        return None
    return sum(1 for r in returns if r > 0) / len(returns)


def simulate(
    snapshots: list[dict],
    strategy: Strategy,
    top_n: int = 5,
    rebalance_every: int = 1,
) -> dict:
    """Full backtest: equity curve plus headline metrics."""
    curve = equity_curve(snapshots, strategy, top_n, rebalance_every)
    returns = _period_returns(curve)
    return {
        "periods": len(snapshots),
        "equity_curve": [round(v, 6) for v in curve],
        "cagr": cagr(curve),
        "max_drawdown": round(max_drawdown(curve), 6),
        "sharpe": sharpe(returns),
        "win_rate": win_rate(returns),
        "selected_first_period": snapshots[0].get("_selected", []) if snapshots else [],
    }
