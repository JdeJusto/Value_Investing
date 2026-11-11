# Book notes — reference map (v0.29.0–v0.32.0)

Curated notes extracted from the reference books available on this machine.
The full extracted text lives in the gitignored `_raw/` directory; only these
notes are versioned.

## Mapping

| Methodology | Reference book | Found? | Notes |
|---|---|---|---|
| `graham` | *The Intelligent Investor* (Graham, 4th revised ed., 1973) | yes | `the-intelligent-investor.md` |
| `graham_dodd` | *Security Analysis* (Graham & Dodd, 1934) | yes | `security-analysis.md` |
| `fisher_quantitative_subset` | *Common Stocks and Uncommon Profits* (Fisher, 1958) | yes | `common-stocks-and-uncommon-profits.md` |
| `buffett_clark` | *Warren Buffett and the Interpretation of Financial Statements* (Mary Buffett & David Clark, 2001) | yes | `buffett-clark-financial-statements.md` |
| `buffett_classic` | *The Warren Buffett Way* (Hagstrom) / Berkshire letters | **no** | `the-warren-buffett-way.md` (public knowledge) |
| `lynch_garp` | *One Up on Wall Street* / *Beating the Street* (Lynch) | **no** | `one-up-on-wall-street.md` (public knowledge) |
| `marks` | *The Most Important Thing* (Marks, 2011) | **no** | `the-most-important-thing.md` (public knowledge) |
| `greenblatt` | *The Little Book That Beats the Market* (Greenblatt, 2005) | **no** | `the-little-book-that-beats-the-market.md` (public knowledge) |

## Source locations

- `~/Descargas/The Intelligent Investor-Graham.pdf` (English)
- `~/Descargas/EL INVERSOR INTELIGENTE - BENJAMIN GRAHAM.pdf` (Spanish)
- `~/Descargas/Security-Analysis-en-espanol.pdf`
- `~/Descargas/Common Stocks and Uncommon Profits - Philip A. Fisher.pdf`
- `~/Descargas/Mary Buffett & David Clark - Warren Buffett y la interpretacion de estados financieros.pdf`
- Curated extractions: `~/books_analysis/source`, `~/books_analysis/extracted`,
  `~/books_analysis/notes`.

## Extraction tools

- `pdftotext` (poppler-utils) is available and was used for the PDFs.
- `ebook-convert` / `pandoc` are not installed; no EPUB extraction was needed.
- `_raw/` contains the extracted text copied from `~/books_analysis/extracted/`.

## Citation policy

Every rule in `docs/<methodology>_rules.md` cites the book and page/chapter
when the book was available. Rules that are public-knowledge derivations say
so explicitly. A missing book is never cited as if it had been read.
