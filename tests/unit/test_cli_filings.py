"""CLI `filings`: default filters, flags and --open (no database)."""

from __future__ import annotations

import sys
from datetime import date
from typing import ClassVar

import pytest

from backend.services.filing_service import DEFAULT_FORM_TYPES
from cli.main import main


class _Record:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _Repo:
    def get_company_name(self, ticker):
        return "Apple Inc."


class _Recorder:
    last: ClassVar[dict] = {}
    records: ClassVar[list] = []

    def __init__(self, *args, **kwargs):
        pass

    def list_filings(self, ticker, **kwargs):
        type(self).last = {"ticker": ticker, **kwargs}
        return list(type(self).records)


def _record(form="10-K"):
    return _Record(
        form_type=form,
        filing_date=date(2024, 11, 1),
        period_of_report=date(2024, 9, 28),
        effective_fiscal_year=2024,
        accession_number="0000320193-24-000123",
        sec_url="https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/",
    )


def _record_doc(form="10-K"):
    """A record whose primary document URL is known."""
    return _Record(
        form_type=form,
        filing_date=date(2024, 11, 1),
        period_of_report=date(2024, 9, 28),
        effective_fiscal_year=2024,
        accession_number="0000320193-24-000123",
        sec_url=(
            "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/"
            "aapl-20240928.htm"
        ),
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    import backend.services.filing_service as module

    _Recorder.last = {}
    _Recorder.records = [_record()]
    monkeypatch.setattr(module, "FilingService", _Recorder)
    monkeypatch.setattr("backend.app.cli.build_financial_repository", lambda: _Repo())


def _run(*argv):
    monkeypatch_argv = ["main.py", "filings", *argv]
    sys.argv = monkeypatch_argv
    main()


def test_default_form_types_and_limit(monkeypatch, capsys):
    _run("AAPL")
    assert _Recorder.last["ticker"] == "AAPL"
    assert _Recorder.last["form_types"] == list(DEFAULT_FORM_TYPES)
    assert _Recorder.last["limit"] == 40
    out = capsys.readouterr().out
    assert "Filings — AAPL (Apple Inc.)" in out
    assert "0000320193-24-000123" in out


def test_form_flag_overrides_defaults(monkeypatch, capsys):
    _run("AAPL", "--form", "10-K,10-Q")
    assert _Recorder.last["form_types"] == ["10-K", "10-Q"]


def test_all_flag_disables_the_form_filter(monkeypatch, capsys):
    _run("AAPL", "--all")
    assert _Recorder.last["form_types"] is None


def test_year_flag_is_repeatable(monkeypatch, capsys):
    _run("AAPL", "--year", "2024", "--year", "2023")
    assert _Recorder.last["fiscal_years"] == [2024, 2023]


def test_since_flag_parses_the_date(monkeypatch, capsys):
    _run("AAPL", "--since", "2020-01-01")
    assert _Recorder.last["start_date"] == date(2020, 1, 1)


def test_invalid_since_does_not_query(monkeypatch, capsys):
    _run("AAPL", "--since", "not-a-date")
    assert _Recorder.last == {}
    assert "Invalid date" in capsys.readouterr().out


def test_open_flag_uses_the_browser(monkeypatch, capsys):
    opened: list[str] = []
    monkeypatch.setattr(
        "cli.commands.filings.webbrowser.open", lambda url: opened.append(url)
    )
    _run("AAPL", "--open")
    assert opened == [_record().sec_url]
    assert "Opening 10-K 2024-11-01" in capsys.readouterr().out


def test_open_passes_the_document_url_when_available(monkeypatch, capsys):
    _Recorder.records = [_record_doc()]
    opened: list[str] = []
    monkeypatch.setattr(
        "cli.commands.filings.webbrowser.open", lambda url: opened.append(url)
    )
    _run("AAPL", "--open")
    assert opened == [_record_doc().sec_url]
    assert opened[0].endswith(".htm")  # the primary document, not the index

    out = capsys.readouterr().out
    assert "Opening 10-K 2024-11-01" in out


def test_empty_state_is_clear(monkeypatch, capsys):
    _Recorder.records = []
    _run("AAPL")
    assert "No filings match the filters" in capsys.readouterr().out


def test_urls_flag_prints_the_raw_url(monkeypatch, capsys):
    _run("AAPL", "--urls")
    assert "https://www.sec.gov/Archives/edgar/data/320193/" in capsys.readouterr().out


def test_urls_flag_prints_the_document_url_when_available(monkeypatch, capsys):
    _Recorder.records = [_record_doc()]
    _run("AAPL", "--urls")
    out = capsys.readouterr().out
    assert (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/"
        "aapl-20240928.htm" in out
    )


def test_rows_are_rendered_as_a_table_without_ansi(monkeypatch, capsys):
    """Filings render through the shared table helper: a framed table on a
    terminal-less run and never a single escape code."""
    _Recorder.records = [_record(), _record("10-Q")]
    _run("AAPL")
    out = capsys.readouterr().out

    assert "┏" in out and "┃" in out and "└" in out  # rich table frame
    for header in ("Form", "Filed", "Period", "FY", "Accession", "Link"):
        assert header in out
    assert "0000320193-24-000123" in out
    assert "10-Q" in out
    assert "\x1b" not in out
