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
The Financial-DataBase project (/home/caudillo/Financial-DataBase) contains a comprehensive SEC EDGAR database with:
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

**prices** table:
- Provides historical price data via `company_listings` → `companies` join
- `price_date`, `open`, `high`, `low`, `close`, `volume`

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

## New Components to Create

### 1. FinancialDatabaseRepository
New repository implementation in `backend/repositories/financial_database_repository.py` that:
- Connects to Financial-DataBase PostgreSQL database
- Implements `FinancialRepository` interface
- Queries financial_facts table to reconstruct NormalizedFinancials
- Handles provider mapping (SEC EDGAR → ProviderName.EDGAR)
- Includes fallback logic to existing providers

### 2. Configuration Updates
- Add `FINANCIAL_DATABASE_URL` environment variable
- Update `build_financial_repository()` in `backend/app/cli.py` to try Financial-DataBase first

### 3. Provider Mapping
Create mapping between Financial-DataBase provider names and Value Investing ProviderName enum:
- 'SEC EDGAR' → ProviderName.EDGAR
- 'Yahoo Finance' → ProviderName.YAHOO

## Environment Variables

Add to `.env`:
```
FINANCIAL_DATABASE_URL=postgresql://financial:test@localhost:5432/financial_database
```

## Key Commands (CLI)

All standard CLI commands will automatically use Financial-DataBase when available:
- `pipenv run python main.py load-data AAPL` - Load data from Financial-DataBase
- `pipenv run python main.py analyze AAPL` - Analyze using cached data
- `pipenv run python main.py screener` - Screen using cached data
- `pipenv run python main.py buffett-analysis AAPL` - Buffett analysis using cached data
- `pipenv run python main.py opportunities` - Find opportunities using cached data

## Testing Instructions

### Running Existing Tests
```bash
source .venv/bin/activate
python -m pytest tests/unit -q
```

### Testing Financial-DataBase Integration
1. Ensure Financial-DataBase is running and accessible:
   ```bash
   cd /home/caudillo/Financial-DataBase
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

### Reference Files (Financial-DataBase)
- `/home/caudillo/Financial-DataBase/src/financial_database/db/migrations/` - Schema migrations
- `/home/caudillo/Financial-DataBase/scripts/analysis/` - Reusable SQL analysis scripts
- `/home/caudillo/Financial-DataBase/src/financial_database/providers/price/yfinance_importer.py` - Existing Yahoo price importer

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
- [ ] Implement price data mapping from prices table
- [ ] Add company listings and exchange information mapping
- [ ] Implement proper error handling and logging
- [ ] Add caching layer for performance
- [ ] Implement batch operations for efficiency
- [ ] Add health check/database availability detection

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