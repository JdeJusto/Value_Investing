"""`filing-section` — extract narrative sections (Risk Factors, MD&A) as plain text.

Pure extraction via the TOC-anchor strategy (see ``docs/narrative_extraction.md``):
the section start is the element the table of contents links to, and the
content is read as-is (no LLM, no summarization). Default prints the first
1000 words so the terminal is not flooded; ``--full`` prints everything
(the extractor still caps at 200 KB).
"""

from __future__ import annotations

from backend.app.cli import add_demo_argument
from cli.formatters import print_header, red, yellow

_SOURCE_LABELS = {
    "toc_anchor": "TOC anchor",
    "text_search": "Text search",
}


def register(subparsers):
    p = subparsers.add_parser(
        "filing-section",
        help="Extract a narrative section (Risk Factors, MD&A) from a filing",
        description=(
            "Extract a narrative section (Risk Factors, MD&A) from a 10-K/10-Q "
            "as plain text via the TOC-anchor strategy."
        ),
    )
    p.add_argument("ticker", help="Ticker (e.g. AAPL)")
    p.add_argument(
        "--type",
        default="risk_factors",
        choices=["risk_factors", "md_a"],
        help="Section type (default: risk_factors)",
    )
    p.add_argument("--accession", help="Specific accession number")
    p.add_argument("--form", help="Form type filter (default: 10-K, 10-Q, 20-F, 40-F)")
    p.add_argument("--year", type=int, help="Fiscal year filter")
    p.add_argument(
        "--word-limit",
        type=int,
        default=1000,
        help="Cap the number of printed words (default: 1000)",
    )
    p.add_argument(
        "--full",
        action="store_true",
        help="Print the entire section (the extractor still caps at 200 KB)",
    )
    add_demo_argument(p)
    p.set_defaults(func=_run)
    return p


def _run(args):
    from backend.services.filing_service import DEFAULT_FORM_TYPES, FilingService
    from backend.services.narrative_extractor import (
        INCORPORATION_WARNING,
        SectionType,
        load_narrative_section,
    )

    section_type = SectionType(args.type)
    ticker = args.ticker.upper().strip()
    service = FilingService()
    if args.accession:
        candidates = [
            record
            for record in service.list_filings(ticker, form_types=None)
            if record.accession_number == args.accession
        ]
    else:
        candidates = service.list_filings(
            ticker,
            form_types=[args.form.upper()] if args.form else list(DEFAULT_FORM_TYPES),
            fiscal_years=[args.year] if args.year else None,
        )
    if not candidates:
        print(yellow(f"No hay filings de {ticker} que coincidan con los filtros."))
        return

    record = candidates[0]
    section = load_narrative_section(record, section_type)
    header = (
        f"{section_type.label} — {ticker} {record.form_type} filed "
        f"{record.filing_date.isoformat()}"
    )
    if record.period_of_report:
        header += f" (period {record.period_of_report.isoformat()})"
    print_header(header)

    if section is None:
        print(red(f"No se pudo extraer {section_type.label} de este documento."))
        if record.sec_url:
            print(f"  Original: {record.sec_url}")
        return

    print()
    print(f"  Word count : {section.word_count:,}")
    print(f"  Source     : {_SOURCE_LABELS.get(section.source, section.source)}")
    print(f"  Title      : {section.title}")

    if any(w == INCORPORATION_WARNING for w in section.extraction_warnings):
        print()
        print(yellow(f"⚠️  {INCORPORATION_WARNING}"))
        print("    See the original filing on SEC EDGAR:")
        if record.sec_url:
            print(f"    {record.sec_url}")

    words = section.text.split()
    total = len(words)
    truncated = not args.full and total > args.word_limit
    if truncated:
        shown = " ".join(words[: args.word_limit])
    else:
        shown = section.text
        truncated = False

    print()
    print("─" * 72)
    if truncated:
        print(f"[first {args.word_limit} words of {total:,}]")
        print()
    print(shown)
    if truncated:
        print()
        print("... (truncated; use --full to see everything, or --word-limit N)")
    if record.sec_url:
        print(f"\n  Original: {record.sec_url}")
