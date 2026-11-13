## [0.34.2] - 2026-11-13

### Fixed
- **Batch operations no longer cascade through FMP/Tiingo.** `vi rank
  --universe sp500` (and the screener/consensus prefetch) used one price
  request per ticker; with free tiers (FMP 250/day, Tiingo 50/hour) that
  could never finish and produced hundreds of 429/403 lines. Batch paths now
  use Yahoo's bulk downloader (`yf.download`, one request per 100-ticker
  chunk) and only fall back per ticker for names the batch answered without
  a price.
- **FMP quote uses the stable API.** `stable/quote` replaces the deprecated
  `api/v3/quote` (403 on free accounts); `historical-price-eod/dividend-
  adjusted` was already stable.
- **Circuit breaker.** After 3 consecutive 429/403 responses a provider is
  disabled for 60 s and skipped by the fallback chain. It logs one warning
  per outage instead of one per ticker; 500/timeouts do not trip it.
- **Graceful batch degradation.** If Yahoo's bulk request fails (429/401),
  the rank does not launch 500 per-ticker `.info` calls for market caps and
  betas: they degrade to `None` and the run still completes.

### Added
- `PriceService.get_batch_prices()`: cached bulk current prices for many
  tickers (Yahoo batch, chunks of 100).
- `CircuitBreaker` in `backend/services/price_providers` with injectable
  clock, rate-limit-only counting and a single log line per outage.
- Tests for bulk parsing, cache reuse, batch failure without cascade, partial
  fallback, the circuit breaker and the FMP stable quote.

### Documentation
- `docs/price_providers.md`: rate-limit table, batch-vs-single rule and
  circuit-breaker behavior.

### Measured
- `vi rank --by buffett_clark --top 20 --universe sp500` under a Yahoo 429:
  **143 s and rc=0**, with **0 provider error lines** (only delisted-ticker
  warnings). Before the fix it did not finish (killed at 219 s with hundreds
  of fallback requests). The <30 s target needs a healthy Yahoo; that was not
  reproducible while testing because the IP was rate-limited.

### Notes
- `PRICE_PROVIDER` semantics are unchanged: single-ticker commands still use
  the configured order (Tiingo → FMP → Yahoo in the local `.env`).
- Free tiers are not batch-safe; a paid FMP/Tiingo plan is required for bulk
  use. Yahoo bulk remains the default for batches.

## [0.34.0] - 2026-11-13

### Added
- **Research-grade backtest** (`vi backtest --research-grade`, requires
  Financial-DataBase 0.4.0+): point-in-time fundamentals, historical S&P 500
  membership, transaction costs, rebalancing, per-name sizing cap and
  replayable price snapshots. `--legacy` keeps the pre-0.34.0 PoC behavior.
  - Fundamentals: `financial_facts.filing_date <= as_of` and
    `period_end <= as_of`; restatements filed later are invisible.
  - Universe: `sp500_constituents` half-open intervals at the entry date.
  - Costs: `--tc-bps` (default 10) and `--tc-fixed` (default 0).
  - Rebalancing: `--rebalance annual|quarterly|threshold` (default annual).
  - Sizing: `--sizing tier|equal` plus `--max-weight` (default 20%). With
    fewer than five names the unfilled remainder stays in cash.
  - Reproducibility: `--save-snapshot` / `--price-snapshot` store and replay
    every `(ticker, date, price)` used by the run.
- `PitMixin` in the FDB repository: `list_years_pit`,
  `get_core_financials_pit`, `get_sp500_universe`.
- FDB 0.4.0 requirement: `sp500_constituents` (1,262 intervals / 1,209
  tickers), `companies.delisted_at` and the PIT index.

### Changed
- `analyze-*` commands are marked `[deprecated]` in `--help`; use
  `vi scorecard <ticker>`.
- Backtest output reports PIT coverage, survivorship status, sizing,
  rebalancing, turnover and cost drag when `--research-grade` is active.
- `docs/backlog.md` consolidated; `LEARNINGS.md` moved to `docs/learnings.md`.

### Fixed
- Removed 401 legacy (pre-SHA-256) price-cache files from local caches; the
  hashed cache is the only format the service reads.
- Mobile: zod 4.6.7 and glob 14.0.6 patched via npm overrides; a `Mobile
  (audit, lint, test)` job now runs in CI.

### Documentation
- `docs/backtesting_design.md`: research-grade mode, PIT SQL, costs,
  rebalancing, snapshots and what remains unsolved (delisted prices,
  market impact, intra-year index events).
- `docs/sprint_v034_decisions.md`: Q1–Q8 answers and the FDB diagnostics.

### Measured
Research-grade, 2015–2024, `--limit 400` per year (historical membership),
10 bps costs, 20% cap, annual rebalancing:

| Methodology | PoC CAGR | Research CAGR | PoC Sharpe | Research Sharpe |
|---|---:|---:|---:|---:|
| `buffett_classic` | 22.14% | **17.08%** | 1.489 | **1.299** |
| `graham` | 9.85% | **4.41%** | 0.366 | **0.482** |

- PIT coverage: 3,332 / 4,000 member-years (83.3%); 529 distinct Buffett
  tickers evaluated.
- Buffett: opportunity set 14.04%, SPY 15.73%, 64 signals (57 STRONG + 7 BUY).
- Graham: 10 signals across 6 invested years; most of the book stays in cash.
- Transaction costs alone are ~0.08%/year, so the PoC→research delta comes
  mainly from the PIT lag (entry in February), the historical membership and
  the 20% cap, not from costs.

### Notes
- Survivorship bias is **not** corrected: Yahoo no longer serves delisted
  symbols, so removed constituents without a live price are skipped and the
  run says so (`config.survivorship_bias: true`).
- The fja05680 membership snapshot ends 2026-08-18; current-composition
  overlap with Wikipedia is 496/503. Backtests ending in 2024 are unaffected.
- The legacy PoC remains the default so previously published numbers stay
  comparable; cite only `--research-grade` results.

## [0.33.0] - 2026-11-12

### Changed
- **VI consumes FDB 0.3.0 `*_usd` columns**: the scorecard, ranking, DCF and
  backtest monetary fields now come from `revenue_usd`, `net_income_usd`,
  `operating_income_usd`, `gross_profit_usd`, `total_assets_usd`,
  `total_liabilities_usd`, `stockholders_equity_usd` and `cash_usd`, converted
  at the fiscal-year-end FX rate. Previously VI read the original-currency
  values, corrupting P/E, P/B and FCF yield for non-USD filers (SAN EUR,
  BTI GBP).
- **`[MIXED-CURRENCY]` badge**: tickers whose filing currency is not USD show
  an orange badge in the CLI (scorecard/rank/backtest) and a chip in the UI;
  the scorecard adds a caption. `currency = NULL` means "assumed USD" and
  never triggers the badge. The backtest summary also reports how many
  signals belong to mixed-currency filers.
- `list_years` converts non-USD rows to their `*_usd` values; US rows keep the
  raw normalized USD history so the long-run backtest stays comparable with
  pre-v0.33 runs. `get_best_available` (scorecard/ranking/DCF) overlays the
  core USD fields for every ticker.

### Measured
- SAN FY2024: net income **€13.744B → $14.279B** (1.0389 USD/EUR at
  2024-12-31); total assets €1.837T → $1.909T.
- BTI FY2024: net income **£3.181B → $3.986B** (1.2529 USD/GBP).
- TTE, AZN, SHEL, AAPL: USD, `*_usd` identical to the original values.
- Backtest Buffett classic 10y/400: **22.14% CAGR / 1.49 Sharpe** (v0.32.1
  audit: 23.76% / 1.53). The 400-ticker sample contains **0 mixed-currency
  filers**, so the difference is price/data drift, not the USD conversion.
- Backtest Graham 5y/400: **4.24% / 0.50** (was 4.2% / 0.50).

### Notes
- **Breaking dependency: FDB 0.3.0+ required.** VI 0.33 with FDB 0.2.x will
  fail because `core_financials.*_usd` does not exist.
- 10,521 `core_financials` rows have a non-USD currency (1,919,437 facts).
- A non-USD row with no FX rate is cleared to `None`, never mixed with the
  original value.
- `balance_effective` is not read by VI anymore; the repository derives the
  USD liabilities from `core_financials` directly.

## [0.32.1] - 2026-11-11

### Security
- **Path injection in the price cache**: `PriceService` built cache
  filenames from the raw, user-controlled ticker. A crafted ticker such as
  `../../etc/passwd` could escape `data/price_cache/`. The cache key is now a
  SHA-256 digest of the normalized ticker, so the tainted string never
  reaches a filesystem path. CodeQL `py/path-injection` alerts: **4 high → 0
  open**. Tests cover traversal payloads, determinism, per-ticker separation
  and the empty-ticker case.

### Documentation
- `docs/backtesting_design.md`: added the 2026-11-11 audit (12 Q&A on price
  sourcing, adjusted close, ADR currency, fiscal-year-end fallback, failure
  behaviour, holdings, rebalancing and the opportunity set), and corrected
  the portfolio formula to tier-weighted.
- `docs/methodology_expansion_summary.md`: corrected the backtest table.
  `buffett_clark` and `marks` were reported at 2021–2024 / 100 tickers;
  the comparable 10y/400 numbers are **15.93% / 1.07** and **15.15% /
  1.39** (not -2.6% / 23.4%).
- `docs/security_review_2026-11-11.md`: CodeQL/Dependabot status.

### Notes
- **v0.32.0 does NOT include the security fix. Use v0.32.1 or later.**
- **ADR currency bug**: SAN reports in EUR and BTI in GBP, while their NYSE
  ADR prices are USD; VI's normalized `currency` is hardcoded to USD, so
  their valuation ratios mix currencies. This is documented (not fixed here);
  the FDB 0.3.0 currency normalization is a separate session.
- Mobile Dependabot alerts (`zod`, `glob`, `deepmerge`) remain in
  `mobile/package-lock.json`; they are transitive build/dev tooling, not the
  Python backend or the app bundle. Follow-up in a dedicated mobile upgrade
  session.

## [0.32.0] - 2026-11-11

### Added
- **`marks` deep expansion (4 → 17 rules)**: 13 checks across valuation,
  quality, risk control and company-level cycle position. The net-debt/EBITDA
  > 4× survival override still forces AVOID after the weighted verdict.
- **`greenblatt` weighted overlay (3 → 15 rules)**: the Magic Formula ranking
  remains the primary input; the old percentile cut is replaced by a
  transparent overlay (top 50/100 ranking, ROC/EY decomposition, quality).
- `docs/methodology_expansion_summary.md`: consolidated view of all eight
  methodologies, book availability, distributions, backtests and deferred
  rules.
- `docs/marks_rules.md`, `docs/greenblatt_rules.md`.

### Measured (SP500, one-pass base verdicts, 2026-11-11)
| Methodology | BUY | WATCH | HOLD | AVOID | N/A | INSUFFICIENT |
|---|---:|---:|---:|---:|---:|---:|
| `graham` | 0 | 3 | 95 | 310 | 71 | 21 |
| `graham_dodd` | 0 | 0 | 22 | 363 | 71 | 44 |
| `buffett_classic` | 9 | 62 | 178 | 152 | 71 | 28 |
| `buffett_clark` | 4 | 48 | 109 | 173 | 71 | 95 |
| `fisher_quantitative_subset` | 12 | 77 | 142 | 160 | 71 | 38 |
| `lynch_garp` | 1 | 21 | 107 | 264 | 71 | 36 |
| `marks` | 3 | 54 | 185 | 170 | 71 | 17 |
| `greenblatt` | 3 | 4 | 187 | 63 | 99 | 144 |

### Backtests (PoC, 2021–2024, 100-ticker sample)
| Methodology | CAGR | Sharpe | Opportunity set |
|---|---:|---:|---:|
| `buffett_clark` | -2.6% | -0.58 | 8.7% |
| `lynch_garp` | 0.9% | 0.20 | 8.7% |
| `graham_dodd` | 0.0% (all cash) | — | 8.7% |
| `fisher_quantitative_subset` | 16.1% | 0.78 | 8.7% |
| `marks` | 23.4% | 0.89 | 8.7% |
| `greenblatt` | — | — | excluded (look-ahead) |

The long-run baselines remain Graham 4.2% CAGR / 0.50 Sharpe (5y/400, v0.26.0)
and Buffett classic 23.8% CAGR / 1.53 Sharpe (10y/400, v0.27.1).

### Tests
- **2948 unit tests passed / 2 skipped** (2819 at v0.29.0; +129), 125 API
  tests, ruff 0/0, theme 26/4.
- 121 new rule tests across the six expanded methodologies; the existing
  methodology tests were adapted to the weighted semantics.

### Notes
- Four releases complete the programme: v0.29.0 (books + Graham/Buffett
  alignment), v0.30.0 (buffett_clark + lynch), v0.31.0 (graham_dodd +
  fisher), v0.32.0 (marks + greenblatt).
- Book availability: *The Intelligent Investor*, *Security Analysis*,
  *Common Stocks and Uncommon Profits* and the Buffett/Clark financial-
  statements book were available and cited by page where the notes support
  it. *The Warren Buffett Way*, *One Up on Wall Street*/*Beating the Street*,
  *The Most Important Thing* and *The Little Book That Beats the Market*
  were not found; their rules are explicit public-knowledge approximations.
- Deferred rules and the specialized bank/REIT analyzers are tracked in
  `docs/methodology_expansion_summary.md` and `docs/backlog.md`.

## [0.31.0] - 2026-11-11

### Added
- **`graham_dodd` deep expansion (5 → 26 rules)**: 21 checks from *Security
  Analysis* (1934) across net-net/NCAV, balance-sheet quality, earnings
  power (including EPV), asset value and margin of safety. Weight 0 for the
  report-only qualitative rule; pages 5, 38/41, 101 and 230 are cited where
  the curated notes support them.
- **`fisher_quantitative_subset` deep expansion (4 → 17 rules)**: 13 new
  checks across growth potential, profitability, cost efficiency and capital
  discipline. The 11 qualitative/scuttlebutt points stay deferred and are
  documented in `docs/fisher_rules.md`.
- `docs/graham_dodd_rules.md` and `docs/fisher_rules.md` with full rule
  tables, weights, sources and distributions.

### Measured (SP500, one-pass base verdicts)
- `graham_dodd`: **0 BUY / 0 WATCH / 22 HOLD / 363 AVOID / 71 N/A /
  44 INSUFFICIENT**. The strictness is deliberate; the book's net-net and
  2/3 NCAV tests rarely trigger on modern large caps.
- `fisher_quantitative_subset`: **12 BUY / 77 WATCH / 142 HOLD / 160 AVOID /
  71 N/A / 38 INSUFFICIENT**.

### Notes
- *Security Analysis* was available and is cited by page where supported;
  Fisher's *Common Stocks and Uncommon Profits* was available and cited.
- The Fisher framework remains a quantitative subset by design.
- Backtests are consolidated in v0.32.0.

## [0.30.0] - 2026-11-11

### Added
- **`buffett_clark` deep expansion (7 → 23 rules)**: 16 new checks from
  *Warren Buffett and the Interpretation of Financial Statements* (2001)
  across durable advantage, owner earnings, valuation and growth. Critical
  rules (×2): ROIC current/5y and the DCF margin of safety. The seven
  original statement-signature rules are kept and weighted.
- **`lynch_garp` deep expansion (5 → 24 rules)**: 19 new checks across core
  GARP, financial health, valuation and the six Lynch categories. The
  category-specific block only enters the score for the ticker's own
  category; the slow-grower/stalwart/fast-grower/cyclical/turnaround/
  asset-play classifier is unchanged.
- `docs/buffett_clark_rules.md` and `docs/lynch_garp_rules.md` with the full
  rule tables, weights, sources and measured distributions.

### Measured (SP500, one-pass base verdicts)
- `buffett_clark`: **4 BUY / 48 WATCH / 109 HOLD / 173 AVOID / 71 N/A /
  95 INSUFFICIENT**. The high INSUFFICIENT count is data coverage (capex,
  D&A and 10-year history), not an applicability guard.
- `lynch_garp`: **1 BUY / 21 WATCH / 107 HOLD / 264 AVOID / 71 N/A /
  36 INSUFFICIENT**.

### Notes
- The Buffett/Clark book was available and is cited by page where the notes
  support it. *One Up on Wall Street* / *Beating the Street* were not
  available; every Lynch rule is explicitly a public-knowledge
  reconstruction.
- Test count grows by 45 rule tests plus the adapted methodology tests.
- Backtests for the two new frameworks are part of the final consolidation
  (v0.32.0).

## [0.29.0] - 2026-11-11

### Added
- **`docs/books_notes/`**: curated notes and a book-to-methodology map for
  the reference library. Four books were available and extracted: *The
  Intelligent Investor* (Graham), *Security Analysis* (Graham & Dodd),
  *Common Stocks and Uncommon Profits* (Fisher) and *Warren Buffett and the
  Interpretation of Financial Statements* (Buffett/Clark). The full text
  lives in the gitignored `_raw/`; only the notes are versioned.
- Four methodologies whose books were **not found** (*The Warren Buffett
  Way*, *One Up on Wall Street*, *The Most Important Thing*, *The Little
  Book That Beats the Market*) have explicit "public knowledge only" stubs,
  so no citation is invented.

### Changed
- **Graham aligned with *The Intelligent Investor*** (ch. 14, p. 112): the
  debt criterion now follows the book's utility branch (utilities may carry
  up to 2× book equity; industrials keep total debt ≤ working capital).
  Total debt remains a stricter proxy for long-term debt.
- Graham source audit: interest coverage (5×) and the EPS-dispersion test
  are now labelled public-knowledge extensions rather than book criteria;
  the NCAV/net-net rule now cites *Security Analysis* (p. 5) instead of
  *The Intelligent Investor*.
- **Buffett classic source audit**: five rules that claimed a specific
  letter were re-labelled as public approximations (ROIC persistence,
  interest coverage, five-year FCF, net margin, earnings yield). Thresholds,
  weights and the measured distribution are unchanged.

### Measured
- Graham distribution (one-pass SP500, base verdicts): **0 BUY / 3 WATCH /
  95 HOLD / 310 AVOID / 71 N/A / 21 INSUFFICIENT** — unchanged; no utility
  crossed a verdict boundary.
- Buffett classic base distribution: **9 BUY / 62 WATCH / 178 HOLD /
  152 AVOID / 71 N/A / 28 INSUFFICIENT** (the tiered rank splits the BUYs
  into STRONG/BUY).
- Backtests are unchanged by the documentation-only Buffett audit; Graham's
  last measured 5-year run was 4.2% CAGR / 0.50 Sharpe (v0.26.0), and the
  utility branch is exercised in the final consolidation.

### Notes
- This release is the first of four checkpoints; the six remaining
  methodologies are expanded in v0.30.0–v0.32.0.
- Book pages are cited only where the notes support them; everything else is
  explicitly a public-knowledge approximation.

## [0.28.0] - 2026-11-11

### Added
- **Guided interactive menu**: every option in `vi` (no arguments) now asks
  for its inputs with numbered selectors, numeric fields with visible
  defaults and y/n questions, instead of asking for raw CLI flags. No flag
  knowledge is required.
  - **Backtest**: methodology list (greenblatt excluded because the PoC
    cannot backtest it), years (`[5]`), limit (`[400]`) and equal-weight
    (`y/N`).
  - **Rank**: methodology list (or `[c] Combine`), top N (`[20]`) and
    universe (demo / indices / all). Combine asks for 2+ methodologies and
    the AND/OR/weighted strategy.
  - **Screener**: optional methodology+verdict filter, universe and top N.
  - **Analysis**: ticker validation for scorecard (optional JSON), balance
    (years), methodologies, DCF, compare and full report (space-separated
    tickers, optional live prices).
  - **Data**: refresh (facts/prices/both), data status, load (years, force),
    filings (limit) and financial alerts.
  - Portfolio view/performance need no prompts.
- **`[x] Advanced`** on the home screen: type a raw command
  (`backtest --methodology graham --years 10`) for cases outside the guided
  flows.
- **Ticker validation**: `ask_ticker()` checks Financial-DataBase and
  re-prompts on an unknown ticker; a database outage degrades gracefully
  instead of blocking the menu.
- **Clean cancellation**: `q` / `back` at any prompt (or `Ctrl+C` / EOF)
  raises `PromptCancelled`; the menu returns to the previous screen without
  executing anything.
- **Synthwave prompts** (`cli/menu_prompts.py`): cyan bold titles, gold
  numbers, dim visible defaults and pink validation errors, sharing the main
  menu's `--no-color` / `NO_COLOR` handling.

### Changed
- The `Methodology and flags [...]` text prompt is gone. Direct commands
  (`vi backtest --methodology graham --years 10`) are unchanged; the guided
  menu is an alternative layer, not a replacement.
- `vi interactive --help` and the command catalogue describe the guided
  flows and the advanced mode.

### Tests
- 59 new tests: 28 for the prompt helpers (selectors, defaults, ranges,
  validators, cancellation, colour on/off) and 31 end-to-end menu flows
  (one per option plus cancellation, advanced mode and the no-flags
  guarantee). Test count: **2759 → 2818**.

## [0.27.1] - 2026-11-10

### Fixed
- **Batch DCF**: the batch price adapters now expose `get_beta`, so the DCF
  margin-of-safety rule is evaluated in rank, screener, compare and backtest
  instead of silently degrading to `N/A`. Previously the Buffett score in
  those contexts was computed on a subset of rules (the critical DCF rule was
  missing).
- **Quote-summary cache**: `PriceService._info` caches the whole Yahoo
  `.info` dict for the TTL, so `get_market_cap()` + `get_beta()` share one
  network request per ticker instead of issuing two.
- `BatchPriceContext` (new, `backend/services/price_adapter.py`) centralizes
  the price/market-cap/beta surface for batch callers. The backtest passes
  `beta=None` on purpose (no point-in-time beta; the DCF uses its documented
  1.0 fallback, avoiding look-ahead).
- The backtest legend now says `N/A: banks/insurers` (REITs are scored and
  flagged `[REIT]`).

### Measured
- **Buffett backtest** (`buffett_classic --years 10 --limit 400`,
  2015–2024, 392 evaluated): **CAGR 23.8% / Sharpe 1.53** (before, with the
  DCF rule N/A: 13.8% / 1.09). Opportunity set 15.2%, SPY 14.7%. The
  activated rule makes the basket smaller and more valuation-driven; the
  PoC has no dividends, costs or survivorship correction.
- **Buffett rank distribution** (SP500): 8 STRONG_BUY / 0 BUY / 63 WATCH /
  177 HOLD / 153 AVOID / 71 N/A / 28 INSUFFICIENT (before: 12 / 9 / 73 /
  150 / 148 / 71 / 37). The fix changed 84 verdicts (75 downgrades) and
  moved 9 unique tickers out of INSUFFICIENT_DATA; across the backtest
  2016–2024 signal-years it removed ~142 INSUFFICIENT rows.
- REITs (28) with the DCF active: 6 HOLD / 17 AVOID / 5 INSUFFICIENT
  (was 2 / 12 / 14). Banks (71) remain N/A.
- **Graham is unchanged**: its methodology has no DCF rule, so its backtest
  stays at the v0.26.0 4.2% CAGR / 0.50 Sharpe.

### Tests
- 8 new tests: batch adapter surface, DCF rule active with a beta and with
  the 1.0 fallback, backtest context, legacy-adapter regression guard, and
  the shared `.info` cache (one request for market cap + beta).
- Test count: **2751 → 2759**.

## [0.27.0] - 2026-11-10

### Changed
- **REIT policy (product change)**: REITs are now scored by all
  methodologies and by the scorecard with the standard industrial rules,
  instead of returning `N/A` on the six dimensions (v0.23.0 behaviour). The
  user decides whether the score is meaningful; every surface shows a visible
  `[REIT]` badge, and the scorecard adds "REIT — scoring uses standard
  industrial rules; FFO considerations may apply". Banks and insurers keep
  their structural `N/A`.
- **`is_reit()` fix**: the classification is now industry-first ("REIT" in
  the industry, or a Real Estate sector without an industry). Real-estate
  services firms (CBRE, CSGP) are operating companies, not REITs, and keep a
  normal scorecard.

### Added
- **`[BANK]` badge**: banks/insurers keep the `N/A` scorecard but now carry a
  purple `[BANK]` badge plus a "specialized analysis planned" note. The badge
  is visible in the scorecard, rank, backtest JSON and the UI.
- **`MethodologyResult.flags`**: `{"reit"}`, `{"bank"}` (set centrally from
  the latest fundamentals), exposed as `overall_flags` in the scorecard JSON
  and `flags` in every methodology payload, rank row and backtest signal.
- **Buffett deep expansion**: `buffett_classic` goes from the wrapped
  4-pillar engine to **20 explicit rules** across moat, financial strength,
  earnings quality, capital allocation, valuation and management. Weighted
  scoring matches Graham v0.26.0: BUY ≥ 0.85, WATCH ≥ 0.70, HOLD ≥ 0.50,
  else AVOID; >30% missing weight returns INSUFFICIENT_DATA. Critical rules
  (×2): ROIC current + 10-year persistence, positive FCF (5y), net margin
  ≥ 10%, no dilution (5y) and DCF margin of safety ≥ 20%. Insider ownership
  and R&D intensity are informational (weight 0).
- New Buffett rules: gross-margin stability, operating-margin trend, pricing
  power, interest coverage ≥ 10×, current ratio ≥ 1.5, FCF conversion ≥ 80%,
  5-year EPS consistency, owner earnings (NI + D&A − capex proxy), buybacks
  in 3 of 5 years, earnings yield ≥ 5%, P/E ≤ 20 and DCF margin ≥ 20%.
- **Specialized analyzers backlog**: bank (NIM, CET1, loan book) and REIT
  (FFO/AFFO, occupancy) analyzers documented in `docs/backlog.md` for
  v0.28+; the v0.27.0 badges are their prerequisites.

### Measured
- Buffett distribution on the S&P 500 (2026-11-10): **12 STRONG_BUY /
  9 BUY / 73 WATCH / 150 HOLD / 148 AVOID / 71 N/A (banks) / 37
  INSUFFICIENT_DATA** — 21 positives (4.2%). No forced BUYs; the three
  valuation rules are what hold the market back.
- REITs (28): 2 HOLD, 12 AVOID, 14 INSUFFICIENT_DATA, 0 positive. The
  INSUFFICIENT share comes from the unclassified REIT balance sheet (the
  FFO analyzer is the v0.28+ fix), not from an N/A guard.
- AAPL WATCH 73.91 (moat/FCF/capital allocation pass; valuation fails at
  ~52× earnings). KO HOLD 58.33 (1.27× debt/equity, 8.3× coverage, 40% FCF
  conversion, ~36× earnings). Keeping KO at HOLD is the honest result of the
  no-forced-verdict policy.
- Backtest `buffett_classic --years 10 --limit 400` (2015–2024): portfolio
  **CAGR 13.8% / Sharpe 1.09** vs the v0.24.0 baseline 14.1% / 1.22;
  opportunity set 15.2%, SPY 14.7%.
- Scorecard: VICI is scored (overall Mixed, `[REIT]`), JPM stays `N/A` with
  `[BANK]`; CBRE/CSGP are no longer classified as REITs.

### Documentation
- `docs/buffett_rules.md` (new): 20-rule table, weights, sources, measured
  distribution, backtest and deferred rules.
- `docs/scoring_methodology.md`: company-type policy (REIT scored + badge,
  banks N/A + badge).
- `docs/backlog.md`: dedicated bank/REIT analyzers and the remaining six
  methodology expansions.

### Notes
- The menu is unchanged.
- Only `buffett_classic` was expanded in this release; the other six
  methodologies keep their rules.
- Test count: **2711 → 2751**.

## [0.26.0] - 2026-11-10

### Added
- **Synthwave interactive menu**: `vi` without arguments now opens an 80s
  trading-terminal menu with ANSI-256 neon colors (cyan, pink, gold), heavy
  box drawing and a compact VALUE INVESTING header. The home screen shows
  three categories (~22 lines) instead of the previous 19-route flat list:
  Analysis, Ranking & screening, and Portfolio · Data · Backtesting.
  Submenus of 5-8 options; `[1-9]` selects, `h` returns home, `s` searches,
  `?` opens the grouped help, `q` quits. `--no-color`, `NO_COLOR` and a
  non-TTY stdout fall back to ASCII borders with no ANSI. The ranking entry
  defaults to `--by graham --universe sp500 --top 20`.
- **Graham deep expansion**: from 8 criteria to **22 weighted rules** across
  six categories (Financial Strength, Earnings Quality, Valuation, Growth,
  Dividends, Margin of Safety). New checks: debt/equity, interest coverage,
  positive working capital, positive 10-year earnings, EPS stability, 3-year
  net-income growth, positive EPS, Graham Number, enterprising P/E ≤ 10
  (informational), revenue CAGR vs 3% inflation, payout ratio, no dividend
  suspension, price vs 2/3 EPV (9% fixed discount) and NCAV vs 1.5× price.
  Sources and weights are documented in `docs/graham_rules.md`.
- **Weighted Graham score**: `Σ passed weight / Σ evaluable weight` with
  thresholds BUY ≥ 0.85, WATCH ≥ 0.70, HOLD ≥ 0.50, else AVOID; >30% of the
  weighted rules missing data returns INSUFFICIENT_DATA. The base verdict
  feeds the v0.24 demote-only tiers unchanged.

### Changed
- Graham distribution on the S&P 500 (2026-11-10): **0 BUY / 3 WATCH /
  95 HOLD / 310 AVOID / 71 N/A / 21 INSUFFICIENT** (before: 0 / 2 / 54 /
  419 / 71 / 8). The three WATCH names are VICI (84.2), LEN (80.0) and SMCI
  (77.3); no company clears the 0.85 BUY line in the current market. That is
  the honest result, not a forced positive.
- Backtest (`graham --years 5 --limit 400`): one 2022 STRONG_BUY, portfolio
  CAGR 4.2% vs opportunity set 21.2% and SPY 14.3% (mostly cash). The 2021-22
  INSUFFICIENT counts are visible in the breakdown because the deep rules
  need history/EBIT/current-split data that older years do not always carry.

### Documentation
- `docs/graham_rules.md` (new): all 22 rules, weights, sources, distribution
  and deferred rules.
- `docs/backlog.md`: one-methodology-per-session plan for the remaining seven
  methodologies (buffett_classic, buffett_clark, lynch_garp, graham_dodd,
  fisher, marks, greenblatt) and the Graham rules that require a data-pipeline
  change (separate long-term debt tag, full 20-year history, dynamic-WACC EPV,
  insider/management quality, true net-net NCAV).

### Notes
- Only Graham was expanded in this release; the other seven methodologies
  keep their current rules.
- `vi analyze-graham` now prints ~22 rules with their category/weight and the
  weighted verdict; the JSON contract (`verdict`, `score`, `tier`) is
  unchanged.
- Test count: **2697 → 2711**.

## [0.25.0] - 2026-11-10

### Added
- **Categorized interactive menu**: `vi` without arguments now groups its
  19 routes by area (Analysis, Ranking & screening, Portfolio, Data &
  refresh, Backtesting) and adds a Help section. `?` prints the grouped
  command catalog, `s` searches it and `q` quits. The ranking entry
  defaults to `--by graham --universe sp500 --top 20`; scorecard, balance,
  DCF, compare, consensus ranking, data status, load-data and backtest are
  reachable from the menu.
- **`vi help <command>`**: alias of `vi <command> --help`.
- **`vi help --search <query>`**: search over command names, keywords and
  descriptions, top 5 with an example (e.g. `vi help --search methodology`
  returns methodologies, compare-methodologies, rank, backtest, screener).
- **Unknown-command suggestions**: `vi top` -> "Did you mean 'vi rank'?";
  intent aliases also cover balance/valuation/scores/menu.
- **Common tasks table** in `docs/cli_reference.md`: "What do you want to
  do?" -> command (top 20 by methodology, balance, scorecard, compare,
  refresh, backtest, consensus, screener by verdict, portfolio, data status,
  filings). Both READMEs link to the reference and mention the search.
- **Price retry and disk cache**: yfinance calls are paced
  (`MIN_REQUEST_INTERVAL=1s`), retried up to 3 times with exponential
  backoff + jitter (no retry for 401), and historical prices are cached in
  the gitignored `data/price_cache/`. Recent ranges expire after one day.

### Changed
- `vi --help` now ends with a Common tasks block and the categorized command
  list instead of only the alphabetical subparser dump.
- `vi rank` without `--by`/`--combine` prints the canonical example
  (`vi rank --by graham --top 20`) instead of a bare argparse error; its
  `--help` includes executable examples.
- The `.info` snapshot path keeps its own 3-attempt/abort policy, so a 429
  during a large stage still aborts the stage instead of retrying every
  ticker.

### Fixed
- `vi refresh` reports `Yahoo rate-limited (429). Retry later or cache.`
  when the retries are exhausted, instead of the generic "price
  unavailable".
- yfinance's "Crumb fetch rate-limited (HTTP 429)" warning is hidden from
  normal output (`PRICE_YF_VERBOSE=1` restores it).

### Measured
- Repeated `vi backtest --methodology graham --years 5`: 38 s first run
  (fills the cache) -> 7-8 s second run (<20%).
- Test count: **2678 → 2697**.

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
