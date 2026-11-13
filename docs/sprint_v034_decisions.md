# Sprint v0.34.0 — decisions (STOP 0)

Date: 2026-11-13. Phase 0 diagnostics were run read-only against
Financial-DataBase `main` before any implementation.

## Diagnostics

| Question | Finding |
|---|---|
| Filing dates | `financial_facts.filing_date` exists, `NOT NULL`, 76,250,812 / 76,250,812 rows (100%), range 2009-04-15 → 2026-11-10. `filings` has 1,095,204 rows, all dated. No backfill needed. |
| Restatements | Multiple rows coexist per (concept, period). AAPL FY2024: original `2024-11-01`, later re-presentation `2026-11-03`. A PIT read keeps the latest `filing_date <= as_of`. |
| Delisted companies | `companies.is_active = false`: 0 rows. No `delisted_at`. One inactive listing in `company_listings`. |
| Delisted prices | Yahoo returns no data for LEHMQ, ENRNQ, WCOM, TWTR, ATVI, FRC, SIVB. |
| Historical constituents | No `sp500_constituents` table. The fja05680 URL in the sprint returns 404, but `sp500_ticker_start_end.csv` in the same repo is live: 1,262 intervals / 1,209 tickers, 1996-01-02 → 2026-08-18. |
| FDB coverage of those tickers | 2015: 387/502 (77%); 2019: 434/505 (86%); 2022: 470/503 (93%); 2024: 485/503 (96%). |

## Answers

| ID | Question | Answer | Rationale |
|---|---|---|---|
| Q1 | Historical constituents source | **B + C: fja05680 base + current-composition sanity check** | CSV is directly `(ticker, start_date, end_date)`; current snapshot overlaps Wikipedia 496/503 (98.6%). Source stale since 2026-08-18, documented. |
| Q2 | Delisted policy | **A: accept the gap and document** | Yahoo serves no delisted prices; FDB has no delisted companies. The run reports `survivorship_bias: true`. |
| Q3 | FDB re-ingest strategy | **A: use the existing `filing_date`** | 100% populated. Migration only adds the PIT index and documents the semantics. |
| Q4 | Transaction costs | **C: configurable, default 10 bps** | `--tc-bps 10 --tc-fixed 0` (fixed per changed name, expressed against capital). |
| Q5 | Rebalancing | **D: configurable, default annual** | `--rebalance annual\|quarterly\|threshold` (threshold default 5%). |
| Q6 | Sizing | **A + 20% cap** | Tier 60/30/10 split within tier, re-scaled to present tiers, every name capped at 20%; no Kelly. |
| Q7 | Mobile Dependabot | **A: patch without Expo SDK upgrade** | zod and glob patched via overrides; deepmerge has no upstream fix (low severity, documented). |
| Q8 | Simplification / Big-O | **Excluded** | No measured bottleneck; 2,976 unit tests green. Backlog: revisit with a profile. |

## Consequences

- Research-grade runs start at the 2015–2024 window where FDB coverage is
  ≥ 77%; earlier years are possible but carry a larger survivorship gap.
- `--research-grade` is the label; the legacy path remains the default so
  previously published PoC numbers stay comparable.
- Delisted constituents without a live price are skipped, never replaced with
  a synthetic series.
