"""Filings preview: demo fixture loading and the UI controls."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest

from backend.services.balance_sheet_parser import load_balance_sheet

PAGE = Path(__file__).resolve().parents[2] / "ui" / "pages" / "02_analysis.py"


class _Record:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _demo_record(ticker="AAPL", form="10-K"):
    """A record matching the committed demo fixture name."""
    return _Record(
        ticker=ticker,
        form_type=form,
        filing_date=date(2025, 10, 31),
        period_of_report=date(2025, 9, 27),
        cik="0000320193",
        accession_number="0000320193-25-000079",
        primary_document=None,
        sec_url="https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/",
    )


def test_demo_fixture_loads_the_real_balance_sheet(monkeypatch):
    monkeypatch.setenv("VI_DEMO", "1")
    sheet = load_balance_sheet(_demo_record())
    assert sheet is not None
    assert sheet.lines, "the fixture must carry rows"
    labels = [line.label for line in sheet.lines]
    assert any("Total assets" in label for label in labels)
    assert sheet.header_periods[0]  # a real period label


def test_missing_demo_fixture_returns_none(monkeypatch):
    monkeypatch.setenv("VI_DEMO", "1")
    assert load_balance_sheet(_demo_record(ticker="ZZZZ")) is None


def test_fetch_failure_returns_none_without_raising(monkeypatch, tmp_path):
    monkeypatch.delenv("VI_DEMO", raising=False)

    class _Boom:
        def fetch_html(self, *args, **kwargs):
            return None

    # A temp cache keeps the test independent of any previously parsed filing
    # (a real fetch of the same accession would otherwise satisfy the lookup).
    assert (
        load_balance_sheet(_demo_record(), fetcher=_Boom(), cache_dir=tmp_path) is None
    )


def _run(monkeypatch) -> AppTest:
    monkeypatch.setenv("VI_DEMO", "1")
    at = AppTest.from_file(str(PAGE), default_timeout=120)
    at.run()
    next(button for button in at.button if button.label == "Analyze").click()
    at.run()
    return at


def test_filings_tab_renders_without_a_selection(monkeypatch):
    at = _run(monkeypatch)
    assert not at.exception, at.exception
    captions = " ".join(caption.value for caption in at.caption)
    assert "Select a row to preview its balance sheet" in captions


def test_tab_renders_the_demo_filings_table(monkeypatch):
    at = _run(monkeypatch)
    assert not at.exception
    frames = [
        element.value
        for element in at.dataframe
        if "Open on SEC" in list(element.value.columns)
    ]
    assert frames, "the filings table must render in demo mode"
    assert frames[0]["Accession"].str.len().min() >= 15
