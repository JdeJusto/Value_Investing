"""Methodology backtest PoC (hermetic): truncation, metrics, Greenblatt guard."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from backend.methodologies.base import Confidence, MethodologyResult, Verdict
from backend.services.methodology_backtest_service import MethodologyBacktestService


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
    def __init__(self, verdict=Verdict.BUY):
        self.verdict = verdict
        self.seen: list[int] = []

    def evaluate(self, ticker, rows, prices):
        self.seen.append(max(row.fiscal_year for row in rows))
        return MethodologyResult(
            methodology="fake",
            version="1.0",
            family="TEST",
            verdict=self.verdict,
            score=None,
            metrics={},
            reasons=[],
            red_flags=[],
            confidence=Confidence.LOW,
            sources=[],
            passed_rules=[],
            failed_rules=[],
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


def _service(method=None):
    method = method or _Method()
    rows = [_row(year) for year in range(2019, 2025)]
    prices = _Prices(
        {
            "AAPL": {
                2019: 100.0,
                2020: 120.0,
                2021: 108.0,
                2022: 129.6,
                2023: 142.56,
                2024: 171.072,
            }
        }
    )
    return (
        MethodologyBacktestService(
            repository=_Repository(rows),
            price_service=prices,
            methodology_registry=_Registry(method),
        ),
        method,
    )


def test_backtest_graham_returns_metrics():
    service, _ = _service()
    result = service.run(["AAPL"], "graham", years=4)

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
    service.run(["AAPL"], "graham", years=4)

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
    result = service.run(["AAPL"], "graham", years=4)

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
