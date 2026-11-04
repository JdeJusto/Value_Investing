"""Backfill of the legacy JSON store from Financial-DataBase."""

from __future__ import annotations

import json

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.repositories.json_financial_repository import JsonFinancialRepository
from scripts.backfill_json_store import backfill, load_tickers


class _FakeFdb:
    def __init__(self, rows):
        self._rows = rows

    def get_best_available(self, ticker):
        return self._rows.get(ticker, [])


class _BoomFdb:
    def get_best_available(self, ticker):
        raise RuntimeError("fdb down")


def _row(ticker: str, year: int, revenue: float) -> NormalizedFinancials:
    return NormalizedFinancials.from_dict(
        {
            "ticker": ticker,
            "fiscal_year": year,
            "period": "FY",
            "source": "edgar",
            "revenue": revenue,
            "net_income": revenue / 10,
        }
    )


def test_load_tickers_dedupes_and_preserves_order(tmp_path):
    path = tmp_path / "universe.csv"
    path.write_text(
        "ticker,source_index\nAAPL,SP500\nMSFT,NASDAQ100\naapl,SP500\n",
        encoding="utf-8",
    )
    assert load_tickers(path) == ["AAPL", "MSFT"]


def test_backfill_replaces_the_legacy_null_file(tmp_path):
    legacy = tmp_path / "AAPL.json"
    legacy.write_text(
        json.dumps(
            {
                "ticker": "AAPL",
                "years": {
                    "2025": {
                        "yahoo": {
                            "ticker": "AAPL",
                            "fiscal_year": 2025,
                            "revenue": None,
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    repo = JsonFinancialRepository(tmp_path)
    fdb = _FakeFdb({"AAPL": [_row("AAPL", 2025, 100.0)]})

    report = backfill(["AAPL"], fdb, repo)

    assert report.written == ["AAPL"]
    payload = json.loads(legacy.read_text(encoding="utf-8"))
    records = [record for year in payload["years"].values() for record in year.values()]
    assert len(records) == 1
    assert records[0]["revenue"] == 100.0


def test_backfill_keeps_the_file_when_fdb_has_no_rows(tmp_path):
    legacy = tmp_path / "AAPL.json"
    legacy.write_text('{"ticker": "AAPL", "years": {}}', encoding="utf-8")
    repo = JsonFinancialRepository(tmp_path)

    report = backfill(["AAPL"], _FakeFdb({}), repo)

    assert report.missing == ["AAPL"]
    assert legacy.exists()


def test_backfill_records_a_failed_ticker_without_stopping(tmp_path):
    repo = JsonFinancialRepository(tmp_path)

    report = backfill(["AAPL"], _BoomFdb(), repo)

    assert report.failed == {"AAPL": "fdb down"}
    assert report.written == []
