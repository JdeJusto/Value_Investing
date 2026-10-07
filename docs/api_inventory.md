# API Inventory — Value Investing Platform

> Roadmap issue: [#27](https://github.com/JdeJusto/Value_Investing/issues/27)

Generated: 2026-10-07

This document catalogs the existing surface area of the Value Investing project
to inform the design of an additive REST API (FastAPI) and a native Android app.

---

## A1 — CLI Commands

All commands from `main.py` (40 subcommands):

| Command | Description |
|---------|-------------|
| `screener` | Stock screener with fundamental filters (P/E, ROE, FCF yield, market cap, etc.) |
| `company` | Basic company information (name, sector, CIK, identifiers) |
| `consensus` | Show one ticker's consensus verdicts across all 8 methodologies |
| `consensus-ranking` | Rank the consensus file by BUYs, AVOIDs or score |
| `consensus-by-category` | Top companies per Lynch category by consensus score |
| `analyze` | Full fundamental analysis of one or more tickers |
| `analyze-full` | Consolidated 6-section report per ticker |
| `buffett-analysis` | Buffett analysis: filter, moat and composite score |
| `historical-valuation` | Show historical valuation ratios (P/E and FCF yield) from FDB + Yahoo |
| `load-data` | Download, normalize and persist historical financial data |
| `data-status` | Data quality, freshness and consistency status per ticker |
| `dcf` | Two-stage DCF valuation (not-from-canon, not a methodology) |
| `opportunities` | Detected opportunities: cheap quality, compounders, turnarounds |
| `anomalies` | Anomalies in the last fiscal year's fundamentals |
| `momentum` | Ranking by fundamental momentum |
| `portfolio` | Portfolio tracking: positions, PnL and allocation (subcommands: add, view, performance, exit, remove) |
| `backtest` | Backtesting over yearly snapshots (deterministic) |
| `alerts` | Evaluate buy/sell signals and events |
| `watchlist` | Track companies under monitoring (add, list) |
| `debug` | System diagnostics and quick tests |
| `sql-analysis` | Run reusable SQL scripts from Financial-DataBase |
| `filings` | List official SEC filings (10-K, 10-Q, 8-K, ...) with EDGAR links |
| `filing-balance-sheet` | Extract and print the balance sheet from a 10-K/10-Q |
| `filing-statement` | Extract a financial statement (balance sheet, income, cash flow) from a filing |
| `filing-income-statement` | Extract the income statement from a 10-K/10-Q |
| `filing-cash-flow` | Extract the cash flow statement from a 10-K/10-Q |
| `filing-section` | Extract a narrative section (Risk Factors, MD&A) from a filing |
| `financial-alerts` | Deterministic financial alerts (cash runway, margins, debt, FCF...) |
| `interactive` | Menu mode: pick a command, type its arguments, run it |
| `methodologies` | Multi-methodology engine commands (wrapper) |
| `analyze-graham` | Run the Graham defensive-investor screen on one company |
| `analyze-buffett-clark` | Run the Buffett/Clark DCA screen on one company |
| `analyze-buffett-classic` | Run the Buffett/Munger 4-pillar qualitative filter |
| `analyze-fisher-quant` | Run Fisher's 4 quantifiable points (R&D, margins, costs, dilution) |
| `analyze-graham-dodd` | Run the Graham & Dodd deep-value screen on one company |
| `analyze-lynch-garp` | Run the Lynch GARP (growth at a reasonable price) screen |
| `analyze-greenblatt` | Run the Greenblatt Magic Formula (weekly rankings) |
| `analyze-marks` | Run Howard Marks' measurable rules on one company |
| `compare-methodologies` | Compare methodologies side by side for one company |

**Total: 40 commands** — All read-only except `portfolio` (write) and `load-data` (write to FDB).

---

## A2 — Streamlit Pages

| File | Title | Purpose |
|------|-------|---------|
| `01_home.py` | Home | Daily snapshot: portfolio summary, latest report, quick actions |
| `02_analysis.py` | Analysis | Single-ticker deep dive with tabs: Overview, Methodologies, DCF, Financials, Filings, Compare |
| `03_screener.py` | Screener | Filters over master universe with explicit Run button; SQL pre-filters → analytics → verdict/category enrichment |
| `04_portfolio.py` | Portfolio | Positions + actions (add/exit/remove), performance/risk tabs; price refreshes in-memory until explicit save |
| `05_reports.py` | Reports | Browse and preview daily reports in `data/reports/` |
| `06_consensus.py` | Consensus | Aggregates 8 methodology verdicts: top by score, best per Lynch category, disagreement zone, full verdict matrix |

**Total: 6 pages** — All read from existing services; no business logic in pages.

---

## A3 — Backend Services Inventory

| Service | Public API (key classes/methods) | Reusable for API? |
|---------|----------------------------------|-------------------|
| `PriceService` | `get_current_price(ticker)`, `get_market_cap(ticker)`, `get_shares_outstanding(ticker)`, `get_dividend_yield(ticker)`, `get_price_at_fiscal_year_end(ticker, year)`, `get_historical_prices(ticker, start, end)`, `get_market_snapshots(tickers)` | **Yes** — core price data |
| `FinancialDatabaseRepository` | `get_best_available(ticker)`, `list_years(ticker)`, `get_fiscal_year_end_date(ticker, year)`, `get_company_name(ticker)`, `has_active_listing(ticker)`, `get_cik(ticker)` | **Yes** — FDB data access |
| `CompanyAnalysisService` | `analyze(ticker, no_prices=False)` → `AnalysisResult` with metrics, ratios, quality scores | **Yes** — fundamentals analytics |
| `StockScreenerService` | `screen(tickers, filters, top_n, progress_callback)` → `ScreenerRow` | **Yes** — screener logic |
| `ConsensusService` | `load_consensus()`, `get_company_consensus(ticker)`, `ranked` property | **Yes** — consensus data |
| `AlertEngine` | `run(tickers, progress_callback)` → `AlertEvent` | **Yes** — alerts |
| `PortfolioService` | `load()`, `save()`, `add_position()`, `exit_position()`, `remove_position()` | **Yes** — portfolio CRUD |
| `HistoricalValuationService` | `get_historical_valuation_summary(ticker)` | **Yes** — P/E + FCF yield history |
| `FinancialInsightsService` | `build_insights(ticker, fundamentals, price)` | **Yes** — narrative insights |
| `FinancialStatementParser` | `load_financial_statement(ticker, form, accession)` | **Yes** — filing statements |
| `FilingsService` | `get_filings(ticker, form=None)` | **Yes** — SEC filings list |
| `NarrativeExtractor` | `extract_section(text, section_type)` | **Yes** — filing sections |
| `RefreshService` | `ensure_fresh_and_prices(tickers, ...)` | **No** — server-side only |
| `DailyReportService` | `build_daily_report()` | **No** — batch job |
| `DataPipelineService` | `run_load_data(tickers, years, force)` | **No** — batch job |
| `SQLAnalysisService` | `run_script(name, params, format)` | **Maybe** — admin only |

**Total: ~27 service modules** — ~15 directly reusable for API endpoints.

---

## A4 — Repositories

| Repository | Purpose | Reusable for API? |
|------------|---------|-------------------|
| `FinancialDatabaseRepository` | Reads from Financial-DataBase PostgreSQL; implements `FinancialRepository` | **Yes** |
| `JsonFinancialRepository` | JSON fallback for normalized financials | **Yes** (fallback) |
| `JsonPortfolioRepository` | Reads/writes `data/portfolio.json` | **Yes** |

---

## A5 — Methodologies (8 book-based + DCF)

Each methodology implements `Methodology` ABC with `evaluate(ticker, fundamentals, prices) -> MethodologyResult`:

| Methodology | Family | Key Metrics |
|-------------|--------|-------------|
| `graham` | DEEP_VALUE | 7 criteria + combined P/E×P/BV test |
| `graham_dodd` | DEEP_VALUE | NWC, fixed charge coverage, earnings stability |
| `buffett_clark` | QUALITY_COMPOUNDER | Gross margin, interest burden, debt/equity, capex/FCF |
| `buffett_classic` | QUALITY_COMPOUNDER | 4 pillars: profitability, financial strength, cash gen, stability |
| `fisher_quantitative_subset` | QUALITY_COMPOUNDER | R&D intensity, margin quality, cost control, dilution |
| `greenblatt` | GARP | Magic Formula rank (ROC + EY) |
| `lynch_garp` | GARP | PEG, growth consistency, debt, inventory, dividend-adjusted PEG |
| `marks` | CYCLE_AWARE_VALUE | Cycle, resilience, margin of safety, quality persistence |

**DCF** (`DCFValuation`) — not-from-canon, uses WACC + 2-stage growth.

All are stateless, deterministic, testable — ideal for API reuse.

---

## A6 — API Exposure Decision Table

| Component | API Exposure? | Rationale |
|-----------|---------------|-----------|
| Fundamentals (FDB) | **Yes** | Core value prop; mobile needs financials |
| Prices (Yahoo, real-time) | **Yes** | Mobile needs live quotes |
| Methodologies verdicts | **Yes** | Core value prop |
| DCF | **Yes** | Valuation tool |
| Filings (list + statements + sections) | **Yes** | Deep dive capability |
| Financials view (all facts per year) | **Yes** | Tabular view for mobile |
| Insights | **Yes** | Narrative summaries |
| Alerts | **Yes** | Push/notifications target |
| Consensus | **Yes** | Aggregated view |
| Screener | **Yes** (with pagination) | Discovery tool |
| Portfolio (JSON) | **Yes** (read + write) | User's positions |
| Daily workflow | **No** | Server-side batch; not interactive |
| Database migrations | **No** | DevOps, not API |
| Scripts (build_demo, etc.) | **No** | Dev tools |
| `RefreshService` | **No** | Background sync, long-running |
| `DataPipelineService` | **No** | Batch ingestion |
| `YahooHealth` / streak metrics | **No** | Internal diagnostics |
| Demo mode | **Yes** | For mobile demo without backend |

**Summary:**
- **Exposed: ~15 service modules** covering all interactive features
- **Not exposed: ~12 modules** (batch jobs, dev tools, internal diagnostics)

---

## A7 — Data Formats & Conventions

| Convention | Detail |
|------------|--------|
| Monetary values | Strings with formatting preserved (`"$416.16B"`, `"$29,943"`) |
| Percentages | Decimals in JSON, formatted strings in UI (`0.1234` → `"12.34%"`) |
| Dates | ISO 8601 UTC (`"2026-10-07T18:30:00Z"`) |
| Tickers | Always uppercase |
| Null handling | `null` in JSON; UI renders as `"N/A"` |
| Enum values | String representation (`"BUY"`, `"SLOW_GROWER"`) |
| Pagination | `?page=1&page_size=50` with `meta.total`, `meta.page`, `meta.page_size` |
| Errors | HTTP codes + JSON: `{"error": {"code": "TICKER_NOT_FOUND", "message": "..."}}` |

---

## A8 — Files Created by This Inventory

- `docs/api_inventory.md` — this file
- Feeds: `docs/api_design.md`, `docs/mobile_app_design.md`, `docs/api_roadmap.md`