"""Hermetic tests for the Greenblatt Magic Formula methodology.

No network, no database: the methodology reads a tmp ranking file and an
injected row; the price object is a stub (and must not be used at all).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.analytics.ratios.greenblatt import earnings_yield, return_on_capital
from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import Verdict
from backend.methodologies.greenblatt.methodology import GreenblattMethodology


class _Prices:
    def get_market_cap(self, ticker):
        return 1_000.0


def _row(**overrides):
    base = {
        "ticker": "TEST",
        "fiscal_year": 2024,
        "period": "FY",
        "ebit": 200.0,
        "current_assets": 500.0,
        "current_liabilities": 200.0,
        "net_ppe": 300.0,
        "total_debt": 100.0,
        "cash_and_equivalents": 50.0,
        "sector": None,
    }
    base.update(overrides)
    return NormalizedFinancials(**base)


def _write_ranking(
    tmp_path: Path, ticker="TEST", percentile=0.05, roc=0.5, ey=0.2, age_days=0
):
    ranking_date = (datetime.now(UTC).date() - timedelta(days=age_days)).isoformat()
    payload = {
        "date": ranking_date,
        "universe_size": 100,
        "rankings": {
            ticker: {
                "rank_roc": 5,
                "rank_ey": 5,
                "combined_rank": 10,
                "percentile": percentile,
                "roc": roc,
                "earnings_yield": ey,
                "fiscal_year": 2024,
            }
        },
    }
    path = tmp_path / f"greenblatt_{ranking_date}.json"
    path.write_text(json.dumps(payload))
    return path


def _evaluate(rows, tmp_path):
    methodology = GreenblattMethodology(rankings_dir=tmp_path)
    return methodology.evaluate("TEST", rows, _Prices())


def test_return_on_capital_known_fixture():
    # EBIT 200 / (max(500 - 200, 0) + 300) = 200 / 600
    assert return_on_capital(_row()) == pytest.approx(200.0 / 600.0)


def test_negative_working_capital_is_floored():
    assert return_on_capital(
        _row(current_assets=100.0, current_liabilities=400.0)
    ) == pytest.approx(200.0 / 300.0)


def test_earnings_yield_known_fixture():
    # EV = market cap 1000 + debt 100 - cash 50
    assert earnings_yield(_row(), 1_000.0) == pytest.approx(200.0 / 1_050.0)


def test_missing_inputs_return_none():
    assert return_on_capital(_row(net_ppe=None)) is None
    assert earnings_yield(_row(), None) is None


def test_roc_not_positive_is_insufficient(tmp_path):
    _write_ranking(tmp_path, roc=0.0)
    result = _evaluate([_row()], tmp_path)
    assert result.verdict is Verdict.INSUFFICIENT_DATA
    assert any("return on capital" in reason for reason in result.reasons)


def test_ey_not_positive_is_insufficient(tmp_path):
    _write_ranking(tmp_path, ey=-0.01)
    result = _evaluate([_row()], tmp_path)
    assert result.verdict is Verdict.INSUFFICIENT_DATA
    assert any("earnings yield" in reason for reason in result.reasons)


@pytest.mark.parametrize(
    "percentile, expected",
    [
        (0.05, Verdict.BUY),
        (0.25, Verdict.WATCH),
        (0.45, Verdict.HOLD),
        (0.75, Verdict.AVOID),
    ],
)
def test_verdict_by_percentile(tmp_path, percentile, expected):
    _write_ranking(tmp_path, percentile=percentile)
    assert _evaluate([_row()], tmp_path).verdict is expected


def test_stale_ranking_is_insufficient(tmp_path):
    _write_ranking(tmp_path, age_days=40)
    result = _evaluate([_row()], tmp_path)
    assert result.verdict is Verdict.INSUFFICIENT_DATA
    assert any("stale" in reason for reason in result.reasons)


def test_ranking_older_than_the_weekly_tolerance_is_stale(tmp_path):
    # Weekly automation: 20 days means two missed runs -> stale (was 30).
    _write_ranking(tmp_path, age_days=20)
    result = _evaluate([_row()], tmp_path)
    assert result.verdict is Verdict.INSUFFICIENT_DATA
    assert any("stale" in reason for reason in result.reasons)


def test_ranking_within_the_weekly_tolerance_is_usable(tmp_path):
    _write_ranking(tmp_path, age_days=10)
    assert _evaluate([_row()], tmp_path).verdict is Verdict.BUY


def test_missing_ranking_file_is_insufficient(tmp_path):
    result = _evaluate([_row()], tmp_path)
    assert result.verdict is Verdict.INSUFFICIENT_DATA
    assert any("no Greenblatt ranking file" in reason for reason in result.reasons)


def test_missing_ticker_is_insufficient(tmp_path):
    _write_ranking(tmp_path, ticker="OTHER")
    result = _evaluate([_row()], tmp_path)
    assert result.verdict is Verdict.INSUFFICIENT_DATA
    assert any("not in the Greenblatt ranking" in reason for reason in result.reasons)


def test_financial_company_is_not_applicable(tmp_path):
    _write_ranking(tmp_path)
    result = _evaluate([_row(sector="Financial Services")], tmp_path)
    assert result.verdict is Verdict.NOT_APPLICABLE
    assert any("financial" in reason.lower() for reason in result.reasons)
    assert result.metrics["financial_company"] is True


def test_deterministic(tmp_path):
    _write_ranking(tmp_path)
    first = _evaluate([_row()], tmp_path)
    second = _evaluate([_row()], tmp_path)
    assert first.verdict == second.verdict
    assert first.score == second.score
    assert first.metrics == second.metrics


def test_no_network_calls_inside_methodology(tmp_path):
    class _Boom:
        def __getattr__(self, name):
            raise AssertionError(f"price service method {name!r} must not be used")

    _write_ranking(tmp_path)
    result = GreenblattMethodology(rankings_dir=tmp_path).evaluate(
        "TEST", [_row()], _Boom()
    )
    assert result.verdict is Verdict.BUY
    assert result.score == pytest.approx(95.0)
