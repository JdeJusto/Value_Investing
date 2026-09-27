# Value Investing Project - AI Agent Guidelines

This file provides comprehensive guidelines and reference information for AI assistants (like Claude) working on the Value Investing project, especially regarding integration with the Financial-DataBase project.

## Project Overview

Value Investing is a terminal-based fundamental analysis platform with:
- CLI for data loading, analysis, screening, portfolio management, backtesting, and alerts
- Streamlit web UI for interactive screening and analysis
- Multi-source data pipeline (Yahoo Finance + SEC EDGAR) with automatic fallback
- Deterministic financial analysis (no ML, no social media dependencies)
- PostgreSQL storage option (with JSON fallback)
- Company quality assessment (Buffett-style), moat analysis, scoring models
- Fundamental screening, opportunity detection, portfolio tracking, backtesting, and alerting

## Architecture Summary

### Layers
1. **Presentation Layer**: CLI (`cli/`), Streamlit UI (`ui/`)
2. **Application Layer**: Commands (`cli/commands/`), Services (`backend/services/`)
3. **Domain Layer**: Entities (`backend/domain/entities/`), Value Objects (`backend/domain/value_objects/`), Interfaces (`backend/domain/interfaces/`)
4. **Infrastructure Layer**: 
   - Providers (`backend/providers/`) - Yahoo Finance, EDGAR
   - Repositories (`backend/repositories/`) - SQL (PostgreSQL) and JSON
   - Normalizers (`backend/providers/normalizers/`) - Convert provider data to canonical format
   - Analytics (`backend/analytics/`) - Ratios, DCF, scoring, quality metrics
   - Intelligence (`backend/intelligence/`) - Buffett engine, moat analysis, anomaly detection
   - Portfolio, Screener, Backtesting, Alerts, Watchlist modules

### Key Interfaces
- `FinancialDataProvider` (domain/interfaces/provider.py): Fetches raw financial statements
- `FinancialRepository` (domain/interfaces/financial_repository.py): Persists normalized financials
- `MarketDataProvider` (domain/interfaces/provider.py): Fetches market data (prices, market cap, etc.)

### Data Flow
```
[User Command] 
    → [CLI Command Handler] 
        → [Service Layer (e.g., DataPipelineService)] 
            → [Providers (Yahoo/EDGAR)] 
                → [Raw Financial Statements] 
                    → [Normalizers] 
                        → [NormalizedFinancials (canonical format)] 
                            → [Repository (PostgreSQL/JSON)] 
                                → [Storage]
                                    ← [Analytics/Services consume NormalizedFinancials]
```

## Current Data Sources and Storage Options

### Data Providers
1. **Yahoo Finance Provider** (`backend/providers/yahoo/provider.py`):
   - Fetches income statements, balance sheets, cash flow statements
   - Gets market data (price, market cap, beta, shares outstanding)
   - Uses yfinance library

2. **EDGAR Provider** (`backend/providers/edgar/provider.py`):
   - Fetches financial statements from SEC EDGAR using edgartools
   - Gets income statements, balance sheets, cash flow statements

### Storage Options
1. **PostgreSQL Repository** (`backend/repositories/financial_repository.py`):
   - Uses SQLAlchemy with `NormalizedFinancialModel`
   - Stores one record per (ticker, fiscal_year, period, source)
   - Supports multiple sources per record (provider-agnostic upsert)

2. **JSON Repository** (`backend/repositories/json_financial_repository.py`):
   - Stores normalized financials as JSON files
   - Fallback when PostgreSQL is unavailable

### Configuration
Environment variables in `.env`:
- `DATABASE_URL`: PostgreSQL connection string (default: postgresql://postgres:postgres@localhost:5432/value_investing)
- `SEC_EMAIL`: Email for SEC EDGAR identification
- `SEC_NAME`: Name for SEC EDGAR identification
- `PORTFOLIO_PATH`: Path to portfolio JSON file

## Integration with Financial-DataBase

### Overview
The Financial-DataBase project (~/Financial-DataBase) contains a comprehensive SEC EDGAR database with:
- 8,023+ companies
- 76M+ financial facts  
- 1.09M+ filings
- Historical data from 2009 onward
- Stock prices from Yahoo Finance
- Reusable SQL analysis scripts

### Integration Strategy
Replace Value Investing's current data fetching (Yahoo/EDGAR on-demand) with queries to the Financial-DataBase PostgreSQL database, falling back to existing providers when needed.

### Database Mapping
Financial-DataBase Schema → Value Investing NormalizedFinancials:

**companies** table:
- `legal_name` → `name` (via Company entity)
- `sector` → `sector` 
- `industry` → `industry`
- `country` → Not directly stored (could be added to Company)

**company_identifiers** table:
- Links companies to identifiers (CIK, ticker, etc.) via `company_id`
- `identifier_type = 'CIK'` and `identifier_value` provides the CIK
- `provider_id` links to data_providers (to identify SEC EDGAR source)

**financial_facts** table (main source of financial data):
- `concept` → Maps to financial statement line items (Revenue, NetIncome, etc.)
- `value` → The numeric value
- `unit` → Currency/units (USD, shares, etc.)
- `fiscal_year`, `fiscal_period` → Time dimension
- `company_id` → Links to company
- `provider_id` → Identifies SEC EDGAR as source

> **Prices are NOT stored in Financial-DataBase for analytics.** Real-time and
> historical prices are fetched on demand from Yahoo Finance through
> `backend/services/price_service.py` (PriceService) with a short in-memory
> cache (default 15 min, `PRICE_CACHE_TTL`). Nothing price-related is read from
> or written to the `prices` table by Value Investing code.

**company_listings** table:
- Links companies to exchange listings
- `exchange_id` links to exchanges table

### Key Tables for Integration
1. `companies` - Company metadata
2. `company_identifiers` - CIK/ticker mappings  
3. `financial_facts` - Normalized financial data (main source)
4. `prices` - Historical price data
5. `company_listings` - Exchange listings
6. `exchanges` - Exchange information
7. `data_providers` - Source identification (SEC EDGAR, Yahoo Finance)

## New Components Created

### 1. FinancialDatabaseRepository
Repository implementation in `backend/repositories/financial_database_repository.py` that:
- Connects to Financial-DataBase PostgreSQL database
- Implements `FinancialRepository` interface
- Queries financial_facts table to reconstruct NormalizedFinancials
- Handles provider mapping (SEC EDGAR → ProviderName.EDGAR)
- Includes fallback logic to existing providers
- Provides fundamentals, shares outstanding, fiscal year end dates
  (`get_fiscal_year_end_date` ranks core 'FY' facts by calendar-year match —
  the bucket's own fiscal year — first, then period span, then latest
  period_end, so a 10-K comparative that a sync mislabels under the current
  fiscal_year cannot hijack the year end even when its annual span is longer)
- Does NOT expose price methods (prices live in PriceService, not the DB)

### 2. PriceService
Service in `backend/services/price_service.py` that:
- Fetches current and historical prices from Yahoo Finance in real time
- Provides `get_current_price`, `get_historical_prices`, `get_price_on_date`,
  `get_price_at_fiscal_year_end`, `get_shares_outstanding`,
  `get_split_adjustment`
- Never persists prices — in-memory cache only (TTL default 900 s)
- `get_split_adjustment` aligns as-reported shares with split-adjusted Yahoo
  prices so historical per-share metrics stay consistent across stock splits

### 3. HistoricalValuationService
Service in `backend/services/historical_valuation_service.py` that:
- Calculates historical P/E ratios and FCF yield from fundamentals
  (Financial-DataBase) + real-time prices (PriceService)
- Prices are fetched on demand and never persisted
- FCF falls back to OCF − capex when direct FreeCashFlow is missing
- Provides formatted table output for easy visualization

### 4. SQL Analysis Service
Service in `backend/services/sql_analysis_service.py` that:
- Executes reusable SQL scripts from Financial-DataBase's scripts/analysis directory
- Handles parameter binding (especially CIK/ticker conversion, `:ciks::text[]`
  arrays for multi-company scripts)
- Resolves script aliases (`compare` → `compare_companies`)
- Supports multiple output formats (table, JSON, CSV)
- Includes helper methods for common scripts like company_overview

### 5. Data Comparison Script
Script in `scripts/compare_sources.py` that:
- Compares ONLY fundamentals from Financial-DataBase with Yahoo Finance and EDGAR providers
- Anchors on the latest completed fiscal year (period='FY'), not the in-progress year

### 5b. Screener ranking calibration

The screener ranks the analyzed universe with `calibrated_rank`
(`backend/screener/ranking_engine.py`), a cross-sectional score that
percentile-ranks each component and blends quality 0.55 / value 0.20 /
momentum 0.10 / growth 0.05 / stability 0.05 / confidence 0.05, mapping onto
a 10-90 band. Companies with negative FCF, debt-to-equity ≥ 1.5, or interest
coverage < 3x are capped at `LEVERAGED_RANK_CAP = 60`. Signal thresholds
(`backend/screener/signals.py`): BUY ≥ 75, WATCHLIST ≥ 60, AVOID when
buffett < 40. See `docs/scoring_methodology.md` and `docs/scoring_validation.md`.

Data quality is derived when the repository has no `data_quality_score`:
`backend/analytics/service.py::_data_reliability` uses history depth
(`min(years, 8) / 8`) and coverage; `confidence_level()` in
`backend/intelligence/scoring_model.py` maps quality + coverage to LOW /
MEDIUM / HIGH. The analytics service compares DCF value (total) to
market_cap (total) for the margin of safety and filters out in-progress,
all-empty fiscal year rows before computing ratios.

The default daily universe comes from `config/universe.csv` — the **master
universe** built by `scripts/build_universe.py` from per-index source files
(S&P 500 + Nasdaq-100 via `scripts/fetch_universe.py`, Russell 2000 via
`scripts/fetch_russell2000.py` from the official iShares IWM holdings snapshot,
and nine European indices via `scripts/fetch_european_indices.py`).
Fundamentals come exclusively from SEC filings, so only companies with an SEC
EDGAR CIK are kept in the master: European ADRs / 20-F / 40-F filers are
analyzable, European non-filers and Russell names without a CIK are excluded
but stay flagged in their per-index files. Tickers resolve to SEC CIKs via
Financial-DataBase. `scripts/validate_universe_against_fdb.py` gates the master
at ≥ 80% FDB coverage (exit code ≠ 0 below it; unresolved list capped at 100).
`scripts/daily_workflow.py` selects a universe with `--universe
sp500|nasdaq100|sp500,nasdaq100|russell2000|european|all|<file>` (default
`sp500`), caps the targeted SEC refresh with `--max-refresh N` (default 200,
stale companies with the most recent filings first, deferred the rest), supports
`--limit`, `--batch-size`, `--batch-delay`, `--workers` (parallel price
prefetch + analysis; default 4, env `WORKFLOW_WORKERS`; the quote-summary
snapshot prefetch tolerates up to 6 — `SNAPSHOT_WORKERS_CAP` — because a
100-ticker probe saw 0 failures there, while `history()` bursts throttle at
2; the prefetch stays batched and retries once), `--refresh-workers N`
(concurrent targeted `sec sync <CIK>` subprocesses, default 2 from
`config/refresh.yaml` → `refresh_workers`, env `REFRESH_WORKERS`), `--resume`
(skips tickers already in the previous `daily_state.json`) and pre-warms
the price cache before analysis.
- Compares 6 fundamental fields (revenue, net income, assets, liabilities,
  operating cash flow, capital expenditures); prices are never compared
- Flags significant discrepancies (>5%) for further investigation
- Provides side-by-side comparison in readable table format

### 5c. On-demand SEC refresh (RefreshService)

`backend/services/refresh_service.py` is the integration point between the
analysis commands and Financial-DataBase ingestion:

- `RefreshService.ensure_fresh_and_prices(tickers, force=..., max_age_hours=...,
  skip_refresh=..., fetch_prices=...)` returns a `RefreshResult` with
  `refreshed` / `skipped` / `failed` and `prices`.
- It only ever acts on **the tickers being analyzed**: for each stale company
  it runs a targeted subprocess `sec sync <CIK>` via the Financial-DataBase
  CLI. The full universe is never synced through this service; universe-wide
  runs (no explicit tickers) skip the sync unless `--refresh` is passed.
- Freshness per company comes from `max(financial_facts.updated_at)` /
  `max(filings.created_at)` — `import_runs` has no per-CIK column.
  `FdbGateway` (a read-only gateway) resolves ticker→CIK via
  `company_listings` / `company_identifiers`, so the refresh keys on
  Financial-DataBase's `company_id`.
- Prices are fetched through `PriceService` (Yahoo, in-memory cache only) and
  **never persisted**.
- Degradation: DB unreachable, missing `SEC_USER_AGENT`, SEC timeouts and
  unknown tickers are reported as skipped/failed with clear messages; the
  analysis command continues with existing data.
- Config: `config/refresh.yaml` (`auto_refresh`, `freshness_max_age_hours=168`,
  `refresh_timeout_seconds=300`, `skip_refresh_flag`), env overrides
  `REFRESH_AUTO` / `FRESHNESS_MAX_AGE_HOURS` / `REFRESH_TIMEOUT_SECONDS` /
  `REFRESH_SKIP_FLAG`, and CLI flags
  `--refresh` / `--no-refresh` / `--freshness-hours N` (added with
  `backend.app.cli.add_refresh_arguments`).

### 5d. Alert calibration (BUY_SIGNAL / SELL_WARNING / TRIGGER_EVENT)

The daily alert evaluation (`backend/alerts/alert_engine.py::run`, wired in
`scripts/daily_workflow.py`) produces three alert types:

- **TRIGGER_EVENT** — only the dominant *positive* fundamental improvement
  (margin expansion / revenue acceleration / ROIC improvement / FCF surge).
  A positive delta must clear an absolute floor (margin ≥ 2pp, revenue
  acceleration ≥ 5pp, ROIC ≥ 3pp, FCF growth ≥ 20% **with positive FCF**)
  **and** a cross-sectional percentile floor of that delta across the
  analyzed universe (`calibrate_trigger_thresholds` in
  `backend/screener/signals.py`, default quantile 0.92; effective threshold
  = max(floor, percentile); skipped below 20 samples so isolated,
  single-company evaluations keep the absolute floors). Improvements must be
  persistent over two consecutive periods where the data permits
  (`*_delta_prev` fields in `backend/intelligence/delta_metrics.py`).
  Deterioration is deliberately **not** a trigger — SELL_WARNING (score
  drops ≥ 10 pts vs the previous day's `daily_state.json`) and anomaly
  reporting cover it.
- **BUY_SIGNAL** — `generate_signal` = BUY (rank ≥ 75, composite ≥ 70,
  confidence HIGH/MEDIUM, buffett ≥ 50; with LOW confidence a materially
  stronger bar applies: rank ≥ 80, composite ≥ 75, buffett ≥ 50).
- **SELL_WARNING** — composite total score drops ≥ 10 pts (HIGH ≥ 15) vs
  the previous day; universe-wide, 0 fires when scores are stable.

Expected counts on the ~500-company daily universe: TRIGGER_EVENT ≈ 6-12%
(~30-60, 58 observed on 2026-09-22, ceiling 80), BUY_SIGNAL ≈ 10-40,
SELL_WARNING ≈ 0-5. See
`docs/scoring_methodology.md` (Alerts and trigger calibration) and
`docs/runbook_daily.md`.

### 5. Configuration Updates
- Add `FINANCIAL_DATABASE_URL` environment variable
- Update `build_financial_repository()` in `backend/app/cli.py` to try Financial-DataBase first

### 6. Provider Mapping
Create mapping between Financial-DataBase provider names and Value Investing ProviderName enum:
- 'SEC EDGAR' → ProviderName.EDGAR
- 'Yahoo Finance' → ProviderName.YAHOO

## Environment Variables

Add to `.env`:
```
FINANCIAL_DATABASE_URL=postgresql://financial:test@localhost:5432/financial_database
```

The on-demand refresh step also honors:
- `SEC_USER_AGENT`: required for the targeted `sec sync <CIK>` (see
  Financial-DataBase `.env.example`); without it the refresh step reports a
  clear failure and analysis continues.
- `FINANCIAL_DATABASE_REPO_PATH`: where the Financial-DataBase checkout lives
  (default: sibling directory of this repo).
- `REFRESH_AUTO` / `FRESHNESS_MAX_AGE_HOURS` / `REFRESH_TIMEOUT_SECONDS` /
  `REFRESH_SKIP_FLAG`: environment overrides for `config/refresh.yaml`.

## Key Commands (CLI)

All standard CLI commands will automatically use Financial-DataBase when available.
`pipenv run python ...` is the documented form; on machines without pipenv the
wrapper `./vi <argv>` is equivalent to
`<repo>/.venv/bin/python main.py <argv>`, and scripts run via
`<repo>/.venv/bin/python scripts/<script>.py` or
`.venv/bin/python -m scripts.daily_workflow` (venv activated).
- `pipenv run python main.py load-data AAPL` - Load data from Financial-DataBase
- `pipenv run python main.py analyze AAPL` - Analyze using cached data
- `pipenv run python main.py screener` - Screen using cached data
- `pipenv run python main.py buffett-analysis AAPL` - Buffett analysis using cached data
- `pipenv run python main.py opportunities` - Find opportunities using cached data

Universe pipeline (regenerate + validate the master `config/universe.csv`):
- `pipenv run python scripts/fetch_universe.py` - S&P 500 + Nasdaq-100 (Wikipedia)
- `pipenv run python scripts/fetch_russell2000.py` - Russell 2000 (iShares IWM holdings)
- `pipenv run python scripts/fetch_european_indices.py` - Nine European indices (SEC-filer flag)
- `pipenv run python scripts/build_universe.py` - Merge + dedup → `config/universe.csv`
- `pipenv run python scripts/validate_universe_against_fdb.py` - Coverage gate (≥ 80%)
- `pipenv run python -m scripts.daily_workflow --universe russell2000` - Run a named subset

## Testing Instructions

### Running Existing Tests
```bash
source .venv/bin/activate
python -m pytest tests/unit -q
```

### Testing Financial-DataBase Integration
1. Ensure Financial-DataBase is running and accessible:
   ```bash
   cd ~/Financial-DataBase
   # Verify database is accessible
   psql postgresql://financial:test@localhost:5432/financial_database -c "SELECT COUNT(*) FROM companies;"
   ```

2. Set environment variable:
   ```bash
   export FINANCIAL_DATABASE_URL="postgresql://financial:test@localhost:5432/financial_database"
   ```

3. Run tests that exercise the data loading path:
   ```bash
   python -m pytest tests/unit/test_data_pipeline.py -v
   python -m pytest tests/unit/test_repository.py -v
   ```

## Cross-Source Validation (`scripts/validate_sp500.py`)

- The S&P 500 validation cross-checks Value Investing fundamentals (read from
  Financial-DataBase, SEC EDGAR derived) against Yahoo Finance. Methodology,
  thresholds, and known expected differences:
  `docs/validation_methodology.md`. Current results and the classification of
  every excluded row: `docs/validation_report_200_sp500.md`.
- **Validations must respect `config/validation_exclusions.yaml`** — do not
  hand-edit `data/validation_discrepancies_200.csv`. To add or change an
  exclusion, edit that YAML (ticker + metric, `metric: "*"` = all metrics,
  plus a `classification` and a `reason`), then rerun
  `python -m scripts.validate_sp500 compare`. A rule must never be added just
  to silence noise; it needs a root-cause reason.
- Excluded rows are counted separately in the `compare` summary
  (genuine vs excluded per severity). A `HIGH genuine` count greater than zero
  means unflagged HIGH discrepancies remain and should be investigated.

## Important Files and Directories

### To Modify/Create
- `backend/repositories/financial_database_repository.py` - NEW: Financial-DataBase repository adapter
- `backend/app/cli.py` - Modify `build_financial_repository()` to prioritize Financial-DataBase
- `.env.example` - Add FINANCIAL_DATABASE_URL variable
- `.env` - Add actual database URL

### Key Existing Files
- `backend/app/cli.py` - Service construction (where repository is chosen)
- `backend/repositories/financial_repository.py` - Current SQL repository
- `backend/repositories/json_financial_repository.py` - JSON fallback repository
- `backend/domain/interfaces/financial_repository.py` - Repository interface
- `backend/domain/value_objects/financials_normalized.py` - NormalizedFinancials definition
- `backend/services/data_pipeline_service.py` - Main data loading pipeline
- `scripts/universe_common.py` - SEC ticker/CIK map, European matching, index registry
- `scripts/fetch_universe.py` - S&P 500 + Nasdaq-100 fetch (→ `config/universe_sp500_nasdaq.csv`)
- `scripts/fetch_russell2000.py` - Russell 2000 fetch from iShares IWM holdings
- `scripts/fetch_european_indices.py` - European index fetch + SEC-filer flagging
- `scripts/build_universe.py` - Merge per-index files into master `config/universe.csv`
- `scripts/validate_universe_against_fdb.py` - FDB coverage gate (≥ 80%, exit-code gate)
- `scripts/daily_workflow.py` - Daily run; `--universe` subsets, `--max-refresh`, `--resume`

### Reference Files (Financial-DataBase)
- `~/Financial-DataBase/src/financial_database/db/migrations/` - Schema migrations
- `~/Financial-DataBase/scripts/analysis/` - Reusable SQL analysis scripts
- `~/Financial-DataBase/src/financial_database/providers/price/yfinance_importer.py` - Existing Yahoo price importer

## Conventions and Rules

### Architectural Rules
1. **Deterministic**: Same input always produces same output (no randomness in domain)
2. **No ML in domain**: Machine learning only in isolated intelligence components if ever added
3. **No pandas in domain**: Domain objects use plain Python/types; pandas only in analytics/reporting
4. **Provider agnosticism**: Repositories and services know nothing about Yahoo/EDGAR internals
5. **Interface segregation**: Depend on interfaces, not implementations
6. **Fail fast**: Clear error messages when configuration is wrong
7. **Fallback strategy**: If primary data source unavailable, automatically fallback

### Coding Conventions
- Follow PEP 8 style guide
- Use type hints for all function signatures
- Document public APIs with docstrings
- Handle exceptions appropriately at boundaries
- Write descriptive commit messages
- Keep functions focused on single responsibility

## Known Limitations

### Current Limitations
1. **JSON repository limitations**: Only stores latest normalized state, no historical versioning
2. **Provider switching**: Current implementation doesn't easily mix providers for same ticker/year
3. **Price data granularity**: Daily prices only; no intraday data in current schema

### Integration-Specific Limitations
1. **Schema mismatch**: Financial-DataBase uses UUID primary keys; Value Investing uses ticker-based lookups
2. **Concept mapping**: Need to map Financial-DataBase XBRL concepts to Value Investing financial statement line items
3. **Temporal alignment**: Financial-DataBase stores period_start/period_end; Value Investing uses fiscal_year/period
4. **Data freshness**: Financial-DataBase requires explicit update commands; Value Investing fetches on demand
5. **Exchange mapping**: Need to map Financial-DataBase exchange IDs to Value Investing exchange handling
6. **Real-time prices**: Prices are fetched from Yahoo on demand and cached in
   memory only (never persisted); metrics that need prices degrade to "N/A" when
   the network or Yahoo is unavailable
7. **Split adjustment**: Split-adjusted Yahoo prices are reconciled with
   as-reported shares via `PriceService.get_split_adjustment`; without Yahoo
   split history, as-reported figures are used as-is

## Next Steps for Full Integration

### Phase 1: Basic Repository Adapter (Current Focus)
- [x] Explore both projects' architectures
- [x] Create AGENTS.md documentation
- [ ] Create FinancialDatabaseRepository implementing FinancialRepository interface
- [ ] Map financial_facts to NormalizedFinancials
- [ ] Implement basic CRUD operations (upsert, get_by_year, list_years, etc.)
- [ ] Add configuration and environment variable support
- [ ] Modify build_financial_repository() to try Financial-DataBase first
- [ ] Test with single ticker (AAPL) load-data command

### Phase 2: Enhanced Features
- [x] Implement real-time price service (PriceService, yfinance, no persistence) (completed)
- [x] Add company listings and exchange information mapping (completed)
- [x] Implement proper error handling and logging (completed)
- [ ] Add caching layer for performance
- [ ] Implement batch operations for efficiency
- [x] Add health check/database availability detection (completed)
- [x] Implement historical valuation calculations (P/E and FCF yield) (completed)
- [x] Create SQL analysis service for running Financial-DataBase reusable SQL scripts (completed)
- [x] Create data comparison script to compare Financial-DataBase with other providers (completed)

### Phase 3: Advanced Integration
- [ ] Implement bi-directional sync (Value Investing → Financial-DataBase)
- [ ] Add support for Financial-DataBase's reusable SQL analysis scripts
- [ ] Implement incremental update coordination
- [ ] Add comprehensive test suite for the new repository
- [ ] Performance optimization and indexing recommendations

### Phase 4: Production Readiness
- [ ] Documentation updates for users
- [ ] Migration guide for existing users
- [ ] Backup and recovery procedures
- [ ] Monitoring and health check endpoints
- [ ] Load testing and performance benchmarks

## Troubleshooting

### Common Issues
1. **Connection failures**: 
   - Verify FINANCIAL_DATABASE_URL is correct
   - Check that Financial-DataBase PostgreSQL is running
   - Ensure network connectivity between projects

2. **Schema mismatches**:
   - Run migrations in Financial-DataBase if needed
   - Verify table structures match expectations
   - Check that required data exists (companies, identifiers, financial_facts)

3. **Data mapping issues**:
   - Verify concept mapping tables are correct
   - Check that financial data reconstructs properly
   - Validate that normalized values match expectations

4. **Fallback not working**:
   - Check repository priority order in build_financial_repository()
   - Verify exception handling in repository methods
   - Test with Financial-DataBase database stopped/disconnected

### Debugging Commands
```bash
# Test Financial-DataBase connection manually
psql "$FINANCIAL_DATABASE_URL" -c "SELECT COUNT(*) FROM companies;"

# Check if AAPL data exists in Financial-DataBase
psql "$FINANCIAL_DATABASE_URL" -c "
SELECT c.legal_name, COUNT(f.fiscal_year) as years_with_data
FROM companies c
JOIN company_identifiers ci ON c.id = ci.company_id
JOIN financial_facts f ON c.id = f.company_id
WHERE ci.identifier_type = 'CIK' 
  AND ci.identifier_value = '0000320193'
  AND ci.provider_id = (SELECT id FROM data_providers WHERE name = 'SEC EDGAR')
GROUP BY c.legal_name;
"

# Test Value Investing with Financial-DataBase
FINANCIAL_DATABASE_URL="postgresql://financial:test@localhost:5432/financial_database" \
pipenv run python main.py load-data AAPL --years 2
```

## Contact
For questions about the Value Investing project or Financial-DataBase integration, consult:
- README.md for general project information
- Source code comments and docstrings for technical details
- Existing tests for usage examples
- Financial-DataBase project documentation for database specifics

Last updated: 2026-09-06