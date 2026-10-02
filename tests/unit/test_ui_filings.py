"""The Analysis page's Filings tab: renders, filters and SEC links (demo)."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).resolve().parents[2] / "ui" / "pages" / "02_analysis.py"


def _run(monkeypatch) -> AppTest:
    monkeypatch.setenv("VI_DEMO", "1")
    at = AppTest.from_file(str(PAGE), default_timeout=120)
    at.run()
    # The page renders the tabs only after Analyze (ticker defaults to AAPL).
    analyze = next(button for button in at.button if button.label == "Analyze")
    analyze.click()
    at.run()
    return at


def test_filings_tab_exists_and_renders_in_demo(monkeypatch):
    at = _run(monkeypatch)
    assert not at.exception, at.exception
    assert "Filings" in [tab.label for tab in at.tabs]


def test_filters_exist(monkeypatch):
    at = _run(monkeypatch)
    assert not at.exception
    labels = [widget.label for widget in at.multiselect]
    assert "Form type" in labels
    assert "Fiscal year" in labels
    assert any(box.label == "Include amendments" for box in at.checkbox)


def _filings_frame(at: AppTest):
    """The filings dataframe (the page renders several tables)."""
    for element in at.dataframe:
        frame = element.value
        if "Open on SEC" in list(frame.columns):
            return frame
    raise AssertionError("the filings table did not render")


def test_summary_and_link_column(monkeypatch):
    at = _run(monkeypatch)
    assert not at.exception
    captions = " ".join(caption.value for caption in at.caption)
    assert "filings match your filters" in captions
    frame = _filings_frame(at)
    assert frame["Open on SEC"].str.startswith("https://www.sec.gov/").all()


def test_demo_fixture_has_real_accessions(monkeypatch):
    at = _run(monkeypatch)
    assert not at.exception
    frame = _filings_frame(at)
    # Real accessions snapshotted from Financial-DataBase, not placeholders.
    assert frame["Accession"].str.len().min() >= 15
    assert frame["FY"].notna().all()
