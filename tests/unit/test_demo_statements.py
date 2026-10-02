"""Demo statement fixtures: every shipped fixture parses and loads."""

from __future__ import annotations

import json
from datetime import date

import pytest

from backend.services.demo_mode import DEMO_ROOT
from backend.services.financial_statement_parser import (
    StatementType,
    load_financial_statement,
)

STATEMENTS_DIR = DEMO_ROOT / "statements"
TICKERS = ("AAPL", "KO", "JNJ", "JPM")


class _Record:
    def __init__(self, ticker: str, period: str):
        self.ticker = ticker
        self.form_type = "10-K"
        self.filing_date = date(2025, 10, 31)
        self.period_of_report = date.fromisoformat(period)
        self.cik = "0000320193"
        self.accession_number = "0000320193-25-000079"
        self.primary_document = None
        self.sec_url = "https://www.sec.gov/"


def _fixtures() -> list[tuple[str, str, str]]:
    """(ticker, statement_type, period) for every committed fixture."""
    found = []
    for path in sorted(STATEMENTS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        ticker = path.stem.split("_", 1)[0]
        statement_type = path.stem.split("_", 1)[1].rsplit("_", 1)[0]
        period = path.stem.rsplit("_", 1)[1]
        found.append((ticker, statement_type, period))
        assert payload["statement_type"] == statement_type
        assert payload["lines"]
    return found


def test_fixtures_exist_and_are_small():
    fixtures = _fixtures()
    assert len(fixtures) >= 11
    total = sum(path.stat().st_size for path in STATEMENTS_DIR.glob("*.json"))
    assert total < 500 * 1024, f"demo statements too heavy: {total / 1024:.0f} KB"


@pytest.mark.parametrize("ticker,statement_type,period", _fixtures())
def test_every_fixture_loads_in_demo_mode(monkeypatch, ticker, statement_type, period):
    monkeypatch.setenv("VI_DEMO", "1")
    statement = load_financial_statement(
        _Record(ticker, period), StatementType(statement_type)
    )
    assert statement is not None
    assert statement.lines
    assert statement.statement_type is StatementType(statement_type)


def test_all_three_types_are_covered_for_most_tickers():
    coverage = {}
    for ticker, statement_type, _period in _fixtures():
        coverage.setdefault(ticker, set()).add(statement_type)
    assert coverage["AAPL"] == {"balance_sheet", "income_statement", "cash_flow"}
    assert coverage["KO"] == {"balance_sheet", "income_statement", "cash_flow"}
    # JNJ's income statement uses "Net earnings": documented follow-up.
    assert "balance_sheet" in coverage["JNJ"] and "cash_flow" in coverage["JNJ"]
    assert coverage["JPM"] == {"balance_sheet", "income_statement", "cash_flow"}


def test_missing_fixture_returns_none(monkeypatch):
    monkeypatch.setenv("VI_DEMO", "1")
    assert (
        load_financial_statement(
            _Record("ZZZZ", "2025-09-27"), StatementType.BALANCE_SHEET
        )
        is None
    )


def test_fixtures_respect_the_line_cap_and_document_truncation():
    for path in STATEMENTS_DIR.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert len(payload["lines"]) <= 50
        if any("truncated" in warning for warning in payload["extraction_warnings"]):
            # A truncation warning implies the fixture hit the cap.
            assert len(payload["lines"]) == 50
