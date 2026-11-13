"""Research-grade portfolio helpers: sizing, turnover, costs, rebalancing.

Pure functions (no DB, no network) so the backtest engine stays deterministic
and testable. Money is expressed as a fraction of portfolio value; ``cash`` is
implicit in the weights (``1 - sum(weights)``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

#: Tier budgets; re-scaled to the tiers actually present.
TIER_BUDGETS = {"STRONG_BUY": 0.60, "BUY": 0.30, "WEAK_BUY": 0.10}
CASH = "CASH"


def _cap(weights: dict[str, float], max_weight: float) -> dict[str, float]:
    """Iteratively cap every name at ``max_weight``, redistributing the excess.

    Redistribution goes pro-rata to names still below the cap. When the number
    of names times the cap is below 1, the remainder stays in cash (the
    weights sum to ``n * cap``), never silently leveraged.
    """
    capped = {ticker: float(weight) for ticker, weight in weights.items()}
    for _ in range(len(capped) + 1):
        over = [
            ticker for ticker, weight in capped.items() if weight > max_weight + 1e-12
        ]
        if not over:
            break
        excess = 0.0
        for ticker in over:
            excess += capped[ticker] - max_weight
            capped[ticker] = max_weight
        room = {
            ticker: max_weight - weight
            for ticker, weight in capped.items()
            if weight < max_weight - 1e-12
        }
        total_room = sum(room.values())
        if total_room <= 0:
            break
        for ticker, space in room.items():
            capped[ticker] += excess * (space / total_room)
    return {ticker: weight for ticker, weight in capped.items() if weight > 1e-12}


def target_weights(
    verdicts: dict[str, str],
    *,
    sizing: str = "tier",
    max_weight: float = 0.20,
) -> dict[str, float]:
    """Target weights for the positive verdicts.

    ``tier`` splits 60/30/10 by STRONG_BUY/BUY/WEAK_BUY, re-scaled to the tiers
    present (so a BUY-only set is 100% BUY) and split equally inside each tier.
    ``equal`` gives every selected name the same weight. In both cases the
    per-name cap is applied last; the unfilled remainder stays in cash.
    """
    positive = {
        ticker: verdict
        for ticker, verdict in verdicts.items()
        if verdict in TIER_BUDGETS
    }
    if not positive:
        return {}

    if sizing == "equal":
        raw = {ticker: 1.0 / len(positive) for ticker in positive}
    elif sizing == "tier":
        by_tier: dict[str, list[str]] = {}
        for ticker, verdict in positive.items():
            by_tier.setdefault(verdict, []).append(ticker)
        present = sum(TIER_BUDGETS[tier] for tier in by_tier)
        raw = {}
        for tier, tickers in by_tier.items():
            budget = TIER_BUDGETS[tier] / present
            for ticker in tickers:
                raw[ticker] = budget / len(tickers)
    else:
        raise ValueError(f"unknown sizing: {sizing}")

    return _cap(raw, max_weight)


def weights_with_cash(weights: dict[str, float]) -> dict[str, float]:
    """Append the implicit cash weight (never negative)."""
    invested = sum(weights.values())
    return {**weights, CASH: max(0.0, 1.0 - invested)}


def turnover(previous: dict[str, float], new: dict[str, float]) -> float:
    """One-way turnover between two weight vectors, including cash.

    ``0`` means the portfolio did not change; ``1`` means everything was
    replaced (building from cash counts as 1).
    """
    old = weights_with_cash(previous)
    current = weights_with_cash(new)
    keys = set(old) | set(current)
    return 0.5 * sum(abs(current.get(key, 0.0) - old.get(key, 0.0)) for key in keys)


@dataclass(frozen=True)
class CostBreakdown:
    """Cost of one rebalance, as a fraction of portfolio value."""

    turnover: float
    trades: int
    bps_cost: float
    fixed_cost: float

    @property
    def total(self) -> float:
        return self.bps_cost + self.fixed_cost


def rebalance_cost(
    previous: dict[str, float],
    new: dict[str, float],
    *,
    tc_bps: float = 10.0,
    tc_fixed: float = 0.0,
    capital: float = 100_000.0,
) -> CostBreakdown:
    """Transaction cost of moving ``previous`` -> ``new``.

    ``tc_bps`` is charged on one-way turnover (notional traded). ``tc_fixed``
    is a dollar commission per changed name, expressed as a fraction of the
    initial capital. Cash is not a trade.
    """
    traded = turnover(previous, new)
    names = set(previous) | set(new)
    trades = sum(
        1
        for name in names
        if name != CASH and abs(new.get(name, 0.0) - previous.get(name, 0.0)) > 1e-12
    )
    bps_cost = traded * max(0.0, float(tc_bps)) / 10_000.0
    fixed_cost = trades * max(0.0, float(tc_fixed)) / capital if capital > 0 else 0.0
    return CostBreakdown(
        turnover=traded,
        trades=trades,
        bps_cost=bps_cost,
        fixed_cost=fixed_cost,
    )


def drift(
    weights: dict[str, float], period_returns: dict[str, float]
) -> tuple[dict[str, float], float]:
    """Drift weights over one sub-period and return ``(weights, growth)``.

    Missing prices are treated as a 0% return (the position is marked flat),
    never as a sale. Cash earns 0%.
    """
    cash = max(0.0, 1.0 - sum(weights.values()))
    grown = {
        ticker: weight * (1.0 + float(period_returns.get(ticker, 0.0)))
        for ticker, weight in weights.items()
    }
    growth = sum(grown.values()) + cash
    if growth <= 0:
        return ({ticker: 0.0 for ticker in weights}, 0.0)
    return ({ticker: value / growth for ticker, value in grown.items()}, growth)


@dataclass
class PeriodSimulation:
    """Result of one holding period with intra-period rebalancing."""

    gross_return: float
    net_return: float
    cost: float = 0.0
    rebalances: int = 0
    turnover: float = 0.0


def quarter_ends(start: date, end: date) -> list[date]:
    """Quarter-end boundaries strictly inside ``(start, end]`` including end.

    The start is excluded (it is the period's first observation) and ``end`` is
    always included so the final boundary is exact.
    """
    boundaries: list[date] = []
    year, quarter = start.year, (start.month - 1) // 3 + 1
    while True:
        month = quarter * 3
        next_month = date(year + (month == 12), month % 12 + 1, 1)
        candidate = next_month - timedelta(days=1)
        if candidate > end:
            break
        if candidate > start:
            boundaries.append(candidate)
        quarter += 1
        if quarter > 4:
            quarter = 1
            year += 1
    if not boundaries or boundaries[-1] != end:
        boundaries.append(end)
    return boundaries


def simulate_holding_period(
    weights: dict[str, float],
    price_at: Callable[[str, date], float | None],
    boundaries: list[date],
    *,
    rebalance: str = "annual",
    threshold: float = 0.05,
    tc_bps: float = 10.0,
    tc_fixed: float = 0.0,
    capital: float = 100_000.0,
) -> PeriodSimulation:
    """Compound one holding period with intra-period rebalancing.

    ``price_at(ticker, date) -> float | None``. ``boundaries`` are the
    sub-period ends (``[start, b1, ..., end]`` is implicit: the first element
    is the first observation, not a return period). ``annual`` never
    rebalances inside the period; ``quarterly`` resets to the target at every
    boundary; ``threshold`` resets when any name drifts more than
    ``threshold`` from its target.
    """
    if not weights or not boundaries:
        return PeriodSimulation(gross_return=0.0, net_return=0.0)

    dates = boundaries
    current = dict(weights)
    target = dict(weights)
    value = 1.0
    gross_value = 1.0
    total_cost = 0.0
    total_turnover = 0.0
    rebalances = 0

    for index in range(1, len(dates)):
        previous_date, current_date = dates[index - 1], dates[index]
        period_returns: dict[str, float] = {}
        for ticker in current:
            start_price = price_at(ticker, previous_date)
            end_price = price_at(ticker, current_date)
            if start_price and end_price and start_price > 0:
                period_returns[ticker] = end_price / start_price - 1.0
        current, growth = drift(current, period_returns)
        gross_value *= growth
        value *= growth
        if index == len(dates) - 1:
            break

        should_rebalance = rebalance == "quarterly"
        if rebalance == "threshold":
            drifted = max(
                (abs(current.get(ticker, 0.0) - target[ticker]) for ticker in target),
                default=0.0,
            )
            should_rebalance = drifted > threshold
        if not should_rebalance:
            continue
        cost = rebalance_cost(
            current,
            target,
            tc_bps=tc_bps,
            tc_fixed=tc_fixed,
            capital=capital,
        )
        if cost.total > 0:
            value *= 1.0 - cost.total
            total_cost += cost.total
            total_turnover += cost.turnover
            rebalances += 1
        current = dict(target)

    gross_return = gross_value - 1.0
    return PeriodSimulation(
        gross_return=gross_return,
        net_return=value - 1.0,
        cost=total_cost,
        rebalances=rebalances,
        turnover=total_turnover,
    )
