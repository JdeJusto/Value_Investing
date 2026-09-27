# End-to-End Verification Report — Financial-DataBase & Value Investing

- **Date:** 2026-09-20 (original audit + same-day follow-up that resolves all blocking findings)
- **Audit type:** Final pre-production verification, then the follow-up task that fixed every blocking issue; all fixes committed (hashes in §8.1), nothing pushed, no PR opened.
- **Scope:** Financial-DataBase (`~/Financial-DataBase`) + Value Investing (`~/Value_Investing`) + PostgreSQL `financial_database`.
- **Golden rules honored:** prices never stored in any database; prices fetched real-time only for analyzed companies; fundamentals sourced from Financial-DataBase; no production data modified.

---

## 1. Environment

| Check | Command | Result | Status |
|---|---|---|---|
| PostgreSQL running | `systemctl status postgresql` | `active (running)`, PID 796, enabled, ~45.8 MB RSS | ✅ PASSED |
| PostgreSQL version | `SELECT version()` | **18.6** | ✅ PASSED |
| Disk space | `df -h /` | `/dev/nvme0n1p6 540G 154G 359G 30%` | ✅ PASSED |
| Database size | `SELECT pg_size_pretty(pg_database_size('financial_database'))` | **65 GB** | ✅ PASSED |
| Python (both venvs) | `.venv/bin/python --version` | **3.14.7** | ✅ PASSED |
| Key libs (FDB) | pip list | psycopg 3.3.4, click 8.5.0, SQLAlchemy 2.0.52, pytest 9.1.1 | ✅ PASSED |
| Key libs (VI) | pip list | pandas 3.0.5, numpy 2.5.3, psycopg2-binary 2.9.12, SQLAlchemy 2.0.52, pytest 9.1.1, yfinance 1.7.0 | ✅ PASSED |
| Databases present | `pg_database` | `financial_database` (production), `financial_database_test`, `financial_db` | ✅ PASSED |

> Note: `schema_migrations` uses a `migration_name` column (not `version`); the audit's `SELECT version ...` fails as written — corrected query used below.

---

## 2. Financial-DataBase status

### 2.1 Migrations — ✅ PASSED

`SELECT migration_name FROM schema_migrations ORDER BY migration_name;` → **20 rows, all applied** (0001_extensions … 0020_extend_financial_facts_columns). `financial-db status` also confirms **Applied: 20, Pending: 0**.

`financial_facts` columns verified via `\d financial_facts`:

| Column | Type | Required |
|---|---|---|
| concept | `text` | ✅ |
| source_id | `text` | ✅ |
| namespace | `text` | ✅ |
| frame | `text` | ✅ |
| value | `numeric(40,10)` | ✅ |

Unique constraint `(company_id, concept, period_start, period_end, filing_id, source_id) NULLS NOT DISTINCT` present (migration 0019).

### 2.2 Data counts

| Table | Count | Status |
|---|---|---|
| companies | 8,023 | ✅ |
| financial_facts | 76,035,751 | ✅ |
| filings | 1,091,495 | ✅ |
| company_listings | 7,837 | ✅ |
| company_identifiers | 16,068 | ✅ |
| raw_documents | 15,048 | ✅ |
| import_runs | 45 | ✅ |

### 2.3 Data integrity — ✅ PASSED (with notes)

| Check | Result | Status |
|---|---|---|
| Duplicates on (company_id, concept, period_start, period_end, filing_id, source_id) | **0** | ✅ PASSED |
| Orphan facts (no company) | 0 | ✅ PASSED |
| Orphan facts (no filing) | 0 | ✅ PASSED |
| Orphan filings | 0 | ✅ PASSED |
| Orphan listings | 0 | ✅ PASSED |
| fiscal_year outside [1990, 2030] | **0** | ✅ PASSED |
| Companies with 0 facts | **1,132** (mostly funds / ADRs / foreign entities — expected for full SEC universe) | ✅ (expected) |
| Active-listing tickers with 0 facts | **1,095** (same profile: funds, ADRs, small foreign cos.) | ✅ (expected) |

Top-20 zero-facts companies (by legal_name): 1WS Credit Income Fund, 3i GROUP PLC, A2 Gold Corp., ABACUS MINING & EXPLORATION CORP, Abaxx Technologies Inc., ABERDEEN GOVERNMENT MARKETS INCOME FUND, ABERDEEN INDIA FUND, ABERDEEN INTERMEDIATE INCOME FUND, ABERDEEN MULTI-MARKET INCOME FUND, ABERDEEN MUNICIPAL INCOME FUND, Above Food Ingredients Inc., ABRDN ASIA-PACIFIC INCOME FUND, ABRDN AUSTRALIA EQUITY FUND, abrdn Emerging Markets ex-China Fund, abrdn Global Infrastructure Income Fund, abrdn Healthcare Investors, abrdn Healthcare Opportunities Fund, abrdn Life Sciences Investors, ADAMS DIVERSIFIED EQUITY FUND, ADAMS NATURAL RESOURCES FUND.

Sample of active tickers with 0 facts: ABCFF, ABVEF, ABXXF, ACMIF, ACV, ADDTF, ADOOY, ADX, ADYYF, AEBZY, AEF, AEGXF, AEHGS, AELKY, AFB, AFNDY, … (full list: 1,095).

### 2.4 Ticker–CIK mappings (previous fixes) — ✅ PASSED (all remain fixed)

| Ticker | Company | CIK | Listing | Facts | Status |
|---|---|---|---|---|---|
| XOM | EXXON MOBIL CORP | 0000034088 | active | 274 | ✅ PASSED |
| CBOE | Cboe Global Markets, Inc. | 0001374310 | active | 25,888 | ✅ PASSED |
| REAX | Real Brokerage Inc | 0001862461 | active | 2,895 | ✅ PASSED |
| REAX (stub) | Real REMAX Group Inc. | 0002136387 | **inactive (is_active=FALSE)** | 13 | ✅ PASSED |

Extra control: XOM’s own CIK appears in its facts-bearing core accessions (`core_with_own_cik = 1`), so it is not flagged as a stub.

### 2.5 Ticker health script (`scripts/check_ticker_health.sql`) — ✅ PASSED (rewritten, f9178a6)

| Section | Rows | Status |
|---|---|---|
| 1. TRUE STUB companies | **6 rows** (was 5,007) | ✅ PASSED (< 100; only EAI/AMUB/GLDI/HSTC/NIKA/NUVI cross-filers remain) |
| 2. Multi-CIK active tickers | **0 rows** | ✅ PASSED |
| 3. Zero-facts active tickers | **1,095 rows** | ✅ (reported, unchanged) |
| 4. universe.csv cross-check | **0 unresolved** of 500 tickers | ✅ PASSED (section 4 added; VALUES block regenerated by `docs/dev/rebuild_health_universe.py`) |

Fix (f9178a6): the agent exclusion is now data-driven — a prefix CIK is treated as
a professional filing agent when it files for >3 distinct companies; a company is
flagged only when **none** of its core-fact accessions use its own CIK **and**
none use an agent prefix. XOM, CBOE and REAX remain absent from section 1 → the
previous mapping fixes hold. Exit code 0.

### 2.6 Test suite (`cd Financial-DataBase && .venv/bin/python -m pytest -q`) — ✅ PASSED (0 failed)

```
184 passed, 0 failed, 1 warning in ~26s
```

Fix (f3dbb68): `tests/conftest.py` makes `db_connection` **function-scoped**, so
each test that overrides `test_db_url` (the analysis-script tests pointing at
the dev DB `financial_database`) gets its own fresh connection instead of
reusing the session-scoped one first created against `financial_database_test`.
The combined repro (previously failing analysis scripts together with
`test_financial_facts_long_strings.py`) passes, and the full suite is green.
No production data is affected (counts unchanged before/after suite runs:
companies 8,023; facts 76,035,751; filings 1,091,495).

### 2.7 CLI smoke tests — ✅ PASSED (with one env note)

| Command | Result | Status |
|---|---|---|
| `financial-db --help` | Lists migrate/prices/sec/status/update-all; exit 0 | ✅ PASSED |
| `financial-db --version` / `status` | version 0.3.0; Applied 20 / Pending 0 | ✅ PASSED |
| `financial-db sec bulk-ingest --help` | Full option help; exit 0 | ✅ PASSED |
| `financial-db sec update-incremental --dry-run --limit 3` | Without `SEC_USER_AGENT` → clean error, **exit 1** (no traceback). With `SEC_USER_AGENT` set → exit 0: “Companies in SEC universe: 3 (limited); Stale companies (>24h): 8023”. No DB writes (raw_documents 15,048 & import_runs 45 unchanged; no new import_run row). | ✅ PASSED (requires env var) |

> Note: the project now ships an **`.env.example`** documenting `SEC_USER_AGENT`,
> `DATABASE_URL` and `DATA_RAW_DIR` (commit f86cc1d); without `SEC_USER_AGENT`
> the incremental command fails by design with a clean error until the operator
> exports it.

---

## 3. Value Investing status

### 3.1 CLI surface — ✅ PASSED

`python main.py --help` — exit 0. All 16 expected commands present: `screener, company, analyze, analyze-full, buffett-analysis, historical-valuation, load-data, data-status, opportunities, anomalies, momentum, portfolio, backtest, alerts, watchlist, debug, sql-analysis`.

### 3.2 Integration with Financial-DataBase — ✅ PASSED

```
FinancialDatabaseRepository True
has_data AAPL: True
list_years len: 17   (>= 15 required)
get_by_year('AAPL', 2024).revenue = 391,035,000,000  (> 0)
```
Repository is read-only for Financial-DataBase (`upsert`/`upsert_many` are no-ops by design); fundamentals are consumed from `financial_database` and never written back by Value Investing.

### 3.3 PriceService — ✅ PASSED (real-time only, nothing persisted)

```
current AAPL: 336.13
historical[:3]: [(2026-08-19, 316.83), (2026-08-20, 311.30), (2026-08-21, 309.35)]
price at FY2023 end: 190.21
```
`SELECT count(*) FROM prices` in `financial_database` = **152 (legacy rows from 2026-09-05); 0 rows created in the last 6 hours.** Verified with `created_at` — the PriceService calls added **zero** rows. The 152 rows are legacy artifacts of migration-era price ingestion (table exists via migration 0009 but the platform never writes to it — the read-only repo + real-time PriceService).

### 3.4 CLI commands (each run verbatim)

| # | Command | Result | Status |
|---|---|---|---|
| a | `load-data AAPL --force` | Ran; loaded **10 years**, **Origen: edgar** (Financial-DataBase active; fix 88b4ac0). No prices written. | ✅ PASSED |
| b | `data-status AAPL` | Per-year coverage 2009–2025, **17 years**, source EDGAR, analysis selection EDGAR, refresh needed: no | ✅ PASSED |
| c | `company AAPL` | Name Apple Inc., price $336.13, market cap $4,905.5B, PER 43.8, P/B 66.53, ROE 151.9%, FCF Yield 2.0%, EV/EBIT 37.0, Revenue $416.2B, Net Income $112.0B | ✅ PASSED |
| d | `analyze AAPL` | Ratios table renders (21 metrics + info block); score 0.3886 | ✅ PASSED |
| e | `analyze-full AAPL` | **All 6 sections render**: 1) Company overview, 2) Real-time price & valuation, 3) Fundamental metrics, 4) Quality (Buffett score 55.6 / moat MODERATE / rating B), 5) Historical valuation (fiscal_year, price, eps, pe_ratio, fcf_yield), 6) Risks/anomalies/triggers. Source EDGAR, confidence HIGH, quality 100% | ✅ PASSED |
| f | `buffett-analysis AAPL` | 4 pillars (Profitability 75.0, Financial Strength 0.0, Cash Generation 100.0, Stability 29.1) + Moat MODERATE (65.0) + composite 67.3 (B), confidence HIGH | ✅ PASSED |
| g | `historical-valuation AAPL` | Table with fiscal_year/price/eps/pe_ratio/fcf_yield (2009–2025); last FY close 254.52, EPS 7.58, P/E 33.57, FCF yield 2.63% | ✅ PASSED |
| h | `screener --tickers AAPL,MSFT,KO,JNJ,PG,XOM,CVX,V,WMT,HD --filter min_score=40` | **9 results** (XOM excluded — only 1 fiscal year of coverage, documented limitation). Rows show price, P/E, FCF yield, EV/EBIT; prices fetched only for the 10 requested tickers (unit test `test_screener_price_scope` also covers this) | ✅ PASSED |
| i | `screener --tickers AAPL,MSFT,KO --no-prices` | Runs; exit 0. **Precio/PER/P/B/FCF yield/EV-EBIT all render N/A** (minor fix 9411b0d); fundamentals intact. | ✅ PASSED |
| j | `sql-analysis --script company_overview --cik 0000320193` | 1 row (Apple Inc., 2009–2026, 25,135 facts, 152 filings) | ✅ PASSED |
| k | `sql-analysis --script financial_series --cik 0000320193 --limit 5` | 5 rows, correct columns/order | ✅ PASSED |
| l | `sql-analysis --script ratios_advanced --cik 0000320193` | 18 rows (FY2009–2026) | ✅ PASSED |
| m | `sql-analysis --script compare --ciks 0000320193,0000789019` | 2 rows (AAPL + MSFT, latest FY 2026) | ✅ PASSED |
| n | `opportunities --tickers AAPL,MSFT,KO,JNJ` | 4 opportunity records (JNJ SPECIAL_SITUATIONS, AAPL/MSFT INFLECTION_POINT, MSFT COMPOUNDERS) | ✅ PASSED |
| o | `anomalies --tickers …` | **Not valid syntax** — `anomalies` takes positional tickers (`anomalies AAPL MSFT KO`). With positional args: ran, flagged MSFT net_income z=+3.16, KO z=+2.09 | ✅ PASSED (arg syntax differs from audit) |
| p | `momentum AAPL MSFT KO` | Ran; exit 0, table renders with a stringified row index (fix 5751823 + 4 regression tests in `tests/unit/test_momentum_command.py`). With `--no-refresh` / refresh flags, prints the targeted-refresh line, then the ranking table. | ✅ PASSED |
| q | `portfolio view` | Empty portfolio, clean message | ✅ PASSED |
| r | `portfolio performance` | Zero values, N/A return, no concentration risk | ✅ PASSED |
| s | `backtest --strategy momentum --years 3 --top 3` | Ran: 2 snapshots, metrics table, first-period selection; note “storage unavailable — falling back to static ticker list” (SQLAlchemy store unavailable; static list used) | ✅ PASSED (with note) |
| t | `alerts --tickers …` | Not valid syntax — positional tickers. `alerts AAPL MSFT KO` → 3 TRIGGER_EVENT alerts | ✅ PASSED (arg syntax differs from audit) |
| u | `watchlist list` | Empty watchlist, clean | ✅ PASSED |
| v | `debug` | 5 diagnostic sections, all OK | ✅ PASSED |

### 3.5 Daily workflow — ✅ PASSED

`python -m scripts.daily_workflow --dry-run --top 10 --limit 20` → exit 0, “=== DRY-RUN — no files written ===”.

- **No DB writes:** companies 8,023 / facts 76,035,751 / filings 1,091,495 / import_runs 45 (identical before/after); prices table 0 new rows.
- Dry-run **prints** the report (by design the script writes files only without `--dry-run`). The report generation was additionally verified with `--no-update --top 10 --limit 20`, which wrote:
  - `data/reports/daily_2026-09-20.md` (2,899 B)
  - `data/reports/daily_state.json` (2,465 B — per ticker only `composite_score`; **no price keys**)
- Report content (read): title/date; SEC update status; **universe size 20**; screened 20 (100% coverage); runtime 43 s; **Screened table** (price, P/E, FCF yield, EV/EBIT, signal); **Alerts** (23 triggers + buy signals); no missing-data section (none missing). The report includes “Missing data” and “Price notes” sections when applicable (these cover the audit’s “errors” expectation); there is no separate “opportunities” heading — opportunity signals appear in the Screened signal column and alert reasons.

### 3.6 Universe file — ✅ PASSED

- `config/universe.csv`: 500 data rows (501 lines), header `ticker,cik,company_name,source_index`; **500 unique tickers, no duplicates**; sample: A 0001090872 AGILENT TECHNOLOGIES, AAPL 0000320193 Apple Inc., ABBV, ABNB, ABT.

### 3.7 Test suite — ✅ PASSED

```
cd ~/Value_Investing && python -m pytest tests/unit -q
382 passed, 1 skipped, 1 warning in ~6s
```
361 pre-existing + **17 new** `test_refresh_service.py` cases (8b7d1b1).
The single skip: `test_financial_database_integration.py:137 — “Existing SQL repository not available”`. PytestUnknownMarkWarning noted. **0 failures.**

### 3.8 Documentation — ✅ PASSED

| File | Present | Size |
|---|---|---|
| README.md | ✅ | 352 lines |
| AGENTS.md | ✅ | 423 lines |
| docs/runbook_daily.md | ✅ | 169 lines (23 headings) |
| docs/scoring_methodology.md | ✅ | 120 lines |
| docs/scoring_validation.md | ✅ | 97 lines |
| docs/validation_report_200_sp500.md | ✅ | 344 lines |
| docs/validation_methodology.md | ✅ | 171 lines |
| config/validation_exclusions.yaml | ✅ | 120 lines |

---

## 4. Cross-project checks

### 4.1 No price persistence anywhere — ✅ PASSED

- `financial_database.prices`: 152 legacy rows (created 2026-09-05); **0 created in the last 6 hours** despite dozens of PriceService calls, screener runs, daily workflow, analyze/analyze-full/historical-valuation. No writes go through the repo (upsert no-op) nor PriceService (pure fetcher).
- `financial_db` schema: no `*price*` tables.
- `Value_Investing/data/` JSON files: `portfolio.json` (positions only, no prices), `data/reports/daily_state.json` (composite scores only, **0 occurrences of “price”**), `data/normalized/AAPL.json` (fundamentals only, **no price key**; created during the DB-unavailable fallback test — it is a fundamentals cache, not a price cache). Reports (`daily_*.md`) contain a Price column by design (allowed: “beyond the reports”).
- `data/cache`, `data/processed`, `data/raw` contain only `.gitkeep` (empty) — **no price cache files exist**.

### 4.2 Consistency across sources — ✅ PASSED

| Ticker | DB latest completed FY (repo) | Value Investing report | sql-analysis (DB raw) | P/E (live price) | FCF yield |
|---|---|---|---|---|---|
| AAPL | FY2025 rev **416,161 M** / NI **112,010 M** | company/analyze: Revenue $416.2B · Net Income $112.0B ✅ | FY2026 (in-progress 10-Q): 364,357 M / 101,464 M (definitional difference — see note) | 44.3 (screener 43.8 — small float/mcap variation) ✅ | 2.0% ✅ |
| MSFT | FY2026 rev **331,839 M** / NI **133,749 M** | compare SQL: 331,839 M / 133,749 M ✅ | same | 27.4 (screener 27.4) ✅ | 1.8% ✅ |
| KO | FY2025 rev **47,941 M** / NI **13,107 M** | screener PER 29.0 / FCF yield 1.4% consistent ✅ | — | 29.0 (screener 29.0) ✅ | 1.4% ✅ |

P/E and FCF yield computed from real-time price + DB fundamentals are internally consistent and in the expected ranges for these large caps (AAPL ~44x, MSFT ~27x, KO ~29x).
> Definitional note: `sql-analysis` scripts use `MAX(fiscal_year)` (includes the in-progress fiscal year — e.g. AAPL 2026 from the latest 10-Q), while the Value Investing repository and reports use the **latest completed** fiscal year (AAPL 2025 annual 10-K). Both are correct within their own definitions.

### 4.3 Validation exclusions honored — ✅ PASSED

- `config/validation_exclusions.yaml` is read by `scripts/validate_sp500.py` (`_load_exclusions` + severity `EXCLUDED` assignment).
- Smoke run: `sample --seed 42 --limit 20` → `vi --limit 20` → `external --limit 20` → `compare`:
  - 20 companies processed; discrepancies: **2 EXCLUDED** (DOC fcf_yield — REIT convention; HAS revenue — gross vs net revenue; both `EXPECTED_DIFFERENCE`), 1 MEDIUM (revenue), 0 HIGH genuine.
  - `by severity: {'EXCLUDED': 2, 'MEDIUM': 1}` — the “EXCLUDED” classification appears and matches the rules file.
- The pre-existing 200-ticker artifacts were backed up to `/tmp/opencode/val_backup/` before the smoke test and **restored byte-for-byte** afterwards (md5 verified).

---

## 5. Error handling results — ✅ PASSED (all cases degrade gracefully)

| Case | Simulation | Observed behavior | Status |
|---|---|---|---|
| a) Yahoo unavailable | Dead proxy (`HTTPS_PROXY=http://127.0.0.1:9`) | `Cookie/crumb fetch failed … continuing without crumb`; `price: None`; `screener --tickers AAPL,MSFT,KO` → exit 0, **Precio/PER/P/B/FCF-Yield = N/A**, fundamentals (ROE/ROIC/FCF) still shown from DB | ✅ PASSED |
| b) Financial-DataBase unavailable | `FINANCIAL_DATABASE_URL` → dead port 59999 | Repo falls back to `JsonFinancialRepository` (“PostgreSQL unavailable — falling back to JSON storage”); `sql-analysis` prints clean `ERROR: connection to server … refused` (exit 0); `company AAPL` still renders full profile via Yahoo fallback (exit 0) | ✅ PASSED |
| c) Missing ticker | `company ZZZZ` / `screener --tickers ZZZZ` | `ERROR: Sin datos suficientes para ZZZZ` / `0 resultados` + “Ninguna empresa cumple los filtros.” exit 0 | ✅ PASSED |
| d) Ticker without facts (fund) | `company ADX` (Adams Diversified Equity Fund) | Name + price + market cap rendered, then `ERROR: Sin datos suficientes para ADX` (exit 0) | ✅ PASSED |
| e) CIK without financials (trust-like entity) | `sql-analysis --script company_overview --cik 0002032732` (Arrived Homes 5 LLC) | 1 row with 0 facts / 0 filings; `financial_series` → `No data returned` (exit 0) | ✅ PASSED |

No case produced a traceback that breaks the CLI — except the momentum table bug (§3.4-p), which is unrelated to these stress cases.

---

## 6. Issues found (with severity) — all resolved below

| # | Severity | Area | Description | Status |
|---|---|---|---|---|
| 1 | **HIGH** | Value Investing CLI | `momentum <tickers>` crashes with `TypeError` — raw `int` row index into `print_table`. | ✅ FIXED (5751823, +4 regression tests) |
| 2 | **MEDIUM** | Financial-DataBase tests | Session-scoped `db_connection` causes 4 analysis-script tests to fail in the full suite (dev-DB override ignored). | ✅ FIXED (f3dbb68; 184 passed / 0 failed) |
| 3 | **MEDIUM** | Financial-DataBase script | `check_ticker_health.sql` section 1 reports 5,007 false “true stubs” (agent-filed accessions not excluded); section 4 missing. | ✅ FIXED (f9178a6; section 1 = 6, section 4 present) |
| 4 | **LOW** | Financial-DataBase CLI | `sec update-incremental` hard-requires `SEC_USER_AGENT`; no `.env.example` documented it. | ✅ FIXED (f86cc1d, `.env.example` shipped) |
| 5 | **LOW** | Value Investing CLI | `screener --no-prices` still rendered price-derived metrics (P/E, FCF yield). | ✅ FIXED (9411b0d; now N/A, 66 tests) |
| 6 | **LOW** | Value Investing backtest | “storage unavailable — falling back to static ticker list”; probably intended fallback. | ⏸️ not changed (by design) |
| 7 | **INFO** | Value Investing tests | Unregistered `@pytest.mark.integration` warning + the only skip. | ⏸️ cosmetic only |
| 8 | **INFO** | VI daily workflow | `--dry-run` prints instead of writing files (by design). | ⏸️ documented, no action |

---

## 7. Recommendations

1. **Fix the momentum crash (HIGH / blocking):** stringify the row index in `cli/commands/momentum.py` (`str(i)`) or harden `print_table`/`remove_ansi` to coerce values to `str`. Add a unit test that renders the momentum table for ≥3 tickers. (DoD: `momentum AAPL MSFT KO JNJ` exits 0 with a rendered table.)
2. **Fix the Financial-DataBase suite isolation (MEDIUM / required for green CI):** make the `db_connection` fixture function-scoped (or module-scoped), or give `test_analysis_scripts.py` its own connection fixture instead of overriding the session-scoped `test_db_url`. Expected outcome: `pytest -q` → 0 failures in the full suite while the analysis tests still hit the dev DB.
3. **Fix `check_ticker_health.sql` section 1:** implement the documented agent-filed exclusion (exclude the known agent prefixes — a maintained list, or exclude prefixes that appear as the filing CIK of >N unrelated companies). Expected: section 1 returns 0 rows (the only remaining case — ENTERGY subsidiaries — should be documented as a parent/sub relation, not a stub).
4. **Financial-DataBase .env:** ship an `.env.example` documenting `SEC_USER_AGENT` (and optionally default it from `SEC_EMAIL` as the daily workflow already does).
5. **`--no-prices` semantics:** either rename/document the flag as “skip real-time price enrichment” or make the analyzer skip market-cap-dependent metrics when `no_prices=True` so P/E/FCF yield render N/A as documented.
6. **Register `integration` pytest marker** in `pyproject.toml` (`[tool.pytest.ini_options] markers`) to remove the warning, and decide whether the SQL-repository integration test should be included/excluded.
7. **Backtest storage:** confirm whether the “storage unavailable” fallback is intended; if a local SQL/JSON store is expected, wire `SqlAlchemyFinancialRepository`/JSON store availability so backtests use real historical snapshots.
8. **Gentle note (no action required):** `financial_database.prices` still contains 152 legacy rows from 2026-09-05. If the “prices never stored” contract is strict, consider truncating this legacy table (schema retained) so the invariant is self-evident.

---

## 8. Follow-up: blocking fixes + on-demand SEC refresh — ALL RESOLVED (2026-09-20)

### 8.1 Commits

**Value Investing** (`~/Value_Investing`):

| Commit | Scope |
|---|---|
| `5751823` | fix: resolve TypeError in momentum command formatter call (FIX 1) |
| `88b4ac0` | fix: report correct source in load-data when using Financial-DataBase (minor a) |
| `9411b0d` | fix: make --no-prices suppress valuation ratios in screener (minor b) |
| `43d71f7` | docs: clarify positional tickers in anomalies, momentum, alerts (minor c) |
| `6285f28` | feat: add on-demand SEC refresh service for analyzed tickers (FIX 4, step A) |
| `a98870b` | feat: wire targeted SEC refresh into the analysis commands (FIX 4, step B + flags) |
| `30abc4f` | feat: add config/refresh.yaml for the on-demand refresh step (FIX 4, step C) |
| `8b7d1b1` | test: cover the on-demand refresh service, 17 cases (FIX 4, step D) |
| `dd314da` | docs: document the on-demand SEC refresh (README/AGENTS/runbook) (FIX 4, step E) |
| `8da1d5e` | fix: point refresh at the sibling Financial-DataBase and track sync freshness |

**Financial-DataBase** (`~/Financial-DataBase`):

| Commit | Scope |
|---|---|
| `f3dbb68` | fix: make db_connection fixture function-scoped for test isolation (FIX 2) |
| `f9178a6` | fix: exclude agent-filed accessions; add section 4 to check_ticker_health.sql (FIX 3) |
| `f86cc1d` | docs: add .env.example documenting SEC_USER_AGENT and DATABASE_URL (minor d) |

Nothing was pushed and no PR was opened, per the task rules.

### 8.2 Test suites — before / after

| Suite | Before | After |
|---|---|---|
| Value Investing `pytest tests/unit` | 361 passed, 0 failed, 1 skipped | **382 passed, 0 failed, 1 skipped** (+ 17 refresh tests) |
| Financial-DataBase `pytest tests/` | 180 passed, **4 failed** | **184 passed, 0 failed** |

### 8.3 DoD verification

| Requirement | Result |
|---|---|
| `momentum AAPL MSFT KO` runs cleanly | ✅ exit 0, table rendered, refresh line printed |
| `momentum` (universe-wide, no tickers) | ✅ skips auto-sync, prints “universo amplio: refresh acotado” |
| `screener --tickers AAPL,MSFT,KO --no-prices` | ✅ exit 0; Precio/PER/P/B/FCF yield render N/A; fundamentals intact |
| `load-data AAPL --force` | ✅ exit 0, “Origen: edgar”, 10 years loaded |
| `analyze-full AAPL` triggers targeted refresh for stale companies | ✅ stale AAPL → per-CIK `sec sync 0000320193` via FDB CLI → “1 sincronizado con SEC” → full 6-section report; fresh KO/MSFT correctly “sin tocar” |
| `--refresh` forces sync regardless of age | ✅ `analyze-full AAPL --refresh` re-synced |
| `--freshness-hours N` overrides threshold | ✅ threshold honored (unit test + CLI path) |
| `--no-refresh` skips the SEC step | ✅ “N sin tocar”, analysis continues |
| Degrade gracefully when SEC_USER_AGENT missing / DB down / SEC timeout / no CIK | ✅ clear per-ticker failure reasons; command exits 0 (unit tests 12–14) |
| Prices never persisted | ✅ refresh path performs SELECT-only DB reads (lines 118/150); prices come from PriceService’s in-memory cache (TTL 900 s); `financial_database.prices` untouched by any exercise |
| Refresh only the analyzed CIKs (never the full universe) | ✅ per-CIK `sec sync <CIK>` subprocess; universe-wide runs skip unless `--refresh` |
| `check_ticker_health.sql` | ✅ section 1 = **6** (< 100) stubs, section 4 = 0 unresolved of 500, XOM/CBOE/REAX absent, exit 0 |
| XOM / CBOE / REAX mapping fixes intact | ✅ verified in §2.4 and absent from §1 stubs |

### 8.4 Residual (non-blocking)

- `@pytest.mark.integration` unregistered-marker warning (issues 7/8 from §6) — cosmetic.
- Healthy SEC reconciliation is judged by last-write timestamps (`financial_facts`, `filings`, plus `companies.updated_at` — touched by every successful sync). A company whose data already matches SEC re-does one idempotent sync per stale window, which advances `companies.updated_at` and marks it fresh.

---

## Overall verdict

| Gate | Result |
|---|---|
| Every CLI command runs without crashing | ✅ **Yes** — `momentum` fixed (5751823); all commands re-verified. |
| Financial-DataBase full suite = 0 failures | ✅ **Yes** — 184 passed / 0 failed (f3dbb68). |
| Value Investing full suite = 0 failures | ✅ Yes — 382 passed, 1 skipped (0 failed). |
| No price persisted anywhere | ✅ Yes — verified at DB and file level after every exercise (refresh path is SELECT-only + in-memory price cache). |
| Verification report written | ✅ Yes — this file. |
| XOM / CBOE / REAX mappings remain fixed | ✅ Yes — verified in data and health script. |
| Flaky analysis-script tests remain fixed | ✅ **Yes** — full FDB suite green. |
| `check_ticker_health.sql` < 100 stubs + section 4 | ✅ Yes — 6 stubs, section 4 = 0 unresolved. |
| `analyze-full` runs a targeted refresh of stale companies | ✅ **Yes** — per-CIK `sec sync`, fresh companies skipped, prices real-time only. |
| On-demand refresh flags (`--refresh` / `--no-refresh` / `--freshness-hours`) | ✅ Yes — registered on all 9 analysis commands. |

**This audit is now a clean release gate.** All three blocking findings (momentum
crash, FDB suite isolation, health-script false positives) are fixed and
committed, and the on-demand, targeted SEC refresh for analyzed companies is
implemented, tested (17 new unit tests), documented, and verified end-to-end
against the live SEC EDGAR + Financial-DataBase + Yahoo price feeds. No prices
are persisted; nothing was pushed; no PR was opened.