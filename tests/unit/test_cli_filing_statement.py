"""CLI `filing-statement` and its aliases."""

from __future__ import annotations

import sys
from datetime import date
from typing import ClassVar

import pytest

from backend.services.financial_statement_parser import StatementType
from cli.main import main


class _Record:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _Service:
    last: ClassVar[dict] = {}
    records: ClassVar[list] = []

    def __init__(self, *args, **kwargs):
        pass

    def list_filings(self, ticker, **kwargs):
        type(self).last = {"ticker": ticker, **kwargs}
        return list(type(self).records)


def _record():
    return _Record(
        form_type="10-K",
        filing_date=date(2025, 10, 31),
        period_of_report=date(2025, 9, 27),
        accession_number="0000320193-25-000079",
        sec_url="https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/",
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    import backend.services.filing_service as service_module
    import backend.services.financial_statement_parser as parser_module

    _Service.last = {}
    _Service.records = [_record()]
    monkeypatch.setattr(service_module, "FilingService", _Service)
    monkeypatch.setattr(
        parser_module,
        "load_financial_statement",
        lambda record, statement_type, **kwargs: _StubStatement(statement_type),
    )


class _StubStatement:
    def __init__(self, statement_type):
        self.statement_type = statement_type
        self.source = "fallback"
        self.extraction_warnings = ["no anchor matched"]
        self.header_periods = ("September 27, 2025", "September 28, 2024")

        class _Line:
            def __init__(self):
                self.label = "Net income"
                self.current = "$93,736"
                self.prior = "$96,995"
                self.indent_level = 0

        self.lines = [_Line()]


def _run(*argv):
    sys.argv = ["main.py", *argv]
    main()


def test_default_type_is_balance_sheet(capsys):
    _run("filing-statement", "AAPL")
    out = capsys.readouterr().out
    assert "Balance Sheet — AAPL" in out
    assert "Statement: Balance Sheet" in out


def test_income_type_flag(capsys):
    _run("filing-statement", "AAPL", "--type", "income_statement")
    assert "Income Statement — AAPL" in capsys.readouterr().out


def test_cash_flow_type_flag(capsys):
    _run("filing-statement", "AAPL", "--type", "cash_flow")
    assert "Cash Flow — AAPL" in capsys.readouterr().out


def test_alias_commands_preset_the_type(capsys):
    _run("filing-income-statement", "AAPL")
    assert "Income Statement — AAPL" in capsys.readouterr().out
    _run("filing-cash-flow", "AAPL")
    assert "Cash Flow — AAPL" in capsys.readouterr().out


def test_loader_receives_the_selected_type(monkeypatch, capsys):
    seen: list = []
    import backend.services.financial_statement_parser as parser_module

    def spy(record, statement_type, **kwargs):
        seen.append(statement_type)
        return _StubStatement(statement_type)

    monkeypatch.setattr(parser_module, "load_financial_statement", spy)
    _run("filing-statement", "AAPL", "--type", "cash_flow")
    assert seen == [StatementType.CASH_FLOW]


def test_raw_flag_prints_plain_rows(capsys):
    _run("filing-statement", "AAPL", "--raw")
    out = capsys.readouterr().out
    assert "Net income | $93,736 | $96,995" in out
