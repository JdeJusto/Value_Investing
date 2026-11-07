## [0.24.0] - 2026-11-07

### Added
- **BUY tiers (demote-only)**: methodology verdicts now include
  `STRONG_BUY` (top 3% of the scored universe, ranked by score), `BUY`
  (3-10%) and `WEAK_BUY` (10-15%). BUYs outside the top 15% are demoted to
  `WATCH`/`HOLD`/`AVOID`. The rule's verdict is the ceiling: `WATCH`/`HOLD`/
  `AVOID` are never promoted, so a rule rejection stays a rejection.
  Universes under 50 scored companies fall back to absolute cut-offs
  (≥80/60/50/40/30). A BUY without a numeric score stays `BUY` with
  `tier=None`.
- **Tier-weighted backtest**: `vi backtest` weights `STRONG_BUY` 60%,
  `BUY` 30% and `WEAK_BUY` 10%, normalized to the tiers present that year
  (BUY+WEAK → 75/25, STRONG+BUY → 66.7/33.3, one tier → 100%).
  `--equal-weight` restores the legacy equal-weight behaviour.
- `is_positive(verdict)` helper grouping the three positive tiers for
  backwards-compatible "buy signal" checks.

### Changed
- Verdict distribution on the S&P 500 with `buffett_classic`: **150 BUY
  (30.1%) → 65 positive** (13 STRONG_BUY + 30 BUY + 22 WEAK_BUY, 15.2%).
  Graham, Graham & Dodd and Marks keep **0 positive** because their rules
  reject the universe; those verdicts are never promoted.
- `vi rank` shows a **Tier** column and adds `--positive-only`; the JSON
  carries `tier` (and keeps `verdict`).
- `vi scorecard --json` includes `tier` on every methodology.
- Consensus `buy_count` aggregates all three tiers via `is_positive`
  (pre-v0.24 consensus files stay compatible).
- UI ticks/chips use tier colours (gold STRONG_BUY, cyan BUY, dim cyan
  WEAK_BUY); the consensus summary lists the new labels.
- The screener's `--methodology NAME:VERDICT` filter applies the
  single-ticker absolute fallback, so `buffett_classic:BUY` matches the
  tiered verdict.

### Notes
- **Demote-only semantics**: a high score never promotes a WATCH/HOLD/AVOID
  into a buy. This preserves each methodology's own criteria.
- **Backwards compatibility**: the `verdict` field is preserved. Code that
  checked `verdict == "BUY"` should migrate to `is_positive(verdict)` to
  match every positive tier.
- **BUY without score** (e.g. some Lynch results) stays `BUY` with
  `tier=None`; the backtest counts it with BUY weight (30%).
- **Historical backtests are not comparable** after this release; re-run
  `vi backtest` (use `--equal-weight` to reproduce the pre-v0.24
  behaviour).
- Measured backtest (`buffett_classic`, 10 years, limit 400): tier-weighted
  CAGR 14.1% / Sharpe 1.22 vs legacy equal 14.2% / 1.20; opportunity set
  15.2%, SPY 14.7%.
- Test count: **2661 → 2678**.

## [0.23.0] - 2026-11-07

### Fixed
- **Fisher aggregation (C4a-2)**: rules whose line item does not exist in the
  business model (R&D in a low-R&D sector, gross margin in a REIT) return
  `NOT_APPLICABLE` instead of `INSUFFICIENT_DATA` and are excluded from the
  verdict denominator. The verdict aggregates on applicable rules: <50%
  applicable → N/A, no scorable rule → INSUFFICIENT, any FAIL → AVOID, BUY
  only when every applicable rule passed and none is missing. A single scored
  rule is not enough evidence. Summary reasons report
  "N not applicable, M insufficient, K scored". TTE moves from
  INSUFFICIENT_DATA to AVOID (the R&D failure is the only scored rule).
- **DCF reason field**: every `INSUFFICIENT_DATA` DCF now carries a one-line
  `reason` (FCF history, negative FCF, DDM history, bank without a dividend
  stream, REIT without FFO, missing terminal input, missing shares/price).
  Rendered by `vi dcf` ("Verdict: INSUFFICIENT_DATA — <reason>"), included in
  the new `vi dcf --json` payload and shown by the Streamlit DCF panel.
- **Greenblatt out-of-universe**: tickers outside the S&P 500 ranking universe
  return N/A with the canonical reason "ticker not in ranking universe
  (SP500)". An in-universe ticker missing from the latest ranking (PCAR)
  returns INSUFFICIENT with "Regenerate it with
  scripts/compute_greenblatt_rankings.py", so a stale ranking is not mistaken
  for an N/A company.
- **Screener performance**: the screener now reuses the persistent
  `AnalysisCache` that single-ticker commands use, instead of re-reading the
  same normalized fundamentals on every run; the Streamlit methodology
  enrichment is cached for 5 minutes. Measured: two consecutive screens of
  AAPL/MSFT hit the cache for every ticker (hits 2 → 4, misses 0).

### Added
- **`vi screener --methodology NAME:VERDICT`**: keeps only tickers whose
  methodology verdict matches (e.g. `graham:BUY`, `lynch:WATCH`). Repeatable
  with AND semantics:
  `--methodology graham:BUY --methodology lynch:BUY`. Methodology names,
  aliases (lynch → lynch_garp) and verdicts are validated; the flag cannot be
  combined with the Buffett quality engine.

### Documentation
- `docs/data_gaps_investigation.md` and `docs/fdb_tickets.md`: PCAR
  (unclassified balance sheet, restricted-inclusive cash only) and BRUN
  (1-2 years of history) documented as residual data gaps.
- `docs/greenblatt_pipeline.md`: explicit `EnvironmentFile=` systemd how-to
  and the log check for the PostgreSQL fallback.
- `docs/backlog.md`: closed vs deferred table. The screener UX redesign needs
  a human-approved mockup (v0.24+); the research-grade backtest requires
  historical universe, costs and rebalancing (v0.24+).
- `docs/insufficient_data_analysis.md`: final state after v0.23.0.

### Measured
- INSUFFICIENT_DATA on the 30-ticker audit set: **43 → 40**
  (dimensions 12 → 12, methodology verdicts 17 → 16, DCF 14 → 12 measured;
  the DCF count is price-dependent and every remaining one has a reason).
- Fisher `INSUFFICIENT_DATA`: **4 → 3**.
- DCF reasons at measurement: 7 insufficient FCF history, 2 negative FCF,
  1 short DDM history, 1 bank without dividends, 1 REIT without FFO.
- Test count: **2624 → 2655**.

### Notes
- "Screener is slow" was partly the missing cache and partly the old default
  SEC refresh (already opt-in since v0.20.2). The UX redesign is out of scope
  until a mockup is approved.
- No Financial-DataBase writes: the new queries and the backtest are
  read-only.

## [0.22.0] - 2026-11-07

### Added
- **Peers tab** (Streamlit Analysis): a radar and a dimension matrix with the
  six scorecard dimensions of the company and up to five same-sector peers.
  The subject is highlighted in neon cyan; peers use the synthwave accents;
  missing scores stay gaps, never 0.
- **`PeerComparisonService`**: same-sector peers (industry fallback) ordered
  by Yahoo market cap (USD, on demand, never persisted) because
  `core_financials.total_assets` is reported in the filing currency. Banks,
  insurers and REITs are skipped (their dimensions are N/A).
- **`LookupsMixin.list_peer_tickers`**: one read-only metadata query over
  `company_listings` + `companies`.
- **Methodology backtesting PoC** (`vi backtest --methodology NAME --years N`)
  and `scripts/backtest_methodologies.py`: re-evaluates each book methodology
  at every fiscal-year end with only the fundamentals known then, holds the
  BUY set equal-weighted for one year, and reports CAGR, equal-weight
  benchmark, hit rate, Sharpe (no risk-free rate) and per-year rows.
  Results go to `data/backtest/` (git-ignored).
- **`docs/circle_chart_design.md`**: radar-of-peers decision, ASCII mockup,
  selection rule and non-goals.
- **`docs/backtesting_design.md`**: metric definitions, data sources and the
  explicit limitations (price return only, survivorship, restatements,
  annual granularity, no costs, Greenblatt excluded).

### Changed
- The methodology backtest universe sample is evenly spaced across the sorted
  tickers (`--limit`), not the first N alphabetically, so the PoC does not
  over-represent A-tickers.

### Notes
- Greenblatt is not historically backtestable: its verdict reads the current
  point-in-time ranking file, so using it for past years would be look-ahead.
- The backtest is a PoC, **not research-grade**. A research-grade version
  (point-in-time fundamentals, delisted prices, dividends, monthly rebalancing)
  is recorded in `docs/backlog.md`.
- No Financial-DataBase writes: every new query is read-only.
- Test count: **2607 → 2624**.

## [0.21.0] - 2026-11-07

### Added
- **Evolution tab** (Streamlit Analysis): eight 10-year charts over the
  canonical `core_financials` fields (revenue, net income, operating income,
  gross profit, total assets, total liabilities, equity, cash), USD billions,
  per-field synthwave colours. Missing years are shown as gaps, never
  invented; fewer than two non-null observations render "insufficient
  history".
- **`get_financial_timeseries`** (`FinancialDatabaseRepository`): windowed
  10-year series deduplicated per fiscal year by the latest `period_end`;
  accepts a ticker (or a company UUID).
- **Interactive menu**: `vi` with no arguments now opens the one-level menu
  (analyze, refresh, rank, portfolio, consensus, screener, filings, alerts).
  `vi --help` still prints the full usage.
- **Sector and industry in `vi company`**: both fields are printed from
  Financial-DataBase metadata via the new `get_company_sector` /
  `get_company_industry` lookups.

### Changed
- **C1-M concept mapping**: IFRS current asset/liability splits and net PP&E
  (`CurrentAssets`, `CurrentLiabilities`, `PropertyPlantAndEquipment`), the
  ROU-inclusive PP&E variants (TotalEnergies, AT&T, AMT, APA), oil-and-gas
  producing properties (APA), IFRS borrowings, and IFRS pretax/tax/finance
  costs. A net-PPE concept priority keeps a residual surface PP&E line from
  outranking producing properties.
- **EBIT fallback**: when no operating-income tag is filed, EBIT is rebuilt
  from pretax income + interest (pretax alone without interest, then net
  income + tax + interest). Fixes JNJ, ADM, PCAR and TotalEnergies.
- **Cash-flow mappings**: Verizon network capex
  (`PaymentsToAcquireOtherProductiveAssets`) and TD Bank dividends
  (`DividendsPaidClassifiedAsFinancingActivities`).
- **Banks, insurers, capital-markets firms and REITs** now return `N/A` on
  all six scorecard dimensions, with a visible reason, instead of a
  misleading 0-10 score. Payment networks and asset managers (V, MA, BLK)
  and utilities (DUK, NEE) keep the standard scorecard. Overall becomes
  `N/A` when every dimension is `N/A`.
- **Greenblatt**: REITs and tickers outside the S&P 500 ranking universe
  return `N/A` with an explicit reason instead of `INSUFFICIENT_DATA`.
- **Greenblatt ranking regenerated** (2026-11-06, 386 companies, was 284).

### Fixed
- **T-view slots and labels** for the new IFRS/ROU/oil-and-gas balance
  concepts, so the UI can place them instead of hiding them as orphans.
- **APA return on capital** no longer uses a 146M residual PP&E line
  (ROC 2114%); it now uses 12.5B of producing properties (ROC 24.6%).
- **ACN Greenblatt**: resolved by the regenerated ranking (WATCH, ROC 101.4%).

### Measured
- INSUFFICIENT_DATA on the 30-ticker audit set: **85 → 43**
  (dimensions 34 → 12, methodology verdicts 37 → 17, DCF unchanged at 14).
- Greenblatt `INSUFFICIENT_DATA`: **15 → 1** (PCAR, unclassified balance
  sheet, documented). N/A methodology verdicts: 56 → 66.
- Test count: **2579 → 2607**.

### Documentation
- `docs/insufficient_data_analysis.md`: C1-M and C4b sections, company-category
  note, measured deltas.
- `docs/scorecard_design.md`: N/A status, company-type guard and the
  `reason` field in the dimension contract.
- READMEs: `vi` with no arguments opens the menu.

### Notes
- PCAR keeps `INSUFFICIENT_DATA` for Greenblatt: its balance sheet is
  unclassified (large finance subsidiary), so net working capital cannot be
  computed. RACE files no `CurrentLiabilities` for the same reason and is N/A
  by universe.
- BRUN (5 of the remaining 12 dimensions) is early-stage with almost no
  history.
- Prices remain on-demand from Yahoo, never persisted.

## [0.20.3] - 2026-11-06

### Added
- **T-view hierarchical sections** (CLI + UI): the balance sheet now
  shows CURRENT ASSETS / NON-CURRENT ASSETS / CURRENT LIABILITIES /
  NON-CURRENT LIABILITIES / SHAREHOLDERS' EQUITY as distinct sections
  with per-section subtotals, always visible in the UI. JSON output
  (`vi financials --json`) unchanged.
- **`vi refresh <ticker>`**: re-fetches SEC facts and Yahoo price for a
  single ticker. Supports `--facts-only`, `--prices-only`, `--json`.
  Exit codes: 0 (all OK), 1 (partial), 2 (single-domain failure).
  Prices are fetched on-demand and are not persisted to FDB.
- **Refresh button** in Streamlit Analysis page: triggers
  `refresh_ticker`, clears cache, reruns.
- **N/A state** in scorecard rules: rules that do not apply (e.g.
  current_ratio for banks) return N/A instead of INSUFFICIENT. N/A is
  excluded from the dimension denominator.

### Changed
- **Fiscal window** anchored on `effective_year` (Assets + Equity in
  `core_financials`) instead of `MAX(fiscal_year)`. The "10 years ago"
  check now fetches 11 rows for methodologies. Fixes **8 of 8** Fisher
  dilution cases that were INSUFFICIENT due to the FY2026 stray bucket
  (including AMT, whose FY2015 row becomes available with the anchored
  window).
- **`current_ratio`** is now computed from normalized `current_assets` /
  `current_liabilities` for non-banks; returns N/A for financials
  (previously hardcoded INSUFFICIENT in 30/30 tickers).

### Fixed
- **Greenblatt safety guard**: the weekly ranking job no longer
  overwrites a valid ranking with an empty one. If the run produces 0
  rankings (Yahoo DNSError), the payload is written to
  `greenblatt_<date>.failed.json` and the job exits non-zero, preserving
  the last valid file.
- **Greenblatt ranking regenerated** (2026-11-06, 284 companies ranked):
  8 SP500 tickers (AAPL, MSFT, CAT, CSX, PG, VZ, DUK, NEE) no longer
  return INSUFFICIENT_DATA for this methodology.
- **Display**: historical P/E chart excludes `|P/E| > 100` with caption
  of hidden years; CLI table shows "n.m." when `|net_income| < 1e6`;
  shares neighbor check rejects ×1000 / ×1e6 outliers (COP FY2011, BTI
  FY2019).

### Documentation
- `docs/greenblatt_pipeline.md` (new): pipeline, dependencies,
  safety guard, failure modes, manual regeneration.
- `docs/insufficient_data_analysis.md`: C2 / C4a-1 fixes recorded.
- READMEs: logo at top, `vi refresh` command, T-view section note,
  prices on-demand note. 8 badges preserved, 1 screenshot.

### Measured
- INSUFFICIENT_DATA: **104 → 85** across the 30-ticker audit set
  (34 scorecard dimensions + 37 methodology verdicts + 14 DCF).
- Greenblatt INSUFFICIENT: **23 → 15** overall. 8 SP500 tickers were
  resolved by the regenerated ranking; 14 mapping gaps remain, and 8
  tickers are outside SP500 (7 of them are also in the mapping gaps;
  BJRI is the remaining out-of-universe case).
- `current_ratio` INSUFFICIENT: **30/30 → 9/30**.
- Test count: 2540 → 2579.

### Notes
- C4a-2 (Fisher aggregation) deferred: requires editing
  `backend/methodologies/fisher_quantitative_subset/`.
- C4b (banks/REITs guard): pending product decision.
- C1-M (mapping): 14 Greenblatt M tickers, IFRS splits, VZ capex, TD
  dividends.
- 8 tickers outside SP500 (Russell2000 / Europe): pending
  multi-universe decision.
- PostgreSQL unavailable in the systemd job: environment issue,
  documented, not fixed.

## [0.20.2] - 2026-11-05

### Fixed
- **AUDIT-001**: NCI-inclusive equity
  (`StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`)
  is now recognized as a subtotal in `ui/balance_map.py`. Fixes equity
  for 7 large caps (JNJ, CAT, T, VZ, CSX, ADM, PG). CLI and UI now
  agree (JNJ: equity 81.5B, delta 0, `derived.equity=false`).
- **AUDIT-002**: `ui/pages/07_methodologies.py` registered in
  `st.navigation`. Methodologies ranking page is now visible in the
  sidebar.
- **AUDIT-004**: The "balanced" chip no longer shows plain "Balanced
  (Δ=0)" when equity is partial (MRX). Now shows "⚠ Balanced (partial
  equity — see caption)".
- **AUDIT-005**: `vi screener` no longer refreshes SEC/Yahoo by default.
  Pass `--refresh` to opt in. `--no-refresh` is deprecated (now the
  default).

### Documentation
- READMEs simplified (424 → 102 lines each). 8 badges preserved, 17
  unused screenshots and GIFs removed from `assets/` (~6 MB). Links to
  historical release notes verified intact.

### Notes
- `financial_facts` and FDB unchanged.
- Test count: 2522 → 2540.
- CI fix: screener refresh help test made portable (no `./vi` wrapper dependency).
- Pending: AUDIT-003 (sparse data banks/IFRS), 006, 007, 008 (low
  severity). Usage notes (`docs/usage_notes.md` Part B) to be filled
  after 1-2 weeks of real use.

## [0.20.1] - 2026-11-04

### Added
- `vi financials <ticker>` — two-section balance view (ASSETS |
  LIABILITIES + EQUITY) with subtotals, totals, balance chip, and
  `*` markers for derived liabilities (PCAR, 345 tickers) and partial
  equity (MRX). Supports `--json`, `--no-color`, `--years`, `--period`.
- `vi rank` — rank tickers by single methodology (`--by graham`) or
  combination (`--combine graham,lynch --strategy and|or|weighted`).
  Supports `--universe`, `--top`, `--include-na`, `--json`. Alias
  `lynch -> lynch_garp`.
- `cli/theme.py` — synthwave ANSI palette (neon cyan, gold, purple,
  pink). Opt-in: only new commands use it; the 40 existing commands
  are unchanged. Respects `--no-color`, `NO_COLOR` and non-TTY stdout.

### JSON contract (`vi financials --json`)
```json
{
  "ticker": "AAPL",
  "fiscal_year": 2025,
  "assets": {
    "current": [{"concept": "...", "label": "...", "value": "..."}],
    "non_current": [],
    "total_current": 0,
    "total_non_current": 0,
    "total": 0
  },
  "liabilities_equity": {
    "current": [],
    "non_current": [],
    "equity": [],
    "total_current": 0,
    "total_non_current": 0,
    "total_equity": 0,
    "total": 0
  },
  "derived": {"liabilities": false, "equity": false},
  "balanced": true,
  "delta": 0.0,
  "balance_sheet": []
}
```

### Documentation
- CLI section in `README.md` and `README.es.md` with examples and an
  abbreviated `vi financials AAPL` capture.

### Notes
- Full side-by-side T-view ASCII layout is deferred to v0.21
  (`# TODO(v0.21)`). The current layout is a flat two-section view with
  line items, subtotals, totals and balance chip.
- `--json` retrofit for the 40 existing commands and
  `vi screen --methodology` are pending.
- Test count: 2498 -> 2522.

## [0.20.0] - 2026-11-04

### Added
- **FDB 0.2.1 integration**: VI reads normalized financial data from
  FDB's `core_financials` MV (8 canonical fields) and
  `financial_facts_normalized` view.
- T-view marks derived values:
  - `*` for derived liabilities (345 tickers; e.g. PCAR).
  - `*` for partial equity (MRX: RetainedEarnings only) with a specific
    caption clarifying that full equity is not reported.

### Changed
- **Effective-year rule** (`analytics.service.effective_year()`):
  requires `total_assets + stockholders_equity` (not `revenue`). MRX
  FY2025 lacks equity → effective year is FY2024. Applies to scorecard,
  screener, ranking and consensus.
- `get_best_available()` merges `core_financials` with normalized fields.
  `fdb_concept_mapping` remains the fallback for ~103 non-canonical
  concepts.
- **Coverage improvement**: 37 large caps (JNJ, CAT, T, VZ, CSX, ADM,
  PG, ...) now have equity via the FDB 0.2.1 NCI alias. VI tickers
  without effective year: **108 → 71**.

### Fixed
- **`methodology_ranking_service` was loading fundamentals from a
  non-existent `get_fundamentals` method**, always returning an empty
  history. Ranking now works via `get_best_available()`. Tests added
  (mock-only; integration test tracked as debt).
- MRX T-view anchors comparative equity by `period_end` to avoid
  bleeding prior-year equity into the selected year.
- MRX equity now uses a specific partial-equity caption instead of the
  generic computed-subtotal note.

### Measured
- Coverage `8/8 canonical fields`: 898 in the VI universe.
- Tickers with derived liabilities: 345.
- Batch `get_core_financials` for 76 tickers: 67-101 ms.
- Unit tests: 2498 (+28 from v0.19.2), 125 API, ruff 0/0.

### Notes
- **Requires FDB >= 0.2.1**. The NCI equity alias was released in FDB
  0.2.1; v0.20.0 depends on it for large-cap coverage.
- `bank_revenue` (FDB 0.2.0) is not yet surfaced in the VI UI.
- MRX equity shows a partial value (RetainedEarnings only); full equity
  is not reported in the filing.
- 71 tickers remain without an effective year (69 without
  `core_financials` rows, BRUN without `total_assets`, SKT without
  balance facts).
- FDB v0.3.0 will split `stockholders_equity_parent` from the
  NCI-inclusive value.

## [0.19.2] - 2026-10-23

### Added
- Demo Financials payloads regenerated for all 76 demo tickers (previously 4). The demo T-view now works for every ticker in the offline bundle and matches the live layout for the key companies.
- `scripts/build_demo_financials.py` extended with Fix-B-aware concept selection (balance rows follow `ui.balance_map` / `BALANCE_MAP`, bucketed via `classify_concept`); generates fixtures for every ticker in `DEMO_TICKERS`.
- New tests `tests/unit/test_demo_financials_payloads.py` cover full demo ticker coverage, ADBE line counts, AAPL layout parity, and payload bucket integrity.
- `docs/data_gaps_investigation.md` documents balance T-view limitations (BDX double-counted deferred tax, 4 FDB-limited tickers APA/APO/ARES/BRK-B, AEE unverified, AAPL commercial-paper trade-off, and 27 tickers that show ≥10 lines but do not balance).

### Changed
- Demo bundle size cap raised from 2 MB to 4 MB (bundle: ~3.88 MB) with documented rationale; fixtures include view payloads, insights and alerts for all 76 tickers.

### Fixed
- T-view opens on the newest fiscal year that actually has filed balance data (Fix E).
- Balance concept map (Fix B): alias resolution by value, zero-vs-non-zero preference, aggregate rendering rules. Banks, insurers, oil & gas, REITs and utilities now render their face lines.

### Notes
- BDX remains a known regression (Δ ≈ −$2.48B) due to a double-counted deferred tax note in FDB aggregates; no containment rule or per-ticker hack added.
- 4 tickers are FDB-limited (APA, APO, ARES, BRK-B); tags exist in filings but are not stored in Financial-DataBase.
- 27 tickers show ≥10 lines per column but the balance chip is honest and reports "does not balance" (documented).

## [0.19.1] - 2026-10-21

### Added

- Radar dimension filter on the Scorecard: multi-select checkboxes to show or
  hide individual radar axes — visual de-cluttering only; the underlying data
  is unchanged. Design options documented in `docs/radar_filter_design.md`.
- Contract test (`tests/unit/test_pipfile_lock_pins.py`) guarding the
  intentionally pinned lock exceptions against re-introducing the previously
  reverted major bumps.

### Changed

- `Pipfile.lock` regenerated from scratch with a reviewed exception pass:
  `pyarrow`, `soupsieve`, `websockets` and `fastapi` keep their previous
  majors on purpose (e.g. `fastapi==0.150.0`); rationale in
  `docs/backlog.md`.
- Lint tooling pinned to `ruff==0.16.4` with its configuration consolidated in
  `pyproject.toml`; codebase formatted to match (568 files).
- `Pipfile` pinned to `python_version = "3.13"` to match CI.
- Streamlit `unsafe_allow_html` calls centralized in a `render_html` helper
  (rendering unchanged, byte-for-byte).
- README screenshots (EN/ES) regenerated from the current UI (11 captures at
  1440x960) and repointed to the canonical `ui_v2_*` set; superseded
  pre-theme PNGs removed and the test badge updated to 2,376.

## [0.19.0] - 2026-10-19

### Added

- English-only UI strings across all Streamlit pages (balance T-view, flat
  financial tables, tooltips, headers).
- Demo bundle expanded from 8 to 76 tickers, with size cap (2 MB) and
  manifest-consistency guardrails in tests.
- STALE classification in `audit_data_quality.py` (companies whose latest FY
  is >15 months old are flagged and excluded from metric comparisons).

### Changed

- `dei:EntityCommonStockSharesOutstanding` used as last-resort fallback in
  share-count mapping; cross-concept scale repair for share counts filed in
  scaled units (e.g. MCD FY2025).
- Audit classifier: weighted-average share counts, bank/REIT revenue,
  segment capex, and derived dividends now classified; stale-fact guard at
  400 days.

### Fixed

- UNCLASSIFIED comparisons in the monthly audit dropped from 43 to 2.
- Bank demo tickers now compute valuation in the scorecard (AFL, AIG, BAC,
  BRK-B).

### Notes

- Two UNCLASSIFIED cases remain by design (TKO dual-class, IBKR revenue
  coverage); documented in `docs/data_gaps_investigation.md`.

## [0.18.1] - 2026-10-17

### Fixed

- Close audit follow-ups and scorecard Phase 3.5 gaps

## [0.18.0] - 2026-10-17

### Added

- Markdown scorecard export and monthly data-quality audit

## [0.17.1] - 2026-10-17

### Fixed

- Peer comparison in the scorecard

## [0.17.0] - 2026-10-15

### Added

- Scorecard radar, four dimension history charts and JSON export

## [0.16.9] - 2026-10-14

### Fixed

- Scorecard tab in Streamlit (text-only)

## [0.16.8] - 2026-10-14

### Fixed

- Scorecard API endpoint and CLI command

## [0.16.7] - 2026-10-14

### Fixed

- Recurring data-sample validation against SEC EDGAR; CI coverage and pyright gates; structured API logs and global error handler; orphan asset cleanup; boot-triggered daily workflow

## [0.16.6] - 2026-10-13

### Fixed

- Re-run mobile APK release after fixing invalid mobile-release.yml

## [0.16.5] - 2026-10-09

### Fixed

- Grant contents:write to the mobile-release workflow


# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.16.4] - 2026-10-09

### Fixed

- Verify automated mobile-release workflow and attach small APK

## [0.16.3] - 2026-10-09

### Fixed

- Fix CI workflow for mobile release

## [0.16.2] - 2026-10-09

### Fixed

- Shrink the mobile APK via release+ABI split and force patched transitive deps

## [0.16.1] - 2026-10-09

### Fixed

- Attach APK to releases, patch mobile CVEs, and merge frontend Dependabot PRs

## [0.16.0] - 2026-10-09

### Added

- Add screener, consensus, search, and portfolio endpoints + mobile screens

## [0.15.0] - 2026-10-08

### Added

- Add financials, filings, statements, sections, and insights endpoints + mobile tabs

## [0.14.0] - 2026-10-08

### Added

- Add company methodologies, DCF, and alerts endpoints + mobile tabs

## [0.13.1] - 2026-10-07

### Fixed

- SCREENER QUALITY PASS: N/A verdict, ratio guards, Lynch sector fallback, split fix, financial subtypes, screener polish

## [0.13.0] - 2026-10-07

### Added

- Rich CLI with colors, spinners, progress bars, and interactive mode

## [0.12.4] - 2026-10-06

### Fixed

- Auto-update badges and add workflow GIFs

## [0.12.3] - 2026-10-06

### Fixed

- Add logo, badges, and refreshed README with screenshots

## [0.12.2] - 2026-10-06

### Fixed

- Inline consensus entry, score-based default sort, and CLI language pass

## [0.12.1] - 2026-10-06

### Fixed

- Fetch prices for consensus and add CLI commands

## [0.12.0] - 2026-10-06

### Added

- Systematic concept coverage fix and consensus screener

## [0.11.2] - 2026-10-06

### Fixed

- Translate UI to English and fix concept mapping for REITs

## [0.11.1] - 2026-10-06

### Fixed

- Clear demo-mode message and English UI strings

## [0.11.0] - 2026-10-05

### Added

- Abbreviate large numbers in UI and pin price/market cap header

## [0.10.3] - 2026-10-05

### Fixed

- Fix complex-number CAGR crash and Streamlit width deprecation

## [0.10.2] - 2026-10-05

### Changed

- Split ui_adapter and financial_database_repository for modularity

## [0.10.1] - 2026-10-05

### Added

- Add deterministic financial alerts in UI sidebar and CLI

## [0.10.0] - 2026-10-05

### Added

- Add Financial Insights panel and refactor for modularity

## [0.9.0] - 2026-10-05

### Added

- Add comprehensive Financials tab with all statement facts per year

## [0.8.1] - 2026-10-02

### Fixed

- Warn when narrative sections incorporate content by reference

## [0.8.0] - 2026-10-02

### Added

- Add Risk Factors and MD&A extraction with UI narrative view

## [0.7.2] - 2026-10-02

### Fixed

- Fix JNJ income statement detection

## [0.7.1] - 2026-10-02

### Fixed

- Add statement type selector to Filings tab UI and 12 demo fixtures

## [0.7.0] - 2026-10-02

### Added

- Add income statement and cash flow extraction with parse cache

## [0.6.0] - 2026-10-02

### Added

- Extract balance sheet from 10-K/10-Q with preview in Filings tab

## [0.5.0] - 2026-10-02

### Added

- Add SEC filings browser with filters and EDGAR links

## [0.4.2] - 2026-09-30

### Fixed

- Add consolidated architecture doc, worked example, and pre-publish checklist

## [0.4.1] - 2026-09-30

### Fixed

- Fix the JSON fallback when no database is available

## [0.4.0] - 2026-09-30

### Added

- Add offline demo mode, terminal GIFs, UI screenshots, and 'Why this project' section

## [0.3.0] - 2026-09-30

### Added

- Add Marks (8th methodology), screener history cap and parallel price warm-up

## [0.2.0] - 2026-09-30

### Added

- Add net income convention, SPAC exclusion, weekly Greenblatt rankings, and shared price prefetch

## [0.1.1] - 2026-09-30

### Fixed

- Fix Python 3.13 compatibility (PEP 758 and self-referential annotations)

## [0.1.0] - 2026-09-30

First public release.

### Added

- Seven book-derived methodologies: Graham (*The Intelligent Investor*),
  Graham & Dodd (*Security Analysis*), Buffett/Clark (*financial statements*),
  Buffett Classic (4-pillar filter), Fisher (quantitative subset), Lynch GARP
  (with company categories) and Greenblatt Magic Formula (cross-sectional,
  weekly rankings).
- DCF valuation module (`not-from-canon`) with four variants: standard, REIT,
  financial (single and two-stage DDM) and hyper-growth.
- Shared `company_type` detection with financial guards across all
  methodologies.
- Financial-DataBase integration: fundamentals from SEC EDGAR, sector
  metadata, and the on-demand targeted refresh (`sec sync <CIK>`).
- Streamlit UI with five pages: Home, Analysis, Screener, Portfolio, Reports.
- Screener with SQL-first filtering, adaptive time estimate, CSV export and
  bounded parallel enrichment.
- Portfolio tracking with buy/sell/exit, PnL, HHI and concentration warnings.
- Daily workflow: universe screening, alerts, DCF, network telemetry,
  `--universe` subsets and `--resume`.
- Ticker preflight validation with clear unknown-ticker errors (exit 2) in
  every `analyze-*` command.
- Weekly Greenblatt Magic Formula rankings
  (`scripts/compute_greenblatt_rankings.py`, idempotent per day).
- IFRS revenue and cost-of-sales mapping for 20-F/40-F filers.
- Data coherence audit (SEC EDGAR / Yahoo) and unmapped-coverage analysis in
  `docs/`.

### Changed

- Prices are never persisted; always fetched in real time from Yahoo through
  `PriceService` (in-memory cache only).
- Financial guard applied consistently across all book methodologies.
- `historical-valuation` uses a single cached full-history price fetch per
  ticker (37 s → 16 s on the reference case).

### Fixed

- Ford no longer classified as financial by the balance-sheet fingerprint
  (sector keywords take priority).
- Preferred dividend contamination in the DDM for banks.
- CompanyRepository import missing in `app/cli.py`.
- `--no-refresh` now wired through all `analyze-*` commands.
- Leftover `DEBUG` prints removed from the CLI entry points.
- IFRS filers without US-GAAP revenue tags now reconstruct revenue.

### Known limitations

- Fisher's full 15 points require scuttlebutt (not implementable from
  filings); only the quantitative subset is scored.
- Greenblatt rankings require running `compute_greenblatt_rankings.py`
  periodically (weekly recommended); missing or > 30-day-old files read
  INSUFFICIENT_DATA.
- KO does not report R&D in XBRL; Fisher rule 1 returns INSUFFICIENT_DATA.
- ~17% of the analyzable universe (1,061 of 6,064 non-OTC companies) has no
  mapped revenue, almost all structurally revenue-less funds, trusts, SPACs
  and shells — see `docs/unmapped_coverage.md`.
- Financial companies abstain from the Greenblatt Magic Formula and the
  industrial ROC denominator.
