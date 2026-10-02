# Filings extraction (planned — not implemented)

Reference for the next session: extracting sections from 10-K/10-Q documents
and showing them inline. **Nothing here is built yet**; the current feature
only links out to SEC EDGAR.

## Goal

Extract and display specific sections of a filing:

- Balance sheet
- Income statement
- Cash flow statement
- Risk factors summary
- MD&A (management discussion and analysis)
- Item 7 / Item 8 (10-K)
- Part I Item 2 (10-Q)

## Approach

Three viable options, in increasing complexity:

1. **Anchor extraction from HTML**
   - SEC primary documents are HTML; most sections carry stable anchors
     (e.g. `<a name="s_balance_sheet">`).
   - Parse the HTML, locate the section, extract the surrounding table/text.
   - Pros: fast, no ML, no new dependencies beyond an HTML parser.
   - Cons: fragile — filings vary; anchors are not guaranteed.

2. **Inline XBRL (iXBRL) parsing**
   - Modern filings embed XBRL tags in the HTML; every financial fact is
     tagged with a concept (`AssetsCurrent`, `Revenues`, …).
   - Extract by concept instead of by position.
   - Pros: robust and semantically rich.
   - Cons: needs an iXBRL parser. Note: Financial-DataBase already stores the
     same facts (`financial_facts`), so for **numbers** the extraction may be
     unnecessary — this option matters for the *narrative* sections.

3. **PDF/text extraction + NLP**
   - Download, extract text, use regex or an LLM for the narrative parts.
   - Pros: handles any format.
   - Cons: fragile, slow, costly; hard to make deterministic.

## Recommended order

Start with **(1) for the balance sheet only** — it is the most standardized
section and the anchors are most reliable there. If the anchors prove too
fragile, move to (2). Keep (3) out of the critical path.

## Data flow (future)

```text
SEC EDGAR (HTML) → fetch once → cache in data/raw/filings/
    → parser (per section) → normalized dict
    → FilingSectionExtractor → UI tab
```

## Considerations

- **Cache the raw HTML locally** (`data/raw/filings/<accession>.htm`) so the
  UI never re-downloads on every load; the directory is already gitignored.
- **Respect the SEC user-agent requirement** — the existing clients already
  send a descriptive `SEC_USER_AGENT`; reuse that path.
- **Fetch each filing at most once per session** (an in-memory cache with a
  long TTL, same pattern as the filings list).
- **Always keep the raw link** as a fallback ("view on SEC EDGAR"), so a
  failed extraction never blocks the user.
- Do **not** add `requests`/`httpx` to the UI layer: extraction belongs in a
  service (`FilingSectionExtractor`) and the UI only renders its result.
- Deterministic output only: the same document must always yield the same
  section text (no LLM in the default path).

## Where it plugs in

- `backend/services/filing_service.py` already resolves the document URL
  (`sec_document_url`, falling back to the index URL).
- A future `backend/services/filing_extractor.py` would take a
  `FilingRecord`, fetch once, parse, and return a
  `dict[str, str | None]` of section → text.
- The Filings tab in `ui/pages/02_analysis.py` already renders a selected-row
  preview: that is where the extracted sections would appear, replacing the
  current "full document preview coming soon" note.
