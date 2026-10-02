"""The Filings tab's Narrative view: demo fixtures, preview and controls."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import ClassVar

from streamlit.testing.v1 import AppTest

from backend.services.narrative_extractor import NarrativeSection, SectionType
from backend.services.ui_adapter import render_narrative_preview

PAGE = Path(__file__).resolve().parents[2] / "ui" / "pages" / "02_analysis.py"


class _Record:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _demo_record(ticker="AAPL"):
    return _Record(
        ticker=ticker,
        form_type="10-K",
        filing_date=date(2025, 10, 31),
        period_of_report=date(2025, 9, 27),
        cik="0000320193",
        accession_number="0000320193-25-000079",
        primary_document=None,
        sec_url="https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/",
    )


def _stub_section(n_words: int = 120) -> NarrativeSection:
    text = " ".join(f"word{index}" for index in range(n_words))
    return NarrativeSection(
        section_type="risk_factors",
        filing_date=date(2025, 10, 31),
        period_end=date(2025, 9, 27),
        form_type="10-K",
        title="Item 1A. Risk Factors",
        text=text,
        word_count=len(text.split()),
        source="toc_anchor",
    )


def test_demo_fixture_loads_real_risk_factors(monkeypatch):
    monkeypatch.setenv("VI_DEMO", "1")
    from backend.services.narrative_extractor import load_narrative_section

    section = load_narrative_section(_demo_record(), SectionType.RISK_FACTORS)
    assert section is not None
    assert section.word_count > 100
    assert "The Company" in section.text


def test_demo_fixture_loads_real_md_a(monkeypatch):
    monkeypatch.setenv("VI_DEMO", "1")
    from backend.services.narrative_extractor import load_narrative_section

    section = load_narrative_section(_demo_record(), SectionType.MD_A)
    assert section is not None
    assert section.word_count > 100


def test_missing_demo_fixture_returns_none(monkeypatch):
    monkeypatch.setenv("VI_DEMO", "1")
    from backend.services.narrative_extractor import load_narrative_section

    assert (
        load_narrative_section(_demo_record("ZZZZ"), SectionType.RISK_FACTORS) is None
    )


def test_preview_renders_metadata_and_text():
    preview = render_narrative_preview(
        _demo_record(), SectionType.RISK_FACTORS, lambda record, st: _stub_section()
    )
    assert preview["ok"] is True
    assert preview["title"] == "Item 1A. Risk Factors"
    assert preview["word_count"] == 120
    assert preview["source_label"] == "TOC anchor"
    assert preview["text"].startswith("word0")


def test_preview_failure_returns_message_and_url():
    preview = render_narrative_preview(
        _demo_record(), SectionType.RISK_FACTORS, lambda record, st: None
    )
    assert preview["ok"] is False
    assert "does not contain" in preview["message"]
    assert "https://www.sec.gov/" in preview["sec_url"]


def test_loader_is_called_only_when_the_preview_renders():
    """No auto-fetch: the loader fires exactly once, on the Load click."""
    calls: list = []

    def spy(record, section_type):
        calls.append(section_type)
        return _stub_section()

    render_narrative_preview(_demo_record(), SectionType.MD_A, spy)
    assert calls == [SectionType.MD_A]


def _run(monkeypatch) -> AppTest:
    monkeypatch.setenv("VI_DEMO", "1")
    at = AppTest.from_file(str(PAGE), default_timeout=120)
    at.run()
    next(button for button in at.button if button.label == "Analyze").click()
    at.run()
    return at


class _FakeSelection:
    rows: ClassVar[list[int]] = [0]


class _FakeEvent:
    selection = _FakeSelection()

    def __getattr__(self, name):
        return None


def _run_with_selection(monkeypatch) -> AppTest:
    """AppTest with st.dataframe faked so one row is always selected.

    AppTest cannot drive dataframe row selection in this Streamlit version,
    and the preview block only renders after a selection; faking the call
    makes the View toggle and both branches exercisable end to end.
    """
    import streamlit

    monkeypatch.setattr(streamlit, "dataframe", lambda *args, **kwargs: _FakeEvent())
    at = _run(monkeypatch)
    assert not at.exception, at.exception
    return at


def test_view_toggle_has_statements_and_narrative(monkeypatch):
    at = _run_with_selection(monkeypatch)
    views = [radio for radio in at.radio if radio.label == "View"]
    assert views and set(views[0].options) == {"Statements", "Narrative"}


def test_narrative_selector_renders_after_toggle(monkeypatch):
    at = _run_with_selection(monkeypatch)
    next(radio for radio in at.radio if radio.label == "View").set_value("Narrative")
    at.run()
    assert not at.exception, at.exception
    sections = [radio for radio in at.radio if radio.label == "Section"]
    assert sections and set(sections[0].options) == {"Risk Factors", "MD&A"}


def test_no_load_button_before_a_row_is_selected(monkeypatch):
    at = _run(monkeypatch)
    assert [b for b in at.button if b.label == "Load"] == []


def test_narrative_load_renders_the_demo_section(monkeypatch):
    at = _run_with_selection(monkeypatch)
    next(radio for radio in at.radio if radio.label == "View").set_value("Narrative")
    at.run()
    # Nothing renders until the Load button is clicked.
    assert "words ·" not in "\n".join(md.value for md in at.markdown)

    load = next(button for button in at.button if button.key == "filings_load_section")
    load.click()
    at.run()
    assert not at.exception, at.exception
    rendered = "\n".join(md.value for md in at.markdown)
    assert "words · TOC anchor" in rendered
    assert "The Company" in rendered
