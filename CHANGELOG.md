# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
