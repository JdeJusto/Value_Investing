# Backlog (updated 2026-09-30, after the refinement sprint)

All P0/P1 and the smaller P2 items from the QA session are closed. This
file now tracks what remains.

## Closed in the refinement sprint (2026-09-30)

| Item | Commit |
| --- | --- |
| `--no-refresh` was a parsed no-op in the six `analyze-*` commands | `54c24b1` (wired through `refresh_analysis_inputs`, regression tests) |
| Unknown ticker in `analyze-full` had no clear message | `1994ce2` (preflight resolver, exit 2, 5 tests) |
| Screener estimate hardcoded / "~0 min" | adaptive per-run measurement (screener commit) |
| Disagreement summary boilerplate on non-value/quality splits | conditional narrative + consensus (`disagreement_narrative`) |
| `buffett_classic` exempt from the financial guard | guard added; JPM/WFC abstain like the other five |
| Ford typed as financial by the leverage fingerprint | known non-financial sector now wins; Ford gets real verdicts |
| `historical-valuation` 37 s (one fetch per fiscal year) | one cached full-history fetch; measured 16 s |

## Remaining

### P2 — nice to have

1. **Extend the unknown-ticker preflight to the six `analyze-*`
   commands.** Today only `analyze-full` validates the ticker; the
   methodology commands evaluate empty rows and print an INSUFFICIENT
   verdict. Reuse `backend/services/ticker_resolver.resolve_ticker` (the
   helper is already shared). *Effort*: S.
2. **Screener enrichment batching.** Verdict/category cost ~1.8 s/ticker
   because each row re-reads fundamentals and runs the registry. Reusing
   the daily workflow's in-process analysis would cut it substantially.
   *Effort*: M.
3. **`get_price_on_date` window semantics** are now applied in memory
   over a full-history fetch; if Yahoo's `history()` default period ever
   changes, the explicit `start=2000-01-01` keeps it safe, but a test
   pinning the fetch args for a no-window caller would document it
   further. *Effort*: XS.

### P3 — deferred / future

4. **New methodologies**: Greenblatt Magic Formula (ROC + earnings
   yield) and Marks cycle positioning — both fit the book methodology
   pattern (rules + README + tests + registry).
5. **Unmapped universe coverage**: ~2,300 listed companies have no
   facts (unmapped / never synced); expanding the CIK mapping grows the
   analyzable universe.
6. **`analyze-graham`/`lynch-garp` first-call warm-up** (13-26 s) is
   Yahoo price latency, not a defect; a shared prefetch across commands
   would smooth it. *Effort*: M.
