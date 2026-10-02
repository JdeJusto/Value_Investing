"""Extract narrative sections (Risk Factors, MD&A) from filings as plain text.

Strategy, informed by the real markup (see ``docs/narrative_extraction.md``):

1. **TOC anchor** — the first "Item 1A." hit in a filing is the *table of
   contents*; the section starts at the element whose ``id`` the TOC link
   points to. ``source="toc_anchor"``.
2. **Text search** fallback — no anchor: search the text for the start
   signature and cut at the end signature. ``source="text_search"``.
3. Modern 10-Ks have **no ``<p>``/``<li>``**: content lives in styled
   ``<div>`` blocks with ``<br>`` line breaks, so text is collected from
   leaf text blocks and joined with blank lines.

Pure extraction: no LLM, no summarization, no network. Never raises on
malformed HTML; returns ``None`` (never fabricated text) when the section
is not found.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

#: Shared with the statement parser: bump when extraction output changes.
PARSER_VERSION = 1
MAX_SECTION_BYTES = 200_000
MIN_BLOCK_WORDS = 3


class SectionType(str, Enum):
    RISK_FACTORS = "risk_factors"
    MD_A = "md_a"

    @property
    def label(self) -> str:
        return {
            SectionType.RISK_FACTORS: "Risk Factors",
            SectionType.MD_A: "MD&A",
        }[self]


SECTION_SIGNATURES: dict[str, dict[str, dict[str, list[str]]]] = {
    "10-K": {
        "risk_factors": {
            "toc_patterns": ["Item 1A", "Item 1A."],
            "end_headings": ["Item 1B", "Item 1B.", "Item 2", "Item 2."],
            "title_patterns": ["Risk Factors"],
        },
        "md_a": {
            "toc_patterns": ["Item 7", "Item 7."],
            "end_headings": ["Item 8", "Item 8."],
            "title_patterns": ["Management's Discussion", "MD&A"],
        },
    },
    "10-Q": {
        "risk_factors": {
            "toc_patterns": ["Item 1A", "Item 1A."],
            "end_headings": ["Item 2", "Item 2.", "Item 3", "Item 3."],
            "title_patterns": ["Risk Factors"],
        },
        "md_a": {
            "toc_patterns": ["Item 2", "Item 2."],
            "end_headings": ["Item 3", "Item 3."],
            "title_patterns": ["Management's Discussion", "MD&A"],
        },
    },
}


def _signature(form_type: str, section_type: SectionType) -> dict[str, list[str]]:
    """Signatures for a form; 10-K/10-Q fall back to each other's shape."""
    forms = SECTION_SIGNATURES
    key = form_type.upper() if form_type else ""
    if key not in forms:
        key = "10-Q" if "10-Q" in key.upper() else "10-K"
    return forms[key][section_type.value]


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _starts_with_any(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    return any(lowered.startswith(pattern.lower()) for pattern in patterns)


@dataclass(frozen=True)
class NarrativeSection:
    section_type: str
    filing_date: date | None
    period_end: date | None
    form_type: str
    title: str
    text: str
    word_count: int
    source: str
    extraction_warnings: list[str] = field(default_factory=list)


class NarrativeExtractor:
    """HTML → :class:`NarrativeSection` (None when nothing usable is found)."""

    def extract(
        self,
        html: str,
        section_type: SectionType,
        form_type: str = "10-K",
        filing_date: date | None = None,
        period_end: date | None = None,
    ) -> NarrativeSection | None:
        if not isinstance(section_type, SectionType):
            try:
                section_type = SectionType(section_type)
            except ValueError as exc:
                raise ValueError(
                    f"unknown section type {section_type!r}; expected one of "
                    f"{[t.value for t in SectionType]}"
                ) from exc
        if not html:
            return None
        try:
            from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(html, "lxml")
        except Exception:  # noqa: BLE001 — malformed input must not raise
            return None

        signature = _signature(form_type, section_type)
        elements = soup.find_all(True)

        start_index, title, source = self._find_start(soup, elements, signature)
        if start_index is None:
            return None

        paragraphs = self._collect(elements, start_index, signature["end_headings"])
        text = "\n\n".join(paragraphs).strip()
        if not text or len(text.split()) < 10:
            # A handful of words is a fragment (navigation), not a section.
            return None

        extraction_warnings: list[str] = []
        if len(text) > MAX_SECTION_BYTES:
            text = text[:MAX_SECTION_BYTES]
            extraction_warnings.append(
                "section truncated at 200 KB; likely includes navigation"
            )

        return NarrativeSection(
            section_type=section_type.value,
            filing_date=filing_date,
            period_end=period_end,
            form_type=form_type,
            title=title,
            text=text,
            word_count=len(text.split()),
            source=source,
            extraction_warnings=extraction_warnings,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _find_start(
        soup: Any, elements: list, signature: dict[str, list[str]]
    ) -> tuple[int | None, str, str]:
        """(index of the start element, title, source) — TOC anchor first."""
        for anchor in soup.find_all("a"):
            text = _clean(anchor.get_text(" ", strip=True))
            if not _starts_with_any(text, signature["toc_patterns"]):
                continue
            href = str(anchor.get("href") or "")
            if not href.startswith("#"):
                continue
            target = soup.find(id=href[1:])
            if target is None:
                continue
            index = next(
                (i for i, element in enumerate(elements) if element is target), None
            )
            if index is not None:
                title = text
                # Prefer the fuller TOC label ("Item 1A. Risk Factors").
                for pattern in signature["title_patterns"]:
                    for anchor_text in (text,):
                        if pattern.lower() not in anchor_text.lower():
                            break
                return index, title, "toc_anchor"

        # Fallback: the first start signature that is NOT inside a TOC table
        # and is a leaf text block (real section headings are leaf divs; the
        # body/table containers are not, and would collect only fragments).
        for index, element in enumerate(elements):
            text = _clean(element.get_text(" ", strip=True))
            if len(text) > 200 or not _starts_with_any(text, signature["toc_patterns"]):
                continue
            if element.find_parent("table") is not None:
                continue  # TOC rows live in tables
            if element.find(["div", "table", "p"]) is not None:
                continue  # a container, not a heading
            return index, text, "text_search"
        return None, "", ""

    @staticmethod
    def _collect(
        elements: list, start_index: int, end_headings: list[str]
    ) -> list[str]:
        """Leaf text blocks between the start element and the end heading."""
        paragraphs: list[str] = []
        for element in elements[start_index + 1 :]:
            text = _clean(element.get_text(" ", strip=True))
            if not text:
                continue
            if len(text) <= 120 and _starts_with_any(text, end_headings):
                break
            # Only leaf blocks (no block children with their own text) to
            # avoid duplicating nested div content.
            if element.find(["div", "table", "p"]) is not None:
                continue
            if len(text.split()) < MIN_BLOCK_WORDS:
                continue  # navigation crumbs / page numbers
            paragraphs.append(text)
        return paragraphs


# ---------------------------------------------------------------------------
# Orchestration: demo fixture, cache, or fetch + extract
# ---------------------------------------------------------------------------
def _demo_section_path(record: Any, section_type: SectionType) -> Path:
    from backend.services.demo_mode import DEMO_ROOT

    return DEMO_ROOT / "sections" / f"{record.ticker}_{section_type.value}.json"


def _section_from_payload(
    payload: dict, section_type: SectionType, record: Any
) -> NarrativeSection:
    return NarrativeSection(
        section_type=payload.get("section_type", section_type.value),
        filing_date=getattr(record, "filing_date", None),
        period_end=getattr(record, "period_of_report", None),
        form_type=payload.get("form_type", getattr(record, "form_type", "")),
        title=payload.get("title", ""),
        text=payload.get("text", ""),
        word_count=int(payload.get("word_count") or 0),
        source=payload.get("source", "demo"),
        extraction_warnings=list(payload.get("extraction_warnings", [])),
    )


def narrative_cache_path(
    cache_dir: str | Path,
    cik: str,
    accession: str,
    document: str | None,
    section_type: SectionType,
) -> Path:
    cik_no_zeros = str(int(cik)) if str(cik).isdigit() else str(cik)
    name = document or "document.htm"
    return (
        Path(cache_dir)
        / cik_no_zeros
        / accession.replace("-", "")
        / (f"{name}.{section_type.value}.json")
    )


def _read_section_cache(path: Path) -> NarrativeSection | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if int(payload.get("version", 0)) != PARSER_VERSION:
        return None
    record = type("_R", (), {})()
    record.filing_date = (
        date.fromisoformat(payload["filing_date"])
        if payload.get("filing_date")
        else None
    )
    record.period_of_report = (
        date.fromisoformat(payload["period_end"]) if payload.get("period_end") else None
    )
    record.form_type = payload.get("form_type")
    try:
        section_type = SectionType(payload["section_type"])
    except (KeyError, ValueError):
        return None
    return _section_from_payload(payload, section_type, record)


def _write_section_cache(path: Path, section: NarrativeSection) -> None:
    payload = {
        "version": PARSER_VERSION,
        "section_type": section.section_type,
        "filing_date": section.filing_date.isoformat() if section.filing_date else None,
        "period_end": section.period_end.isoformat() if section.period_end else None,
        "form_type": section.form_type,
        "title": section.title,
        "text": section.text,
        "word_count": section.word_count,
        "source": section.source,
        "extraction_warnings": section.extraction_warnings,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except OSError:
        pass


def clear_section_cache(
    cache_dir: str | Path = "data/raw/filings",
    section_type: SectionType | None = None,
) -> int:
    """Delete cached narrative sections (JSON only); the HTML is kept."""
    names = (
        [section_type.value, "risk_factors", "md_a"]
        if section_type is None
        else [section_type.value]
    )
    removed = 0
    for name in set(names):
        for path in Path(cache_dir).rglob(f"*.{name}.json"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
    return removed


def load_narrative_section(
    record: Any,
    section_type: SectionType,
    fetcher: Any = None,
    cache_dir: str | Path = "data/raw/filings",
) -> NarrativeSection | None:
    """Section for a filing record: demo fixture → JSON cache → fetch+extract."""
    from backend.services.demo_mode import is_demo

    if is_demo():
        path = _demo_section_path(record, section_type)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        section = _section_from_payload(payload, section_type, record)
        return section if section.text else None

    cik = getattr(record, "cik", "")
    accession = getattr(record, "accession_number", "")
    document = getattr(record, "primary_document", None)
    cache_path = narrative_cache_path(cache_dir, cik, accession, document, section_type)
    cached = _read_section_cache(cache_path)
    if cached is not None:
        return cached

    if fetcher is None:
        from backend.services.filing_fetcher import FilingFetcher

        fetcher = FilingFetcher(cache_dir=cache_dir)
    html = fetcher.fetch_html(cik, accession, document)
    if html is None:
        return None
    section = NarrativeExtractor().extract(
        html,
        section_type,
        form_type=getattr(record, "form_type", "10-K") or "10-K",
        filing_date=getattr(record, "filing_date", None),
        period_end=getattr(record, "period_of_report", None),
    )
    if section is not None:
        _write_section_cache(cache_path, section)
    return section
