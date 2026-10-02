# Narrative section extraction (v0.8.0)

Extract Risk Factors (Item 1A) and MD&A (Item 7 in a 10-K, Item 2 in a 10-Q)
as plain text from filings and show them in the CLI and the UI.

## Scope — pure extraction, NO LLM

- No summarization, no NLP, no external APIs, no new dependencies.
- The user reads the source text directly.
- LLM summarization is deferred to v0.9.0+ (optional, behind a flag).

## What the real filings look like (measured)

Inspected on the cached documents (`data/raw/filings/`):

| Observation | Consequence |
| --- | --- |
| The **first** "Item 1A." hit is the **table of contents** (an `<a href="#i7bf…">Item 1A.</a>` row), not the section | A naive text search finds the TOC; the extractor must follow the anchor |
| Sections **do carry ids** (`id="i7bfbfbe54b9647b1b4ba4ff4e0aba09d_52"`) that the TOC links to | Start the section at the element whose `id` matches the TOC's `href` |
| Modern 10-Ks have **no `<p>` and no `<ul>`** (0 of each in AAPL's 1.4 MB 10-K) — everything is styled `<div>` blocks | Paragraph extraction must use `<div>`/`<br>` structure, not `<p>`/`<li>` |
| Headings are not `<h1>`–`<h4>`; they are styled divs/anchors | Heading detection cannot rely on heading tags alone |
| 10-Q: "Item 1A." → "Item 2."/"Item 3."; MD&A is "Item 2." → "Item 3." | Signatures are per form type |

## Detection strategy (revised for the real markup)

1. Parse with BeautifulSoup (lxml).
2. Find the **TOC anchor** for the start signature: the first `<a>` whose text
   starts with e.g. "Item 1A." and whose `href` begins with `#`.
3. Resolve the target: the element with that `id` is the section start.
4. Walk forward (document order) collecting block text until a block whose text
   starts with an end signature ("Item 1B." / "Item 2." for a 10-K risk
   factors; "Item 8." for MD&A).
5. **Fallback** (`source="text_search"`) when there is no TOC/anchor: search the
   raw text for the start signature, ignoring the first hit when it looks like a
   TOC row (short line ending in a page number or inside an `<a href="#…">`).
6. If neither path finds the section → return `None` with a warning. Never
   fabricate text.

Text normalisation: strip tags, collapse whitespace inside each block, join
blocks with `\n` (blank line between top-level blocks). The filing's block
structure is preserved; nothing is collapsed into a single paragraph.

## Structure

```python
@dataclass(frozen=True)
class NarrativeSection:
    section_type: str  # "risk_factors" | "md_a"
    filing_date: date
    period_end: date | None
    form_type: str
    title: str
    text: str
    word_count: int
    source: str  # "heading" | "text_search"
    extraction_warnings: list[str]
```

## Signatures

| Section | 10-K start → end | 10-Q start → end |
| --- | --- | --- |
| risk_factors | Item 1A → Item 1B / Item 2 | Item 1A → Item 2 / Item 3 |
| md_a | Item 7 → Item 8 | Item 2 → Item 3 |

## Cache

`<doc>.<section_type>.json` under `data/raw/filings/`, next to the statement
caches, invalidated by `NARRATIVE_PARSER_VERSION` (kept separate from the
  statement parser's `PARSER_VERSION` so one bump does not invalidate the
  other's cache).

## Limits

- Text is capped at 200 KB; beyond that the extraction is almost certainly
  wrong (navigation captured instead of the section) and a warning is added.
- Navigation stripping is best-effort, not perfect.
- No comparison between filings (which risks are new this quarter).
- The section boundaries rely on the filing's own item numbering; a filer that
  omits the end item falls back to the next top-level heading.

## Incorporation by reference

Some SEC filings do not include certain sections inline. Instead, the section
points to another section, an exhibit, or another document (common for MD&A in
some filers, and for proxy content). When the extractor finds a section
shorter than 500 words (`INCORPORATION_WORD_THRESHOLD`) containing phrases
like "incorporated by reference" / "refer to" (see
`INCORPORATION_PHRASES`), it still returns the text but adds a warning to
`extraction_warnings` (`INCORPORATION_WARNING`).

Example: JPM's 10-K MD&A is a 158-word stub that points to the full MD&A
included elsewhere ("appears on pages 46-160 of the annual report"). The
extractor returns the stub text with the warning rather than silently
producing a misleading short "section". The CLI prints the warning before the
text; the UI shows it as an `st.info` banner with a link to the filing.

Auto-following the reference (extracting the referenced content) is NOT
implemented. It would require parsing exhibit indices and fetching additional
documents. This is deferred (see `docs/backlog.md`).
