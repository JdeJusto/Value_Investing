"""NarrativeExtractor: TOC anchor, fallback, normalization, cache."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from backend.services.narrative_extractor import (
    INCORPORATION_WARNING,
    NarrativeExtractor,
    SectionType,
    _is_likely_incorporation,
    load_narrative_section,
    narrative_cache_path,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "filings"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_real_10k_risk_factors_uses_the_toc_anchor():
    section = NarrativeExtractor().extract(
        _html("aapl_10k_risk_factors.html"), SectionType.RISK_FACTORS, "10-K"
    )
    assert section is not None
    assert section.source == "toc_anchor"
    assert section.text
    assert section.word_count > 1000
    assert (
        "The Company" in section.text
    )  # real body text (the heading is de-duplicated)


def test_real_10k_md_a_extracts():
    section = NarrativeExtractor().extract(
        _html("aapl_10k_md_a.html"), SectionType.MD_A, "10-K"
    )
    assert section is not None
    assert section.source == "toc_anchor"
    assert section.word_count > 500
    assert "Management" in section.text


def test_10q_signatures_are_used():
    section = NarrativeExtractor().extract(
        _html("aapl_10q_risk_factors.html"), SectionType.RISK_FACTORS, "10-Q"
    )
    assert section is not None
    assert section.source == "toc_anchor"
    assert section.text


def test_text_search_fallback_without_anchors():
    body = " ".join(
        f"We face risk number {index} in our business operations every day."
        for index in range(1, 12)
    )
    html = (
        "<html><body><div>Item 1A. Risk Factors</div>"
        f"<div>{body}</div>"
        "<div>Item 1B. Unresolved Staff Comments</div>"
        "<div>This should not be included in the extraction at all.</div>"
        "</body></html>"
    )
    section = NarrativeExtractor().extract(html, SectionType.RISK_FACTORS, "10-K")
    assert section is not None
    assert section.source == "text_search"
    assert "risk number 1" in section.text
    assert "should not be included" not in section.text


def test_toc_without_content_returns_none():
    assert (
        NarrativeExtractor().extract(
            _html("toc_only.html"), SectionType.RISK_FACTORS, "10-K"
        )
        is None
    )


def test_malformed_html_returns_none():
    extractor = NarrativeExtractor()
    assert extractor.extract("", SectionType.RISK_FACTORS, "10-K") is None
    assert extractor.extract("<html><body>", SectionType.MD_A, "10-K") is None
    assert extractor.extract("\x00\x01binary", SectionType.MD_A, "10-K") is None


def test_unknown_section_type_raises():
    with pytest.raises(ValueError, match="unknown section type"):
        NarrativeExtractor().extract("<html></html>", "risk", "10-K")  # type: ignore[arg-type]


def test_text_is_normalized_with_paragraph_breaks():
    section = NarrativeExtractor().extract(
        _html("aapl_10k_risk_factors.html"), SectionType.RISK_FACTORS, "10-K"
    )
    assert section is not None
    text = section.text
    assert "<" not in text and ">" not in text  # no HTML tags
    assert "\n\n" in text  # paragraphs preserved
    assert text == text.strip()
    assert section.word_count == len(text.split())


def test_truncation_adds_a_warning(monkeypatch):
    import backend.services.narrative_extractor as module

    monkeypatch.setattr(module, "MAX_SECTION_BYTES", 200)
    section = NarrativeExtractor().extract(
        _html("aapl_10k_risk_factors.html"), SectionType.RISK_FACTORS, "10-K"
    )
    assert section is not None
    assert len(section.text) == 200
    assert any("truncated" in warning for warning in section.extraction_warnings)


class _Record:
    ticker = "AAPL"
    cik = "0000320193"
    accession_number = "0000320193-25-000079"
    primary_document = "aapl.htm"
    form_type = "10-K"
    filing_date = date(2025, 10, 31)
    period_of_report = date(2025, 9, 27)
    sec_url = "https://www.sec.gov/"


def test_cache_roundtrip_avoids_re_extraction(tmp_path, monkeypatch):
    monkeypatch.delenv("VI_DEMO", raising=False)
    html = _html("aapl_10k_risk_factors.html")

    class _Fetcher:
        calls = 0

        def fetch_html(self, *args, **kwargs):
            type(self).calls += 1
            return html

    fetcher = _Fetcher()
    first = load_narrative_section(
        _Record(), SectionType.RISK_FACTORS, fetcher=fetcher, cache_dir=tmp_path
    )
    assert first is not None and first.word_count > 1000

    class _Boom:
        def extract(self, *args, **kwargs):
            raise AssertionError("the extractor must not run on a cache hit")

    monkeypatch.setattr(
        "backend.services.narrative_extractor.NarrativeExtractor", _Boom
    )
    second = load_narrative_section(
        _Record(), SectionType.RISK_FACTORS, fetcher=fetcher, cache_dir=tmp_path
    )
    assert second is not None and second.text == first.text
    assert fetcher.calls == 1  # neither re-fetched nor re-parsed


def test_text_does_not_start_with_the_duplicated_title():
    section = NarrativeExtractor().extract(
        _html("aapl_10k_risk_factors.html"), SectionType.RISK_FACTORS, "10-K"
    )
    assert section is not None
    first_line = section.text.split("\n\n")[0]
    assert "Item 1A" not in first_line


def test_is_likely_incorporation_flags_short_reference_text():
    # JPM-like stub: short, and points at pages in the annual report.
    assert _is_likely_incorporation(
        "The MD&A appears on pages 46-160. Refer to the annual report.", 42
    )


def test_is_likely_incorporation_ignores_long_sections():
    # Over the 500-word threshold even when the phrases are present.
    assert not _is_likely_incorporation("Refer to the annual report. " * 100, 600)


def test_is_likely_incorporation_ignores_short_plain_text():
    assert not _is_likely_incorporation(
        "We face risks from competition, regulation and macroeconomic conditions.", 14
    )


def test_incorporation_stub_gets_a_warning():
    section = NarrativeExtractor().extract(
        _html("incorporation_stub.html"), SectionType.MD_A, "10-K"
    )
    assert section is not None
    assert section.source == "toc_anchor"
    assert section.word_count < 500
    assert "refer to" in section.text.lower()
    assert INCORPORATION_WARNING in section.extraction_warnings


def test_full_sections_get_no_incorporation_warning():
    section = NarrativeExtractor().extract(
        _html("aapl_10k_md_a.html"), SectionType.MD_A, "10-K"
    )
    assert section is not None
    assert INCORPORATION_WARNING not in section.extraction_warnings


def test_stale_cache_version_triggers_a_re_extraction(tmp_path, monkeypatch):
    """A section cached before a parser-version bump must be re-extracted.

    Guarantees behavioral changes (e.g. the incorporation warning) reach
    sections that were already cached under an older version.
    """
    from backend.services.narrative_extractor import NARRATIVE_PARSER_VERSION

    monkeypatch.delenv("VI_DEMO", raising=False)

    class _Fetcher:
        calls = 0

        def fetch_html(self, *args, **kwargs):
            type(self).calls += 1
            return _html("aapl_10k_risk_factors.html")

    fetcher = _Fetcher()
    load_narrative_section(
        _Record(), SectionType.RISK_FACTORS, fetcher=fetcher, cache_dir=tmp_path
    )
    assert fetcher.calls == 1
    path = narrative_cache_path(
        tmp_path,
        "0000320193",
        "0000320193-25-000079",
        "aapl.htm",
        SectionType.RISK_FACTORS,
    )
    payload = path.read_text(encoding="utf-8").replace(
        f'"version": {NARRATIVE_PARSER_VERSION}', '"version": 0'
    )
    path.write_text(payload, encoding="utf-8")

    section = load_narrative_section(
        _Record(), SectionType.RISK_FACTORS, fetcher=fetcher, cache_dir=tmp_path
    )
    assert section is not None and section.word_count > 1000
    assert fetcher.calls == 2  # a stale cache must not be served as-is
