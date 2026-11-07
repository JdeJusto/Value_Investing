"""Methodology backtest PoC (hermetic): truncation, metrics, Greenblatt guard."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from backend.methodologies.base import Confidence, MethodologyResult, Verdict
from backend.services.methodology_backtest_service import MethodologyBacktestService

TODAY = date(2026, 11, 7)


class _Repository:
    def __init__(self, rows):
        self.rows = rows

    def list_all(self, ticker, max_years=None):
        return list(self.rows)

    def get_fiscal_year_end_date(self, ticker, year):
        return date(year, 12, 31)


class _Prices:
    def __init__(self, series):
        self.series = series

    def get_price_at_fiscal_year_end(self, ticker, year, end=None):
        return self.series.get(ticker, {}).get(year)


class _Method:
    def __init__(
        self,
        verdict=Verdict.BUY,
        *,
        by_year: dict[int, Verdict] | None = None,
        failed_by_ticker: dict[str, tuple[str, ...]] | None = None,
        na_tickers: set[str] | None = None,
    ):
        self.verdict = verdict
        self.by_year = by_year or {}
        self.failed_by_ticker = failed_by_ticker or {}
        self.na_tickers = na_tickers or set()
        self.seen: list[int] = []

    def rules(self):
        return [
            SimpleNamespace(id="fake.rule_1", name="Rule one"),
            SimpleNamespace(id="fake.rule_2", name="Rule two"),
        ]

    def evaluate(self, ticker, rows, prices):
        year = max(row.fiscal_year for row in rows)
        self.seen.append(year)
        verdict = (
            Verdict.NOT_APPLICABLE
            if ticker in self.na_tickers
            else self.by_year.get(year, self.verdict)
        )
        failed = self.failed_by_ticker.get(ticker, ())
        return MethodologyResult(
            methodology="fake",
            version="1.0",
            family="TEST",
            verdict=verdict,
            score=None,
            metrics={},
            reasons=[],
            red_flags=[],
            confidence=Confidence.LOW,
            sources=[],
            passed_rules=[],
            failed_rules=list(failed),
        )


class _Registry:
    def __init__(self, method):
        self.method = method

    def list(self):
        return ["graham", "greenblatt"]

    def get(self, name):
        return self.method if name == "graham" else None


def _row(year):
    return SimpleNamespace(
        fiscal_year=year,
        shares_outstanding=1_000,
        split_adjustment_factor=1.0,
    )


def _service(method=None, series=None, spy=None, rows_years=None):
    method = method or _Method()
    years = rows_years or range(2019, 2025)
    rows = [_row(year) for year in years]
    default_series = {
        "AAPL": {
            2019: 100.0,
            2020: 120.0,
            2021: 108.0,
            2022: 129.6,
            2023: 142.56,
            2024: 171.072,
        }
    }
    price_series = series or default_series
    if spy:
        price_series = {**price_series, "SPY": spy}
    return (
        MethodologyBacktestService(
            repository=_Repository(rows),
            price_service=_Prices(price_series),
            methodology_registry=_Registry(method),
        ),
        method,
    )


def test_backtest_graham_returns_metrics():
    service, _ = _service()
    result = service.run(["AAPL"], "graham", years=4, today=TODAY)

    assert result.years == (2021, 2022, 2023)
    assert result.buy_signals == 3
    assert result.annualized_return is not None
    assert result.hit_rate is not None
    assert result.benchmark_annualized is not None
    assert len(result.per_year) == 3
    payload = result.to_dict()
    assert payload["methodology"] == "graham"
    assert set(payload) >= {"annualized_return", "hit_rate", "sharpe"}


def test_fundamentals_are_truncated_to_the_signal_year():
    service, method = _service()
    service.run(["AAPL"], "graham", years=4, today=TODAY)

    assert method.seen == [2021, 2022, 2023]


def test_greenblatt_is_rejected_for_look_ahead():
    service, _ = _service()
    with pytest.raises(ValueError, match="look-ahead"):
        service.run(["AAPL"], "greenblatt")


def test_unknown_methodology_raises():
    service, _ = _service()
    with pytest.raises(ValueError, match="unknown methodology"):
        service.run(["AAPL"], "nope")


def test_no_buy_signals_means_cash_and_no_hit_rate():
    service, _ = _service(_Method(verdict=Verdict.AVOID))
    result = service.run(["AAPL"], "graham", years=4, today=TODAY)

    assert result.buy_signals == 0
    assert result.annualized_return == 0.0
    assert result.hit_rate is None


def test_cli_methodology_backtest_prints_a_table(monkeypatch, capsys):
    from argparse import Namespace

    import cli.commands.backtest as backtest_cli

    service, _ = _service()
    monkeypatch.setattr(
        "backend.services.methodology_backtest_service.MethodologyBacktestService",
        lambda: service,
    )
    backtest_cli._run_methodology_backtest(
        Namespace(
            methodology=["graham"],
            tickers=["AAPL"],
            universe="sp500",
            limit=25,
            years=4,
        )
    )

    out = capsys.readouterr().out
    assert "graham" in out
    assert "CAGR" in out


# ---------------------------------------------------------------------------
# v0.23.0 output: year breakdown, dual benchmark, YTD, closest, filter, JSON
# ---------------------------------------------------------------------------
def test_backtest_output_has_year_breakdown():
    method = _Method(
        by_year={2021: Verdict.BUY, 2022: Verdict.WATCH, 2023: Verdict.AVOID}
    )
    service, _ = _service(method)
    result = service.run(["AAPL"], "graham", years=4, today=TODAY)
    payload = result.to_dict()

    assert payload["verdicts_by_year"]["2021"]["BUY"] == 1
    assert payload["verdicts_by_year"]["2022"]["WATCH"] == 1
    assert payload["verdicts_by_year"]["2023"]["AVOID"] == 1
    assert set(payload["verdicts_by_year"]["2023"]) == {
        "BUY",
        "WATCH",
        "HOLD",
        "AVOID",
        "N/A",
        "INSUFFICIENT_DATA",
    }


def test_backtest_output_benchmark_labels(capsys):
    import cli.commands.backtest as backtest_cli

    spy = {2020: 100.0, 2021: 110.0, 2022: 99.0, 2023: 118.8, 2024: 148.5}
    service, _ = _service(spy=spy)
    result = service.run(["AAPL"], "graham", years=4, today=TODAY)
    assert result.spy_annualized is not None

    backtest_cli._render_methodology(result)
    out = capsys.readouterr().out
    assert "Opportunity set CAGR" in out
    assert "SPY CAGR" in out


def test_backtest_2025_ytd_excluded_from_cagr():
    series = {
        "AAPL": {
            2019: 100.0,
            2020: 100.0,
            2021: 110.0,
            2022: 121.0,
            2023: 133.1,
            2024: 146.41,
            2025: 161.051,
            2026: 322.102,
        }
    }
    service, _ = _service(series=series, rows_years=range(2019, 2027))
    result = service.run(["AAPL"], "graham", years=7, today=TODAY)

    assert result.per_year[-1].year == 2025
    assert result.per_year[-1].complete is False
    assert result.complete_years == (2021, 2022, 2023, 2024)
    assert result.annualized_return == pytest.approx(0.10)
    payload = result.to_dict()
    assert payload["years"][-1] == {"year": 2025, "complete": False, "label": "YTD"}


def test_backtest_closest_reason():
    series = {
        "AAPL": {year: 100.0 + year for year in range(2019, 2025)},
        "MSFT": {year: 200.0 + year for year in range(2019, 2025)},
        "JPM": {year: 300.0 + year for year in range(2019, 2025)},
    }
    method = _Method(
        verdict=Verdict.AVOID,
        failed_by_ticker={
            "AAPL": ("fake.rule_1",),
            "MSFT": (
                "fake.rule_1",
                "fake.rule_2",
                "fake.rule_3",
                "fake.rule_4",
            ),
        },
        na_tickers={"JPM"},
    )
    service, _ = _service(method, series=series)
    result = service.run(["AAPL", "MSFT", "JPM"], "graham", years=4, today=TODAY)
    reason = result.no_buy_reason

    assert reason["closest"][0]["ticker"] == "AAPL"
    assert reason["closest"][0]["n_failed"] == 1
    assert all(record["ticker"] != "JPM" for record in reason["closest"])
    # 3 AAPL years (<3 failures); the N/A company is not counted.
    assert reason["counts"]["lt3_failed"] == 3
    assert reason["rules"] == [
        {"id": "fake.rule_1", "name": "Rule one"},
        {"id": "fake.rule_2", "name": "Rule two"},
    ]


def test_backtest_verdict_filter(monkeypatch):
    from cli.commands.backtest import parse_methodology_arg

    assert parse_methodology_arg("graham:BUY") == ("graham", "BUY")
    assert parse_methodology_arg("graham") == ("graham", None)

    method = _Method(
        by_year={2021: Verdict.WATCH, 2022: Verdict.WATCH, 2023: Verdict.WATCH}
    )
    service, _ = _service(method)
    result = service.run(
        ["AAPL"], "graham", years=4, verdict_filter="WATCH", today=TODAY
    )
    assert result.selected_verdict == "WATCH"
    assert result.buy_signals == 3
    # Forward returns 2021->2022 (+20%), 2022->2023 (+10%), 2023->2024 (+20%).
    assert result.annualized_return == pytest.approx((1.2 * 1.1 * 1.2) ** (1 / 3) - 1)

    with pytest.raises(ValueError, match="unknown verdict"):
        service.run(["AAPL"], "graham", verdict_filter="MAYBE")


def test_backtest_json_shape():
    service, _ = _service()
    result = service.run(
        ["AAPL"],
        "graham",
        years=4,
        universe_name="sp500",
        universe_total=500,
        today=TODAY,
    )
    payload = result.to_dict()

    assert payload["universe"] == {
        "name": "sp500",
        "evaluated": 1,
        "total": 1,
        "sample_of": 500,
    }
    assert payload["years"][0]["complete"] is True
    assert set(payload["performance"]) >= {
        "portfolio_cagr",
        "opportunity_set_cagr",
        "spy_cagr",
        "alpha_vs_opportunity_set",
        "alpha_vs_spy",
        "portfolio_sharpe",
        "opportunity_set_sharpe",
        "spy_sharpe",
    }
    assert "rules" in payload["no_buy_reason"]
    assert "closest" in payload["no_buy_reason"]
    assert isinstance(payload["skipped_tickers"], list)
    assert isinstance(payload["notes"], list)
