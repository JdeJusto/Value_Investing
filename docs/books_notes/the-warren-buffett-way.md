# The Warren Buffett Way (Hagstrom, 1994/2004)

> **Methodology:** `buffett_classic`
> **Availability:** **not found in ~/Descargas or ~/books_analysis**. The rules are public-knowledge
> approximations or prior implementation rules; every rule in
> `docs/buffett_classic_rules.md` is labelled accordingly. No claim of book/page
> fidelity is made for this methodology.

## Why this file exists

The sprint (v0.29.0–v0.32.0) asks for book-referenced rules. The reference
book was searched in `~/Descargas`, `~/Downloads`, `~/Descargados` and
`~/books_analysis` (source PDFs, extracted text and curated notes). Only four
books were available: *The Intelligent Investor*, *Security Analysis*,
*Common Stocks and Uncommon Profits* and *Warren Buffett and the
Interpretation of Financial Statements* (the Buffett/Clark reference).

## Rules kept from public knowledge

The existing implementation already used public-knowledge thresholds. They
remain in place and are labelled `public knowledge` in the rules doc:

- `buffett_classic`: see `backend/methodologies/buffett_classic/` and
  `docs/buffett_classic_rules.md`.

## Search log

```
find /home/caudillo -maxdepth 6 -type f \( -iname '*one*up*' ...
# returned no book files (only browser bookmarks / unrelated code)
```
