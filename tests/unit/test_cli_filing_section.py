"""CLI `filing-section` — Risk Factors and MD&A extraction."""

from __future__ import annotations

import sys
from datetime import date
from typing import ClassVar

import pytest

from backend.services.narrative_extractor import NarrativeSection, SectionType
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


def _section(n_words: int = 2100, source: str = "toc_anchor") -> NarrativeSection:
    text = " ".join(f"word{index}" for index in range(n_words))
    return NarrativeSection(
        section_type="risk_factors",
        filing_date=date(2025, 10, 31),
        period_end=date(2025, 9, 27),
        form_type="10-K",
        title="Item 1A. Risk Factors",
        text=text,
        word_count=len(text.split()),
        source=source,
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    import backend.services.filing_service as service_module
    import backend.services.narrative_extractor as narr_module

    _Service.last = {}
    _Service.records = [_record()]
    monkeypatch.setattr(service_module, "FilingService", _Service)
    monkeypatch.setattr(
        narr_module,
        "load_narrative_section",
        lambda record, section_type, **kwargs: _section(),
    )


def _run(*argv):
    sys.argv = ["main.py", *argv]
    main()


def test_default_type_is_risk_factors(capsys):
    _run("filing-section", "AAPL")
    out = capsys.readouterr().out
    assert "Risk Factors — AAPL 10-K filed 2025-10-31" in out
    assert "Word count : 2,100" in out
    assert "TOC anchor" in out
    assert "Item 1A. Risk Factors" in out


def test_md_a_type_flag(capsys):
    _run("filing-section", "AAPL", "--type", "md_a")
    out = capsys.readouterr().out
    assert "MD&A — AAPL" in out


def test_loader_receives_the_selected_type_and_form(monkeypatch, capsys):
    seen: list = []
    import backend.services.narrative_extractor as narr_module

    def spy(record, section_type, **kwargs):
        seen.append((section_type, record.form_type))
        return _section()

    monkeypatch.setattr(narr_module, "load_narrative_section", spy)
    _run("filing-section", "AAPL", "--type", "md_a", "--form", "10-K", "--year", "2024")
    assert seen == [(SectionType.MD_A, "10-K")]
    filters = _Service.last
    assert filters["form_types"] == ["10-K"]
    assert filters["fiscal_years"] == [2024]


def test_default_output_is_truncated_at_1000_words(capsys):
    import re

    _run("filing-section", "AAPL")
    out = capsys.readouterr().out
    assert "[first 1000 words of 2,100]" in out
    assert "... (truncated; use --full" in out
    match = re.search(r"\[first 1000 words of 2,100\]\n\n(.*?)\n\n\.\.\. \(truncated", out, re.S)
    assert match is not None
    assert len(match.group(1).split()) == 1000


def test_word_limit_flag_truncates_at_n_words(capsys):
    _run("filing-section", "AAPL", "--word-limit", "500")
    out = capsys.readouterr().out
    assert "[first 500 words of 2,100]" in out


def test_full_prints_everything(capsys):
    _run("filing-section", "AAPL", "--full")
    out = capsys.readouterr().out
    assert "[first" not in out
    assert "(truncated" not in out
    assert "word2099" in out  # the very last word is present


def test_failure_prints_warning_and_sec_url(monkeypatch, capsys):
    import backend.services.narrative_extractor as narr_module

    monkeypatch.setattr(narr_module, "load_narrative_section", lambda *a, **k: None)
    _run("filing-section", "AAPL")
    out = capsys.readouterr().out
    assert "No se pudo extraer Risk Factors" in out
    assert "https://www.sec.gov/Archives/edgar/data/320193" in out


def test_unknown_type_raises_a_clear_error(capsys):
    with pytest.raises(SystemExit):
        _run("filing-section", "AAPL", "--type", "bogus")
    err = capsys.readouterr().err
    assert "invalid choice" in err


def test_accession_flag_picks_a_specific_filing(monkeypatch, capsys):
    import backend.services.narrative_extractor as narr_module

    seen: list = []
    monkeypatch.setattr(
        narr_module,
        "load_narrative_section",
        lambda record, section_type, **kwargs: (
            seen.append(record.accession_number) or _section()
        ),
    )
    _run("filing-section", "AAPL", "--accession", "0000320193-25-000079")
    assert seen == ["0000320193-25-000079"]
    assert _Service.last["form_types"] is None
