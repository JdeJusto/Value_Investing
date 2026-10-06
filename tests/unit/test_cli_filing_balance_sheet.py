"""CLI `filing-balance-sheet`: flags, call order and fallback."""

from __future__ import annotations

import sys
from datetime import date
from typing import ClassVar

import pytest

from cli.main import main


class _Record:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _Sheet:
    source = "fallback"
    extraction_warnings: ClassVar[list] = ["no anchor matched"]
    header_periods = ("September 27, 2025", "September 28, 2024")

    class _Line:
        def __init__(self, label, current, prior):
            self.label, self.current, self.prior, self.indent_level = (
                label,
                current,
                prior,
                0,
            )

    lines: ClassVar[list] = [
        _Line("Cash and cash equivalents", "$29,943", "$29,965"),
        _Line("Total assets", "$364,980", "$352,583"),
    ]


def _record():
    return _Record(
        form_type="10-K",
        filing_date=date(2025, 10, 31),
        period_of_report=date(2025, 9, 27),
        accession_number="0000320193-25-000079",
        sec_url="https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/",
    )


class _Service:
    last: ClassVar[dict] = {}
    records: ClassVar[list] = []

    def __init__(self, *args, **kwargs):
        pass

    def list_filings(self, ticker, **kwargs):
        type(self).last = {"ticker": ticker, **kwargs}
        return list(type(self).records)


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    import backend.services.balance_sheet_parser as parser_module
    import backend.services.filing_service as service_module

    _Service.last = {}
    _Service.records = [_record()]
    monkeypatch.setattr(service_module, "FilingService", _Service)
    monkeypatch.setattr(
        parser_module, "load_balance_sheet", lambda record, fetcher=None: _Sheet()
    )


def _run(*argv):
    sys.argv = ["main.py", "filing-balance-sheet", *argv]
    main()


def test_default_filters_and_formatted_output(capsys):
    _run("AAPL")
    from backend.services.filing_service import DEFAULT_FORM_TYPES

    assert _Service.last["form_types"] == list(DEFAULT_FORM_TYPES)
    out = capsys.readouterr().out
    assert "Balance Sheet — AAPL 10-K filed 2025-10-31" in out
    assert "$29,943" in out
    assert "Total assets" in out
    assert "Extraction: fallback" in out
    assert "Original: https://www.sec.gov" in out


def test_form_and_year_filters(capsys):
    _run("AAPL", "--form", "10-K", "--year", "2025")
    assert _Service.last["form_types"] == ["10-K"]
    assert _Service.last["fiscal_years"] == [2025]


def test_accession_flag_selects_the_filing(capsys):
    _run("AAPL", "--accession", "0000320193-25-000079")
    assert _Service.last["form_types"] is None
    assert "10-K" in capsys.readouterr().out


def test_raw_flag_prints_plain_rows(capsys):
    _run("AAPL", "--raw")
    out = capsys.readouterr().out
    assert "Cash and cash equivalents | $29,943 | $29,965" in out
    assert "Line item" not in out


def test_no_match_prints_a_message(monkeypatch, capsys):
    _Service.records = []
    _run("AAPL")
    assert "No filings for AAPL" in capsys.readouterr().out


def test_parser_failure_shows_the_sec_url(monkeypatch, capsys):
    import backend.services.balance_sheet_parser as parser_module

    monkeypatch.setattr(
        parser_module, "load_balance_sheet", lambda record, fetcher=None: None
    )
    _run("AAPL")
    out = capsys.readouterr().out
    assert "Could not extract the balance sheet" in out
    assert "Original: https://www.sec.gov" in out
