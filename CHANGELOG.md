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
