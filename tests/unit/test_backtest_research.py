"""Research-grade backtest: sizing, costs, rebalancing and PIT plumbing."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from backend.backtesting.research import (
    drift,
    quarter_ends,
    rebalance_cost,
    simulate_holding_period,
    target_weights,
    turnover,
)
from backend.methodologies.base import Confidence, MethodologyResult, Verdict
from backend.services.methodology_backtest_service import MethodologyBacktestService


# ---------------------------------------------------------------------------
# Sizing and cap
# ---------------------------------------------------------------------------
def test_tier_weights_split_within_tier_and_rescale_present_tiers():
    weights = target_weights({"A": "BUY", "B": "BUY", "C": "WEAK_BUY"}, max_weight=1.0)
    assert weights["A"] == pytest.approx(0.375)
    assert weights["B"] == pytest.approx(0.375)
    assert weights["C"] == pytest.approx(0.25)


def test_cap_redistributes_or_leaves_cash_when_too_few_names():
    five = target_weights({ticker: "STRONG_BUY" for ticker in "ABCDE"})
    assert sum(five.values()) == pytest.approx(1.0)
    assert max(five.values()) == pytest.approx(0.20)

    three = target_weights({ticker: "STRONG_BUY" for ticker in "ABC"})
    assert sum(three.values()) == pytest.approx(0.60)
    assert max(three.values()) == pytest.approx(0.20)


def test_equal_sizing_ignores_tiers():
    weights = target_weights(
        {"A": "STRONG_BUY", "B": "WEAK_BUY"}, sizing="equal", max_weight=1.0
    )
    assert weights == pytest.approx({"A": 0.5, "B": 0.5})


def test_non_positive_verdicts_are_not_held():
    assert target_weights({"A": "WATCH", "B": "AVOID"}) == {}


# ---------------------------------------------------------------------------
# Turnover and costs
# ---------------------------------------------------------------------------
def test_turnover_counts_build_from_cash_as_full_replacement():
    assert turnover({}, {"A": 0.5, "B": 0.5}) == pytest.approx(1.0)


def test_turnover_is_zero_when_weights_do_not_change():
    weights = {"A": 0.5, "B": 0.5}
    assert turnover(weights, weights) == pytest.approx(0.0)


def test_rebalance_cost_combines_bps_and_fixed():
    cost = rebalance_cost(
        {},
        {"A": 0.5, "B": 0.5},
        tc_bps=10.0,
        tc_fixed=5.0,
        capital=100_000.0,
    )
    assert cost.turnover == pytest.approx(1.0)
    assert cost.trades == 2
    assert cost.bps_cost == pytest.approx(0.001)
    assert cost.fixed_cost == pytest.approx(0.0001)
    assert cost.total == pytest.approx(0.0011)


def test_drift_reweights_winners_and_preserves_growth():
    weights, growth = drift({"A": 0.5, "B": 0.5}, {"A": 1.0, "B": 0.0})
    assert growth == pytest.approx(1.5)
    assert weights["A"] == pytest.approx(2 / 3)
    assert weights["B"] == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# Rebalancing
# ---------------------------------------------------------------------------
def test_quarter_ends_cover_every_quarter_and_the_end_date():
    boundaries = quarter_ends(date(2024, 2, 14), date(2025, 2, 14))
    assert boundaries == [
        date(2024, 3, 31),
        date(2024, 6, 30),
        date(2024, 9, 30),
        date(2024, 12, 31),
        date(2025, 2, 14),
    ]


def test_annual_holding_period_never_rebalances():
    prices = {
        ("A", date(2024, 1, 1)): 100.0,
        ("A", date(2025, 1, 1)): 200.0,
        ("B", date(2024, 1, 1)): 100.0,
        ("B", date(2025, 1, 1)): 100.0,
    }
    result = simulate_holding_period(
        {"A": 0.5, "B": 0.5},
        lambda ticker, when: prices.get((ticker, when)),
        [date(2024, 1, 1), date(2025, 1, 1)],
        rebalance="annual",
    )
    assert result.gross_return == pytest.approx(0.5)
    assert result.net_return == pytest.approx(0.5)
    assert result.rebalances == 0


def test_threshold_rebalances_after_a_large_drift():
    prices = {}
    for ticker in ("A", "B"):
        prices[(ticker, date(2024, 1, 1))] = 100.0
    prices[("A", date(2024, 3, 31))] = 200.0
    prices[("B", date(2024, 3, 31))] = 100.0
    prices[("A", date(2025, 1, 1))] = 220.0
    prices[("B", date(2025, 1, 1))] = 100.0
    result = simulate_holding_period(
        {"A": 0.5, "B": 0.5},
        lambda ticker, when: prices.get((ticker, when)),
        [date(2024, 1, 1), date(2024, 3, 31), date(2025, 1, 1)],
        rebalance="threshold",
        threshold=0.05,
        tc_bps=10.0,
    )
    assert result.rebalances == 1
    assert result.cost > 0
    assert result.net_return < result.gross_return


# ---------------------------------------------------------------------------
# Service wiring
# ---------------------------------------------------------------------------
class _PitRepo:
    def __init__(self, years=(2020, 2021, 2022, 2023), universe=("A", "B")):
        self.rows = [
            SimpleNamespace(
                fiscal_year=year,
                shares_outstanding=1_000,
                split_adjustment_factor=1.0,
            )
            for year in years
        ]
        self.universe = list(universe)
        self.queries: list[tuple[str, date]] = []

    def historical_universe_available(self):
        return True

    def get_sp500_universe(self, as_of):
        return list(self.universe)

    def list_years_pit(self, ticker, as_of, max_years=None):
        self.queries.append((ticker, as_of))
        return [row for row in self.rows if row.fiscal_year < as_of.year]


class _PitPrices:
    def __init__(self, series):
        self.series = series
        self.calls: list[tuple[str, date]] = []

    def get_price_on_date(self, ticker, when):
        self.calls.append((ticker, when))
        return self.series.get((ticker, when))


class _BuyMethod:
    def rules(self):
        return [SimpleNamespace(id="fake.rule", name="Fake rule")]

    def evaluate(self, ticker, rows, prices):
        return MethodologyResult(
            methodology="fake",
            version="1.0",
            family="TEST",
            verdict=Verdict.BUY,
            score=90.0,
            metrics={},
            reasons=[],
            red_flags=[],
            confidence=Confidence.HIGH,
            sources=[],
            passed_rules=[],
            failed_rules=[],
        )


class _Registry:
    def list(self):
        return ["fake"]

    def get(self, name):
        return _BuyMethod() if name == "fake" else None


def _pit_prices():
    return {
        ("A", date(2023, 2, 14)): 100.0,
        ("A", date(2024, 2, 14)): 120.0,
        ("A", date(2025, 2, 14)): 150.0,
        ("A", date(2026, 2, 14)): 180.0,
        ("B", date(2023, 2, 14)): 100.0,
        ("B", date(2024, 2, 14)): 110.0,
        ("B", date(2025, 2, 14)): 130.0,
        ("B", date(2026, 2, 14)): 143.0,
    }


def test_research_run_uses_pit_universe_cost_and_cap():
    repo = _PitRepo()
    prices = _PitPrices(_pit_prices())
    service = MethodologyBacktestService(
        repository=repo, price_service=prices, methodology_registry=_Registry()
    )
    result = service.run(
        [],
        "fake",
        years=2,
        research_grade=True,
        today=date(2026, 11, 13),
        max_weight=0.20,
        tc_bps=10.0,
    )
    assert result.research_grade
    assert result.years == (2023, 2024)
    assert result.pit_coverage == pytest.approx(1.0)
    # Two names, cap 20% -> 40% invested, 60% cash.
    assert result.per_year[0].buys == 2
    assert result.per_year[0].turnover == pytest.approx(0.4)
    gross = 0.2 * 0.25 + 0.2 * (130.0 / 110.0 - 1.0)
    assert result.per_year[0].portfolio_return == pytest.approx(
        (1.0 + gross) * (1.0 - 0.4 * 10.0 / 10_000.0) - 1.0
    )
    assert result.per_year[1].portfolio_return == pytest.approx(0.2 * 0.20 + 0.2 * 0.10)
    assert result.snapshot_out["A"][date(2024, 2, 14).isoformat()] == 120.0


def test_research_snapshot_replay_never_calls_the_network():
    repo = _PitRepo()
    first = MethodologyBacktestService(
        repository=repo,
        price_service=_PitPrices(_pit_prices()),
        methodology_registry=_Registry(),
    ).run([], "fake", years=2, research_grade=True, today=date(2026, 11, 13))

    class _ForbiddenPrices:
        def get_price_on_date(self, ticker, when):
            raise AssertionError("snapshot replay must not fetch prices")

    replay = MethodologyBacktestService(
        repository=_PitRepo(),
        price_service=_ForbiddenPrices(),
        methodology_registry=_Registry(),
    ).run(
        [],
        "fake",
        years=2,
        research_grade=True,
        today=date(2026, 11, 13),
        price_snapshot=first.snapshot_out,
    )
    assert replay.annualized_return == pytest.approx(first.annualized_return)
    assert replay.per_year[0].portfolio_return == pytest.approx(
        first.per_year[0].portfolio_return
    )


def test_research_rejects_repositories_without_pit_support():
    class _LegacyRepo:
        pass

    service = MethodologyBacktestService(
        repository=_LegacyRepo(), methodology_registry=_Registry()
    )
    with pytest.raises(ValueError, match="Financial-DataBase 0.4.0"):
        service.run([], "fake", years=2, research_grade=True)
