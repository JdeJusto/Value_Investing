import math

from backend.backtesting import (
    buffett_strategy,
    fundamental_momentum_scores,
    get_strategy,
    momentum_strategy,
    run_backtest,
    sort_snapshots,
)
from backend.backtesting.simulator import (
    cagr,
    equity_curve,
    max_drawdown,
    sharpe,
    win_rate,
)
from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.intelligence.delta_metrics import compute_delta_metrics


def _build_rows(records):
    return [
        NormalizedFinancials(
            ticker="AAA",
            source="yahoo",
            currency="USD",
            period="FY",
            fiscal_year=record.get("fiscal_year"),
            revenue=record.get("revenue"),
            net_income=record.get("net_income"),
            gross_profit=record.get("gross_profit"),
            operating_income=record.get("operating_income"),
            ebitda=record.get("ebitda"),
            ebit=record.get("ebitda"),
            pretax_income=record.get("pretax_income"),
            tax_provision=record.get("tax_provision"),
            interest_expense=record.get("interest_expense", 0.0),
            total_assets=record.get("total_assets"),
            total_liabilities=record.get("total_liabilities"),
            total_debt=record.get("total_debt"),
            stockholders_equity=record.get("stockholders_equity"),
            operating_cash_flow=record.get("operating_cash_flow"),
            capital_expenditure=record.get("capital_expenditure"),
            free_cash_flow=record.get("free_cash_flow"),
            shares_outstanding=record.get("shares_outstanding"),
            is_complete=record.get("is_complete", True),
        )
        for record in records
    ]


def make_rows(years, base_revenue, growths):
    rows = []
    revenue = base_revenue
    for index, year in enumerate(years):
        rows.append(
            {
                "ticker": "AAA",
                "fiscal_year": year,
                "revenue": revenue,
                "net_income": 100.0,
                "operating_income": 120.0,
                "ebitda": 130.0,
                "gross_profit": 180.0,
                "free_cash_flow": 60.0,
                "operating_cash_flow": 90.0,
                "total_debt": 50.0,
                "stockholders_equity": 500.0,
                "total_assets": 1000.0,
                "capital_expenditure": 30.0,
                "pretax_income": 110.0,
                "tax_provision": 10.0,
                "shares_outstanding": 100.0,
                "is_complete": True,
            }
        )
        if index + 1 < len(years):
            revenue *= 1.0 + growths[index]
    return _build_rows(rows)


def make_analysis(rows):
    deltas = compute_delta_metrics(rows)
    return {"delta_metrics": deltas, "rank_score": 80.0, "composite": 0.85}


def make_snapshot(years, base_revenue, growths, start, end):
    rows = make_rows(years, base_revenue, growths)
    return {
        "year": years[-1],
        "analyses": {"AAA": make_analysis(rows)},
        "prices": {"AAA": (start, end)},
    }


class TestFundamentalMomentum:
    def test_formula_weights_favor_revenue_and_margin(self):
        fast = compute_delta_metrics(
            make_rows([2020, 2021, 2022], 100.0, [0.05, 0.10, 0.20])
        )
        slow = compute_delta_metrics(
            make_rows([2020, 2021, 2022], 100.0, [0.05, 0.06, 0.07])
        )
        scores = fundamental_momentum_scores(
            {
                "FAST": {"delta_metrics": fast},
                "SLOW": {"delta_metrics": slow},
            }
        )
        self_scores = fundamental_momentum_scores({"ONLY": {"delta_metrics": slow}})
        assert scores["FAST"] > scores["SLOW"]
        assert self_scores["ONLY"] == slow["revenue_growth_delta"] * 0.4

    def test_momentum_missing_deltas_yields_none(self):
        scores = fundamental_momentum_scores({"EMPTY": {"delta_metrics": {}}})
        assert scores["EMPTY"] is None

    def test_zscore_normalizes_universe(self):
        one = compute_delta_metrics(
            make_rows([2019, 2020, 2021], 100.0, [0.05, 0.10, 0.10])
        )
        two = compute_delta_metrics(
            make_rows([2019, 2020, 2021], 100.0, [0.05, 0.10, 0.10])
        )
        scores = fundamental_momentum_scores(
            {"ONE": {"delta_metrics": one}, "TWO": {"delta_metrics": two}}
        )
        assert math.isclose(scores["ONE"], scores["TWO"], rel_tol=1e-9)


class TestStrategies:
    def test_momentum_picks_fastest_grower(self):
        fast = make_analysis(make_rows([2019, 2020, 2021], 100.0, [0.05, 0.10, 0.30]))
        slow = make_analysis(make_rows([2019, 2020, 2021], 100.0, [0.05, 0.06, 0.07]))
        picked = momentum_strategy({"FAST": fast, "SLOW": slow}, top_n=1)
        assert picked == ["FAST"]

    def test_buffett_uses_rank_score(self):
        good = {"composite_score": {"total_score": 0.9}, "dcf_margin_of_safety": 0.3}
        bad = {"composite_score": {"total_score": 0.5}, "dcf_margin_of_safety": 0.0}
        picked = buffett_strategy({"BAD": bad, "GOOD": good}, top_n=1)
        assert picked == ["GOOD"]

    def test_buffett_picks_none_when_all_equal(self):
        neutral = {"composite_score": {"total_score": 0.5}}
        picked = buffett_strategy({"A": neutral, "B": neutral}, top_n=1)
        assert picked == ["A"]

    def test_get_strategy_unknown_raises(self):
        try:
            get_strategy("bogus")
            assert False, "expected ValueError"
        except ValueError:
            pass

    def test_get_strategy_case_insensitive(self):
        assert get_strategy("MOMENTUM") is momentum_strategy


class TestSimulator:
    def test_equity_curve_compounds(self):
        snapshots = [
            {
                "analyses": {"A": {"rank_score": 90}, "B": {"rank_score": 80}},
                "prices": {"A": (100.0, 110.0), "B": (100.0, 90.0)},
            },
            {
                "analyses": {"A": {"rank_score": 90}, "B": {"rank_score": 80}},
                "prices": {"A": (110.0, 121.0), "B": (90.0, 99.0)},
            },
        ]
        curve = equity_curve(snapshots, buffett_strategy, top_n=2, rebalance_every=1)
        assert curve == [1.0, 1.0, 1.1]

    def test_curve_respects_rebalance_window(self):
        snapshots = [
            {"analyses": {"A": {"rank_score": 90}}, "prices": {"A": (100.0, 110.0)}},
            {"analyses": {"A": {"rank_score": 90}}, "prices": {"A": (110.0, 99.0)}},
            {"analyses": {"A": {"rank_score": 90}}, "prices": {"A": (99.0, 108.9)}},
        ]
        curve = equity_curve(snapshots, buffett_strategy, top_n=1, rebalance_every=2)
        assert curve == [1.0, 1.1, 1.1 * 0.9, 1.1 * 0.9 * 1.1]

    def test_missing_prices_treated_as_flat(self):
        snapshots = [
            {
                "analyses": {"A": {"rank_score": 90}, "B": {"rank_score": 80}},
                "prices": {"A": (100.0, 110.0), "B": None},
            },
            {
                "analyses": {"A": {"rank_score": 90}, "B": {"rank_score": 80}},
                "prices": {},
            },
        ]
        curve = equity_curve(snapshots, buffett_strategy, top_n=2, rebalance_every=1)
        assert curve == [1.0, 1.1, 1.1]

    def test_cagr_and_metrics(self):
        curve = [1.0, 1.1, 1.21]
        assert math.isclose(cagr(curve), 0.1)
        assert max_drawdown([1.0, 1.2, 0.6, 0.75]) == -0.5
        assert win_rate([0.1, -0.1]) == 0.5
        assert sharpe([0.05] * 5) is None
        assert (
            math.isclose(sharpe([0.1, -0.1]), -0.0, abs_tol=1e-9)
            or sharpe([0.1, -0.1]) is None
        )

    def test_cagr_none_when_final_value_non_positive(self):
        # A negative final equity value must not produce a complex CAGR.
        assert cagr([1.0, 0.5, -0.2]) is None
        assert cagr([1.0, 0.5, 0.0]) is None

    def test_win_rate_none_empty(self):
        assert win_rate([]) is None


class TestEngine:
    def test_run_backtest_returns_metrics(self):
        snapshots = [
            {
                "year": 2021,
                "analyses": {"A": {"composite_score": {"total_score": 0.9}}},
                "prices": {"A": (100.0, 120.0)},
            },
            {
                "year": 2022,
                "analyses": {"A": {"composite_score": {"total_score": 0.9}}},
                "prices": {"A": (120.0, 144.0)},
            },
            {
                "year": 2023,
                "analyses": {"A": {"composite_score": {"total_score": 0.9}}},
                "prices": {"A": (144.0, 172.8)},
            },
        ]
        result = run_backtest(snapshots, buffett_strategy, top_n=1)
        assert result["cagr"] is not None
        assert abs(result["cagr"] - 0.2) < 1e-9
        assert result["selected_first_period"] == ["A"]
        assert result["periods"] == 3
        assert result["max_drawdown"] >= -1e-9

    def test_empty_snapshots_raise(self):
        try:
            run_backtest([], buffett_strategy)
            assert False, "expected ValueError"
        except ValueError:
            pass

    def test_sort_snapshots_orders_by_year(self):
        snapshots = [{"year": 2022, "analyses": {}}, {"year": 2020, "analyses": {}}]
        assert [s["year"] for s in sort_snapshots(snapshots)] == [2020, 2022]


class TestDeltaFcfGrowth:
    def test_fcf_growth_delta_requires_three_years(self):
        rows = make_rows([2020, 2021], 100.0, [0.10])
        deltas = compute_delta_metrics(rows)
        assert deltas["fcf_growth_last"] is not None
        assert deltas["fcf_growth_prev"] is None
        assert deltas["fcf_growth_delta"] is None

    def test_fcf_growth_delta_acceleration(self):
        rows = [
            {"fiscal_year": 2018, "free_cash_flow": 50.0},
            {"fiscal_year": 2019, "free_cash_flow": 60.0},
            {"fiscal_year": 2020, "free_cash_flow": 90.0},
        ]
        built = _build_rows([{**r, "ticker": "AAA", "is_complete": True} for r in rows])
        deltas = compute_delta_metrics(built)
        assert deltas["fcf_growth_last"] == 0.5
        assert deltas["fcf_growth_prev"] == 0.2
        assert deltas["fcf_growth_delta"] == 0.3
