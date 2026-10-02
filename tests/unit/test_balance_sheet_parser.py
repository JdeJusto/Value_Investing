"""Balance sheet extraction: fallback, anchors, malformed input."""

from __future__ import annotations

from pathlib import Path

from backend.services.balance_sheet_parser import BalanceSheetParser

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "filings"


def _parse(name: str):
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BalanceSheetParser().parse(html)


def test_real_10k_uses_the_content_fallback():
    sheet = _parse("aapl_10k.html")
    assert sheet is not None
    assert sheet.source == "fallback"
    assert sheet.extraction_warnings, "the fallback must be reported"


def test_real_10k_preserves_the_filed_formatting():
    sheet = _parse("aapl_10k.html")
    assert sheet is not None
    labels = [line.label for line in sheet.lines]
    assert "Total assets" in labels
    cash = next(
        line for line in sheet.lines if line.label == "Cash and cash equivalents"
    )
    assert cash.current == "$29,943"  # exactly as filed, not 29943
    assert cash.prior == "$29,965"
    total = next(line for line in sheet.lines if line.label == "Total assets")
    assert total.current == "$364,980"
    assert len(sheet.lines) >= 20


def test_period_header_is_captured():
    sheet = _parse("aapl_10k.html")
    assert sheet is not None
    assert sheet.header_periods == ("September 28, 2024", "September 30, 2023")


def test_anchor_path_wins_when_present():
    sheet = _parse("legacy_10k.html")
    assert sheet is not None
    assert sheet.source == "anchors"
    assert sheet.extraction_warnings == []
    assert sheet.header_periods == ("December 31, 2015", "December 31, 2014")
    total = next(line for line in sheet.lines if line.label == "Total assets")
    assert total.current == "$10,000"
    assert total.prior == "$9,000"


def test_malformed_html_returns_none_without_raising():
    assert _parse("malformed.html") is None
    assert BalanceSheetParser().parse("") is None
    assert BalanceSheetParser().parse("<html><body>") is None
    assert BalanceSheetParser().parse("not html at all <<<>>>") is None


def test_as_rows_renders_labels_and_periods():
    sheet = _parse("legacy_10k.html")
    assert sheet is not None
    rows = sheet.as_rows()
    assert rows
    assert "Total assets" in rows[-2]["Line item"]
    assert rows[-2]["December 31, 2015"] == "$10,000"


def test_parser_never_raises_on_binary_garbage():
    assert BalanceSheetParser().parse("\x00\x01\x02binary") is None
