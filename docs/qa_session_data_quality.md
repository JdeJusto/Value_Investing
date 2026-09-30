# QA session — data quality and edge cases (2026-09-30)

## F1 — Edge case tickers (`analyze-full`)

| Ticker | Profile | Result | Flag |
| --- | --- | --- | --- |
| OYSE | SPAC (shell) | Score 2.6, INSUFFICIENT_DATA, exit 0 | OK |
| TSM | Foreign ADR (20-F filer) | Score 33.5, INSUFFICIENT_DATA, exit 0 | OK (degrades) |
| ZZZZ | Unknown ticker | exit 0, but only Yahoo warnings (`Invalid Crumb`, DNSError); no explicit "unknown ticker" message | IMPROVEMENT (P2) |
| RBRK | Recent IPO (few years) | Score 61.8, INSUFFICIENT_DATA, exit 0 | OK (degrades) |

No crashes on any edge case. The unknown ticker does not crash but also
does not say the ticker is unknown — backlog P2.

## F2 — AAPL FY2024 cross-check vs SEC EDGAR

| Concept | FDB (best) | SEC companyconcept | Delta |
| --- | --- | --- | --- |
| Revenue (contract) | 391.035 B | 391.035 B | **0.00%** |
| Net income | 93.736 B | 93.736 B | **0.00%** |
| Total assets | 364.980 B | 364.980 B | **0.00%** |

The fact tables hold several comparatives per concept (e.g. assets
352.583/364.980), but the repository's newest-comparative ranking selects
the FY2024 figure exactly. Tolerance <2% satisfied with zero delta.

## F3 — Concept coverage (companies with an active listing, n=7,826)

| Missing | Count | Share |
| --- | --- | --- |
| Revenue (any of the 8 mapped concepts) | 2,313 | 29.6% |
| Net income (any of 4 mapped concepts) | 1,292 | 16.5% |
| Total assets (`Assets`) | 1,300 | 16.6% |

The revenue gap is dominated by companies with **no facts at all**
(unmapped / never synced): the daily workflow reports ~2,528 unmapped
tickers, which matches this order of magnitude. Companies with facts have
the three core concepts with ~0% gaps. Raw single-concept counts
(`Revenues` only: 4,088) overstate the gap because most filers use
`RevenueFromContractWithCustomerExcludingAssessedTax`.

## Assessment

Data quality for the analyzable universe is high (exact EDGAR match on
the AAPL spot check; core concepts present whenever facts exist). The
remaining gap is coverage (unmapped companies), not correctness.
