"""Tests for the Greenblatt ranking script (deterministic, no network)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from scripts import compute_greenblatt_rankings as script


def _row(ebit, ca, cl, ppe):
    return NormalizedFinancials(
        ticker="X",
        fiscal_year=2024,
        period="FY",
        ebit=ebit,
        current_assets=ca,
        current_liabilities=cl,
        net_ppe=ppe,
        total_debt=0.0,
        cash_and_equivalents=0.0,
    )


class _Repo:
    def __init__(self, rows):
        self._rows = rows

    def get_best_available(self, ticker):
        return self._rows.get(ticker, [])


class _Prices:
    def __init__(self, caps):
        self._caps = caps

    def get_market_snapshots(self, tickers):
        return {ticker: {"marketCap": self._caps.get(ticker)} for ticker in tickers}


def _universe(tmp_path: Path) -> Path:
    path = tmp_path / "universe.csv"
    path.write_text(
        "ticker,cik,company_name,source_index\n"
        "AAPL,1,Apple,SP500\n"
        "MSFT,2,Microsoft,SP500\n"
        "KO,3,Coca-Cola,SP500\n"
    )
    return path


def _patch(monkeypatch):
    repo = _Repo(
        {
            "AAPL": [_row(200.0, 500.0, 200.0, 300.0)],  # ROC 33%
            "MSFT": [_row(100.0, 500.0, 200.0, 800.0)],  # ROC 11%
            "KO": [_row(150.0, 500.0, 400.0, 100.0)],  # NWC floored, ROC 150%
        }
    )
    prices = _Prices({"AAPL": 1_000.0, "MSFT": 2_000.0, "KO": 500.0})
    monkeypatch.setattr(script, "build_financial_repository", lambda: repo)
    monkeypatch.setattr(script, "get_price_service", lambda: prices)


def test_script_writes_valid_json(tmp_path, monkeypatch):
    _patch(monkeypatch)
    code = script.main(
        ["--universe", str(_universe(tmp_path)), "--output-dir", str(tmp_path)]
    )
    assert code == 0
    payload = json.loads(
        (
            tmp_path / f"greenblatt_{datetime.now(UTC).date().isoformat()}.json"
        ).read_text()
    )
    assert payload["universe_size"] == 3
    assert set(payload["rankings"]) == {"AAPL", "KO", "MSFT"}
    ko = payload["rankings"]["KO"]
    assert ko["rank_roc"] == 1  # highest ROC
    assert 0 < ko["percentile"] <= 1


def test_two_runs_same_day_identical(tmp_path, monkeypatch):
    _patch(monkeypatch)
    output = tmp_path / "out"
    args = ["--universe", str(_universe(tmp_path)), "--output-dir", str(output)]
    assert script.main(args) == 0
    first = (
        output / f"greenblatt_{datetime.now(UTC).date().isoformat()}.json"
    ).read_text()
    assert script.main(args) == 0
    second = (
        output / f"greenblatt_{datetime.now(UTC).date().isoformat()}.json"
    ).read_text()
    assert first == second


def test_deterministic_ordering(tmp_path, monkeypatch):
    _patch(monkeypatch)
    payload = script.compute_rankings(
        ["MSFT", "AAPL", "KO"],
        _Repo(
            {
                "AAPL": [_row(200.0, 500.0, 200.0, 300.0)],
                "MSFT": [_row(100.0, 500.0, 200.0, 800.0)],
                "KO": [_row(150.0, 500.0, 400.0, 100.0)],
            }
        ),
        _Prices({"AAPL": 1_000.0, "MSFT": 2_000.0, "KO": 500.0}),
    )
    assert list(payload["rankings"]) == ["AAPL", "KO", "MSFT"]  # sorted keys
    assert payload["rankings"]["KO"]["rank_roc"] == 1
    assert payload["rankings"]["MSFT"]["rank_roc"] == 3
