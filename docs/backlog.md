# Backlog (prioritized, from the 2026-09-30 QA session)

## P0 — must fix before the next feature

_None._ The only P0 found (the `analyze-buffett-classic --no-refresh`
inconsistency) was fixed in commit `da54066`.

## P1 — should fix soon

1. **`--no-refresh` is parsed but unused in the six `analyze-*`
   commands.** The flag exists (and its help says "Skip the on-demand
   SEC refresh") but no command reads `args.no_refresh`; the refresh
   runs only through `add_refresh_arguments` in the main commands.
   Either wire the flag to `RefreshService` or remove it from the six
   commands. *Repro*: `grep -rn no_refresh cli/commands/` → no reads.
   *Effort*: S (wire) / XS (remove).
2. **Unknown ticker in `analyze-full` has no explicit message.** Running
   `analyze-full ZZZZ` exits 0 with only Yahoo warnings; add a clear
   "ticker not found in the repository" message before the analysis.
   *Repro*: `python main.py analyze-full ZZZZ --no-refresh`.
   *Effort*: S.

## P2 — nice to have

3. **Disagreement summary is boilerplate for non-value/quality splits.**
   For XOM (cyclical) the paragraph about "expensive or levered balance
   sheet vs strong-but-expensive quality" does not describe the conflict.
   Make the explanation conditional (only when a deep-value member is
   AVOID and a quality member is BUY; otherwise "different lenses").
   *Effort*: S.
4. **Ford trips the financial fingerprint** (`total_liabilities /
   total_assets > 0.85` from Ford Credit), so five methodologies abstain
   on an automaker. Consider requiring "no inventory" alongside the
   ratio, or a sector-hint override. *Effort*: M (calibration risk).
5. **`buffett_classic` does not abstain on banks** (JPM AVOID 29.2
   because its financial-strength pillar reads bank leverage as
   weakness). Decide: add the financial guard or adjust the pillar.
   *Effort*: M.
6. **Screener estimate could be adaptive** (use the last run's measured
   seconds-per-ticker instead of the fixed 1.8). *Effort*: S.
7. **`historical-valuation` takes ~37 s** (one Yahoo price fetch per
   fiscal year). Batch the fetches through the snapshot prefetch or a
   longer cache. *Effort*: M.

## P3 — deferred / future

8. **New methodologies**: Greenblatt Magic Formula (ROC + earnings
   yield) and Marks cycle positioning — both fit the existing book
   methodology pattern.
9. **Unmapped universe coverage**: ~2,300 listed companies have no facts
   (unmapped / never synced); expanding the CIK mapping would grow the
   analyzable universe.
10. **Screener enrichment cost**: verdict/category per screened row
    (~1.8 s/ticker). A batch path reusing the workflow's in-process
    analysis would cut it substantially.
