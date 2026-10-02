"""Statement preview view-model (pure, no Streamlit)."""

from __future__ import annotations

from datetime import date
from typing import ClassVar

from backend.services.financial_statement_parser import StatementType
from backend.services.ui_adapter import render_statement_preview


class _Record:
    form_type = "10-K"
    filing_date = date(2025, 10, 31)
    period_of_report = date(2025, 9, 27)
    sec_url = "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/"


class _Statement:
    source = "fallback"
    extraction_warnings: ClassVar[list] = ["no anchor matched"]

    class _Line:
        label = "Total assets"
        current = "$364,980"
        prior = "$352,583"
        indent_level = 0

    lines: ClassVar[list] = [_Line()]

    def as_rows(self):
        return [{"Line item": "Total assets", "September 27, 2025": "$364,980"}]


def _loader_ok(record, statement_type):
    return _Statement()


def _loader_none(record, statement_type):
    return None


def test_valid_statement_returns_header_rows_and_caption():
    preview = render_statement_preview(
        _Record(), StatementType.BALANCE_SHEET, _loader_ok
    )
    assert preview["ok"] is True
    assert "10-K filed 2025-10-31" in preview["header"]
    assert preview["table_rows"]
    assert "Statement: Balance Sheet" in preview["caption"]
    assert "Extraction: fallback" in preview["caption"]
    assert preview["warnings"] == ["no anchor matched"]
    assert preview["message"] is None


def test_missing_statement_returns_the_warning_and_the_url():
    preview = render_statement_preview(
        _Record(), StatementType.INCOME_STATEMENT, _loader_none
    )
    assert preview["ok"] is False
    assert preview["table_rows"] == []
    assert "does not contain a Income Statement statement" in preview["message"]
    assert preview["sec_url"].startswith("https://www.sec.gov/")


def test_caption_includes_the_statement_type_label():
    for statement_type in StatementType:
        preview = render_statement_preview(_Record(), statement_type, _loader_ok)
        assert f"Statement: {statement_type.label}" in preview["caption"]


def test_header_handles_a_missing_period():
    class _NoPeriod(_Record):
        period_of_report = None

    preview = render_statement_preview(
        _NoPeriod(), StatementType.BALANCE_SHEET, _loader_ok
    )
    assert "period —" in preview["header"]
