# CLI reference

`vi` is the terminal interface to Value Investing: 43 commands across
analysis, ranking, portfolio and data management. Every command is documented
here from its real `--help`; the README keeps a short quick-start list.

## Quick start

```bash
./vi scorecard AAPL      # First command: six-dimension scorecard
./vi --help              # List all 43 commands
./vi                     # Interactive menu (no arguments)
```

Installation and database setup: see [README](../README.md#install).
Prices are fetched on demand from Yahoo and are never persisted to FDB.

## Common tasks — "What do you want to do?"

| I want to... | Command |
|---|---|
| See the top 20 by methodology | `vi rank --by graham --top 20` |
| Combine Graham + Lynch (AND) | `vi rank --combine graham,lynch_garp --strategy and --universe sp500 --top 20` |
| Analyze one company | `vi scorecard AAPL` |
| See the balance sheet (T-view) | `vi financials AAPL` |
| Compare the eight methodologies | `vi compare-methodologies AAPL` |
| Inspect one methodology's rules | `vi methodologies show graham` |
| Value a company with a DCF | `vi dcf AAPL` |
| Refresh facts + price for one ticker | `vi refresh AAPL` |
| Backtest a methodology | `vi backtest --methodology graham --years 5` |
| See the consensus (all methodologies) | `vi consensus AAPL --universe all` |
| Rank the consensus file | `vi consensus-ranking --universe sp500 --top 10` |
| Filter the screener by verdict | `vi screener --methodology graham:BUY --top 20` |
| See my portfolio | `vi portfolio view` |
| Check data freshness | `vi data-status AAPL` |
| List SEC filings | `vi filings AAPL --form 10-K` |

If you do not remember a command:

```bash
vi help --search methodology     # top matches with examples
vi help rank                     # same as vi rank --help
vi                               # interactive menu with categories
```

The Evolution (10-year charts) and Peers (peer radar) views live in the
Streamlit **Analysis** page, not in the CLI.

## Contents

- [Analysis](#analysis) — scorecard, financials, dcf, methodologies,
  analyze-*, compare-methodologies, company, opportunities, anomalies,
  momentum, alerts, interactive
- [Ranking & screening](#ranking--screening) — rank, screener, consensus,
  consensus-ranking, consensus-by-category
- [Portfolio](#portfolio) — portfolio (5 actions), watchlist (5 actions),
  backtest
- [Data & filings](#data--filings) — refresh, load-data, data-status,
  filings, filing-*, financial-alerts
- [Debug & misc](#debug--misc) — sql-analysis, debug
- [Appendix: JSON output shapes](#appendix-json-output-shapes)

## Global options

| Flag | Effect |
|---|---|
| `--no-color` | Disable ANSI colours (same as `NO_COLOR=1`); accepted before or after the subcommand |
| `-h`, `--help` | Show help for any command (`vi <cmd> --help`) |
| `--json` | Machine-readable output; only on `scorecard`, `financials`, `rank`, `refresh` and `dcf` (see Appendix) |
| `--demo` | Offline demo mode (8 bundled tickers, no PostgreSQL/SEC/Yahoo); available on the analysis, screener, filing and DCF commands that show it in `--help` |

`vi --no-color scorecard AAPL` and `vi scorecard AAPL --no-color` are
equivalent.

## Commands

### Analysis

#### `vi scorecard <ticker>`

Six-dimension scorecard: each dimension's score, verdict, rules and the
reasons behind them. Missing data is `INSUFFICIENT`/`N/A`, never fabricated.

Flags:
- `--period PERIOD`: fiscal period (default `FY`; `Q1`–`Q4` where stored)
- `--json`: print the raw payload (JSON shape in Appendix)
- `--markdown`: print a portable Markdown report
- `--out FILE`: with `--markdown`, write the report to `FILE`

```bash
./vi scorecard AAPL
./vi scorecard AAPL --markdown --out AAPL-scorecard.md
```

Exit codes: `0` OK, `2` unknown ticker or no data, `3` unexpected error.

#### `vi financials <ticker>`

Hierarchical T-view balance sheet: current/non-current assets and
liabilities plus shareholders' equity, with per-section subtotals and a
balance chip.

Flags:
- `--years N`: fiscal years to load (default `5`)
- `--period PERIOD`: fiscal period (default `FY`)
- `--json`: raw `FinancialsView` payload (JSON shape in Appendix)

```bash
./vi financials AAPL
./vi financials AAPL --years 3
```

#### `vi dcf <ticker>`

Two-stage discounted cash flow valuation (labelled `not-from-canon`, never a
book methodology). Variants: standard FCF, REIT FFO, bank/insurer DDM and
hyper-growth.

Flags:
- `--wacc WACC`: override the WACC (e.g. `0.10`)
- `--growth GROWTH`: override years 1–5 growth (e.g. `0.08`)
- `--terminal-growth VALUE`: override terminal growth (e.g. `0.03`)
- `--json`: print the result payload, including `reason` when
  `INSUFFICIENT_DATA` (shape in Appendix; see the known issue there)

```bash
./vi dcf AAPL
./vi dcf AAPL --wacc 0.09 --growth 0.06
```

#### `vi methodologies`

Multi-methodology engine commands.

```bash
./vi methodologies list
./vi methodologies show graham
```

#### `vi methodologies list`

Name, version, family and source of every registered methodology.

#### `vi methodologies show <name>`

Rules, verdict logic and known limitations of one methodology.

```bash
./vi methodologies show lynch_garp
```

#### `vi analyze <ticker> [ticker ...]`

Full analysis: ratios, scoring and DCF, printed in detail.

Flags: `--refresh` / `--no-refresh`, `--freshness-hours N` (default `168`).

```bash
./vi analyze AAPL
./vi analyze AAPL MSFT GOOGL --no-refresh
```

#### `vi analyze-full <ticker> [ticker ...]`

Consolidated six-section report: overview, price, metrics, Buffett quality,
historical valuation and risks.

Flags:
- `--no-prices`: skip real-time prices (section 2 stays partial)
- `--no-dcf`: skip the supplementary DCF section
- `--refresh` / `--no-refresh`, `--freshness-hours N`
- `--demo`

```bash
./vi analyze-full AAPL
./vi analyze-full AAPL --no-prices --no-dcf
```

#### `vi analyze-graham <ticker>`

Graham defensive-investor screen: 22 weighted rules across financial
strength, earnings quality, valuation, growth, dividends and margin of
safety (see `docs/graham_rules.md`). The verdict uses a weighted pass ratio
(BUY ≥ 0.85, WATCH ≥ 0.70, HOLD ≥ 0.50, else AVOID).

Flags: `--era-adjustment` (rescale the size threshold to 2024 dollars,
labelled `graham_modernized`), `--refresh` / `--no-refresh`,
`--freshness-hours N`, `--demo`.

```bash
./vi analyze-graham AAPL
./vi analyze-graham AAPL --era-adjustment
```

#### `vi analyze-graham-dodd <ticker>`

Graham & Dodd deep-value rules: NWC test, fixed-charge coverage, earnings
stability, balance sheet strength and margin of safety.

Flags: `--refresh` / `--no-refresh`, `--freshness-hours N`, `--demo`.

```bash
./vi analyze-graham-dodd AAPL
```

#### `vi analyze-buffett-classic <ticker>`

Buffett/Munger quality compounder: 20 explicit weighted rules across moat,
financial strength, earnings quality, capital allocation, valuation and
management (see `docs/buffett_rules.md`). Verdict thresholds match Graham:
BUY ≥ 0.85, WATCH ≥ 0.70, HOLD ≥ 0.50, else AVOID. Banks return `N/A`; REITs
are scored and carry a `[REIT]` badge.

Flags: `--refresh` / `--no-refresh`, `--freshness-hours N`, `--demo`.

```bash
./vi analyze-buffett-classic AAPL
```

#### `vi analyze-buffett-clark <ticker>`

Buffett/Clark seven rules for durable competitive advantage.

Flags: `--refresh` / `--no-refresh`, `--freshness-hours N`, `--demo`.

```bash
./vi analyze-buffett-clark AAPL
```

#### `vi analyze-fisher-quant <ticker>`

Fisher's four quantifiable points: R&D intensity, profit margin, cost control
and equity financing. The other 11 points need scuttlebutt and are out of
scope.

Flags: `--refresh` / `--no-refresh`, `--freshness-hours N`, `--demo`.

```bash
./vi analyze-fisher-quant AAPL
```

#### `vi analyze-lynch-garp <ticker>`

Lynch GARP rules: PEG, earnings-growth consistency, debt conservatism,
inventory watch and dividend-adjusted PEG.

Flags: `--refresh` / `--no-refresh`, `--freshness-hours N`, `--demo`.

```bash
./vi analyze-lynch-garp AAPL
```

#### `vi analyze-greenblatt <ticker>`

Greenblatt Magic Formula: looks the ticker up in the newest
`data/rankings/greenblatt_*.json` and maps its combined-rank percentile to a
verdict. Refresh the rankings with
`python -m scripts.compute_greenblatt_rankings --universe sp500`.

Flags: `--refresh` / `--no-refresh`, `--freshness-hours N`, `--demo`.

```bash
./vi analyze-greenblatt AAPL
```

#### `vi analyze-marks <ticker>`

Howard Marks' measurable rules: cycle position, resilience, margin of safety
and quality persistence.

Flags: `--refresh` / `--no-refresh`, `--freshness-hours N`, `--demo`.

```bash
./vi analyze-marks AAPL
```

#### `vi buffett-analysis <ticker> [ticker ...]`

Business quality (moat), financial strength and Buffett/Munger-style
insights.

Flags: `--full` (also print the full fundamental analysis), `--refresh` /
`--no-refresh`, `--freshness-hours N`.

```bash
./vi buffett-analysis AAPL
./vi buffett-analysis AAPL --full
```

#### `vi historical-valuation <ticker> [ticker ...]`

Historical P/E and FCF yield using the fiscal-year-end price from Yahoo.

Flags: `--refresh` / `--no-refresh`, `--freshness-hours N`, `--demo`.

```bash
./vi historical-valuation AAPL
```

#### `vi compare-methodologies <ticker>`

Runs every registered methodology on one ticker and prints a side-by-side
table plus a disagreement summary.

Flags: `--methodologies A,B` (comma-separated subset; default all), `--demo`.

```bash
./vi compare-methodologies AAPL
./vi compare-methodologies AAPL --methodologies graham,lynch_garp
```

#### `vi company <ticker>`

Name, sector/industry, price and key metrics for one ticker.

Flags: `--demo`.

```bash
./vi company META
```

#### `vi opportunities`

Detected situations (cheap quality, compounders, turnarounds, special
situations) with type, confidence and reasons.

Flags:
- `--tickers AAPL,MSFT`: restrict the universe
- `--type {UNDERVALUED_QUALITY,COMPOUNDERS,TURNAROUNDS,SPECIAL_SITUATIONS}`
- `--refresh` / `--no-refresh`, `--freshness-hours N`

```bash
./vi opportunities
./vi opportunities --type COMPOUNDERS
```

#### `vi anomalies [ticker ...]`

Latest year versus the historical mean/deviation (z-score) and abnormal
year-over-year jumps, with severity.

Flags: `--refresh` / `--no-refresh`, `--freshness-hours N`.

```bash
./vi anomalies AAPL
```

#### `vi momentum [ticker ...]`

Ranks by fundamental momentum (revenue acceleration, margins, ROIC, FCF) with
its dominant trigger.

Flags: `--refresh` / `--no-refresh`, `--freshness-hours N`.

```bash
./vi momentum
```

#### `vi alerts [ticker ...]`

Alert engine (`BUY_SIGNAL`, `SELL_WARNING`, `TRIGGER_EVENT`) over the
universe. With `--state`, evaluates score drops against a previous state file.

Flags:
- `--state STATE`: JSON with previous analyses (`{ticker: analysis}`)
- `--refresh` / `--no-refresh`, `--freshness-hours N`

```bash
./vi alerts
./vi alerts AAPL MSFT
```

#### `vi interactive`

Guided menu over the regular commands. Every option asks for its inputs with
numbered selectors, numeric fields (with visible defaults) and y/n questions;
no CLI flags need to be memorised. `x` opens the advanced raw-command mode,
`s` searches the help catalogue, `h` returns home and `q` quits. Typing `q`
or `back` at any prompt (or `Ctrl+C`) cancels it and returns to the previous
menu. Running `vi` with no arguments opens the same menu.

```bash
./vi interactive
```

### Ranking & screening

#### `vi rank (--by METHOD | --combine A,B)`

Ranks a universe with one methodology or an AND/OR/weighted combination.
Defaults to the demo universe for a quick smoke test.

Flags:
- `--by METHOD`: single methodology
- `--combine A,B`: comma-separated methodologies to combine
- `--strategy {and,or,weighted}`: combination strategy (default `and`)
- `--universe UNIVERSE`: `demo` | `sp500` | `nasdaq100` | `russell2000` |
  `all` | path to a CSV
- `--top N`: rows to show (default `20`)
- `--include-na`: include N/A verdicts with their reason
- `--positive-only`: keep only positive signals (STRONG_BUY/BUY/WEAK_BUY)
- `--json`: ranked payload (shape in Appendix)

```bash
./vi rank --by graham --top 20
./vi rank --by buffett_classic --top 20 --positive-only
./vi rank --combine graham,lynch_garp --strategy and --universe sp500
```

Exit codes: `0` OK, `2` bad universe or unknown methodology, `3` ranking
failure.

#### `vi screener`

Stock screener with fundamental filters. Two engines: market data
(Yahoo/EDGAR) or the Buffett quality engine (`--filter moat=STRONG
min_score=80`). Cached data is the default; SEC refresh is opt-in.

Flags:
- `--tickers TICKERS`, `--universe UNIVERSE` (`demo`), `--search QUERY`
- `--pe-max/--per-max N`, `--pe-min/--per-min N`, `--ev-ebit-max N`,
  `--pb-max N`, `--pb-min N`, `--roe-min N`, `--roic-min N`, `--fcf-min N`,
  `--fcf-yield-min N`, `--market-cap-min N`, `--debt-to-equity-max N`,
  `--op-margin-min N`, `--net-margin-min N`
- `--no-prices`: skip real-time prices
- `--filter 'field < value'|'key=value'`: raw market filter or Buffett
  quality filter
- `--methodology NAME:VERDICT`: keep tickers matching a methodology verdict;
  repeat for AND semantics (e.g. `graham:BUY`)
- `--top N`: max results (default `30`)
- `--save`: write `screener_resultados.csv`
- `--refresh` / `--no-refresh` (deprecated), `--freshness-hours N`, `--demo`

```bash
./vi screener --tickers AAPL,MSFT --no-prices --no-refresh
./vi screener --methodology graham:BUY --top 20
./vi screener --methodology graham:BUY --methodology lynch_garp:BUY
```

Exit codes: `0` success, `1` invalid filter/methodology or mixed engines
(argparse itself exits `2` on malformed usage). No `--json`: use `--save`
for a CSV.

#### `vi consensus <ticker>`

Reads the precomputed consensus file and prints one company's verdicts.

Flags: `--universe sp500|nasdaq100|all`, `--date YYYY-MM-DD`, `--csv CSV`,
`--demo`.

```bash
./vi consensus AAPL --universe all
```

#### `vi consensus-ranking`

Top rows of the consensus file.

Flags: `--universe`, `--date`, `--csv`, `--demo`, `--top N` (default `20`),
`--by {avoid,buys,score}` (default `buys`).

```bash
./vi consensus-ranking --universe sp500 --top 10
```

#### `vi consensus-by-category`

Consensus grouped by category.

Flags: `--universe`, `--date`, `--csv`, `--demo`, `--per-category N`
(default `5`).

```bash
./vi consensus-by-category --universe sp500
```

### Portfolio

#### `vi portfolio`

Positions, value, realized/unrealized PnL, risk concentration and sector
exposure. The subcommands below are the actual API.

#### `vi portfolio add <ticker> <quantity> <avg_price>`

Add (or average) a position.

Flags: `--thesis TEXT`, `--signal SIGNAL_AT_ENTRY` (e.g. `BUY`), `--date
YYYY-MM-DD` (default today), `--demo`.

```bash
./vi portfolio add AAPL 10 180 --thesis "strong moat"
```

#### `vi portfolio exit <ticker> <price>`

Close a position by selling.

Flags: `--date YYYY-MM-DD` (default today), `--demo`.

```bash
./vi portfolio exit AAPL 210
```

#### `vi portfolio remove <ticker>`

Delete a position without recording a sale.

Flags: `--demo`.

```bash
./vi portfolio remove AAPL
```

#### `vi portfolio view`

Positions enriched with scores.

Flags: `--demo`.

```bash
./vi portfolio view
```

#### `vi portfolio performance`

Portfolio returns, PnL and allocation analysis.

```bash
./vi portfolio performance
```

#### `vi watchlist`

Persistent watchlist enriched with scores, signal and opportunity.

#### `vi watchlist add <ticker>`

Add a ticker to the watchlist.

Flags: `--note TEXT` (reason for monitoring).

```bash
./vi watchlist add AAPL --note "pending entry"
```

#### `vi watchlist remove <ticker>`

Remove a ticker.

```bash
./vi watchlist remove AAPL
```

#### `vi watchlist status <ticker> --status {MONITORING,BOUGHT,DISCARDED}`

Change the watchlist status.

```bash
./vi watchlist status AAPL --status BOUGHT
```

#### `vi watchlist list`

Show the enriched watchlist.

```bash
./vi watchlist list
```

#### `vi watchlist export [path]`

Export the watchlist to CSV.

Flags: `--monitoring-only` (only `MONITORING` items).

```bash
./vi watchlist export --monitoring-only
```

#### `vi backtest`

Backtesting over yearly snapshots. Two modes:

- **Strategy mode** (default): simulates an equal-weighted portfolio with
  rebalancing every N years, using `--strategy {buffett,momentum}`.
- **Methodology mode** (`--methodology`): re-evaluates a book methodology at
  every fiscal-year end using only the fundamentals known then, holds the
  selected verdict for one year and reports the verdict breakdown per year,
  CAGR vs the equal-weight opportunity set and vs SPY, alpha, hit rate and
  Sharpe. A partial year is shown as `YTD` and excluded from CAGR/Sharpe.
  This is a **PoC**, not research-grade. Greenblatt is excluded (its ranking
  file is point-in-time).

Flags:
- `--strategy {buffett,momentum}` (default `buffett`)
- `--methodology METHOD[:VERDICT]`: repeatable; `graham`, `graham_dodd`,
  `buffett_classic`, `fisher_quantitative_subset`, `lynch_garp`, `marks`.
  Add `:VERDICT` to hold another verdict (e.g. `graham:AVOID`)
- `--universe UNIVERSE` (for `--methodology`, default `sp500`)
- `--limit N` (max tickers for `--methodology`, default `25`)
- `--years N`, `--top N` (default `5`), `--rebalance N` (default `1`)
- `--prices FILE`: `TICKER,YEAR,PRICE` per line for real returns
- `--equal-weight`: legacy equal weighting (default is tier-weighted:
  STRONG 60 / BUY 30 / WEAK 10, re-scaled when a tier is empty)
- `--json`: same payload as the rendered report (shape in Appendix)
- positional `tickers` (optional)

```bash
./vi backtest --strategy buffett --top 5
./vi backtest --methodology graham --years 5
./vi backtest --methodology buffett_classic --years 10 --limit 400
./vi backtest --methodology graham:AVOID --years 5 --equal-weight
./vi backtest --methodology graham --methodology lynch_garp --limit 50
```

Exit codes: `0` OK, `1` invalid `--top` or no tickers; `--methodology`
skips an unknown/excluded methodology with a printed reason and continues.

### Data & filings

#### `vi refresh <ticker>`

Targeted single-company refresh: SEC facts via `RefreshService` and the current
Yahoo price on demand. Prices are never persisted to FDB.

Flags: `--facts-only`, `--prices-only`, `--json` (shape in Appendix).

```bash
./vi refresh AAPL
./vi refresh AAPL --prices-only
```

Exit codes: `0` everything requested succeeded, `1` partial success (one of
facts/prices), `2` the requested domain failed (or both were requested and
neither succeeded).

#### `vi load-data <ticker> [ticker ...]`

Runs the full pipeline (fetch → normalize → store).

Flags: `--years N` (default `10`), `--force` (re-download and overwrite).

```bash
./vi load-data AAPL
./vi load-data AAPL --years 15 --force
```

#### `vi data-status <ticker> [ticker ...]`

Per-ticker source, coverage, quality, data provenance and whether a refresh is
needed.

```bash
./vi data-status AAPL
```

#### `vi filings <ticker>`

Reads the filings table and builds SEC EDGAR URLs. Nothing is downloaded; the
links open the official documents on sec.gov.

Flags: `--form 10-K,10-Q`, `--year YEAR` (repeatable), `--since YYYY-MM-DD`,
`--all`, `--urls`, `--limit N` (default `40`), `--open` (newest match in the
browser), `--demo`.

```bash
./vi filings AAPL
./vi filings AAPL --form 10-K --year 2025 --urls
```

#### `vi filing-balance-sheet <ticker>`

Finds the matching filing, fetches its HTML (cached under
`data/raw/filings/`), parses the balance sheet and prints the values as filed.

Flags: `--accession ACCESSION`, `--form FORM`, `--year YEAR`, `--raw`,
`--demo`.

```bash
./vi filing-balance-sheet AAPL
./vi filing-balance-sheet AAPL --year 2025 --raw
```

#### `vi filing-statement <ticker>`

Extracts a financial statement from a filing.

Flags: `--type {balance_sheet,income_statement,cash_flow}` (default
`balance_sheet`), `--accession`, `--form`, `--year`, `--raw`, `--demo`.

```bash
./vi filing-statement AAPL --type income_statement
```

#### `vi filing-income-statement <ticker>`

Extracts the income statement from a 10-K/10-Q.

Flags: `--accession`, `--form`, `--year`, `--raw`, `--demo`.

```bash
./vi filing-income-statement AAPL
```

#### `vi filing-cash-flow <ticker>`

Extracts the cash flow statement from a 10-K/10-Q.

Flags: `--accession`, `--form`, `--year`, `--raw`, `--demo`.

```bash
./vi filing-cash-flow AAPL
```

#### `vi filing-section <ticker>`

Extracts a narrative section (Risk Factors, MD&A) as plain text via the
TOC-anchor strategy.

Flags: `--type {risk_factors,md_a}` (default `risk_factors`), `--accession`,
`--form`, `--year`, `--word-limit N` (default `1000`), `--full`, `--demo`.

```bash
./vi filing-section AAPL --type md_a
```

#### `vi financial-alerts <ticker>`

Deterministic alert rules over the company's facts (cash runway, margins,
debt, FCF...).

Flags: `--period PERIOD` (default `FY`), `--severity
CRITICAL,WARNING,INFO` (display filter), `--demo`.

```bash
./vi financial-alerts AAPL
./vi financial-alerts AAPL --severity CRITICAL
```

Exit codes: `0` no CRITICAL alert, `1` at least one CRITICAL alert fired
(`--severity` only filters what is displayed).

### Debug & misc

#### `vi sql-analysis [script]`

Executes reusable SQL scripts from Financial-DataBase's `scripts/analysis`
directory.

Flags:
- positional `script` (without `.sql`) or `--script NAME`
- `--ticker TICKER`, `--cik CIK`, `--ciks A,B` (array scripts)
- `--params JSON`, `--limit N`, `--list`
- `--output {table,json,csv}` (default `table`)

```bash
./vi sql-analysis --list
./vi sql-analysis company_overview --ticker AAPL
./vi sql-analysis ratios_advanced --ticker AAPL --output json
```

#### `vi debug`

System diagnostics and quick tests.

```bash
./vi debug
```

## Appendix: JSON output shapes

Only these commands accept `--json`: `scorecard`, `financials`, `rank`,
`refresh`, `dcf` and `backtest`. `screener` has no `--json` (use `--save`
for CSV).

### `vi scorecard --json`

```json
{
  "ticker": "AAPL",
  "company": "Apple Inc.",
  "sector": "Technology",
  "industry": "Consumer Electronics",
  "period": "FY",
  "price": 342.37,
  "market_cap": 1510000000000.0,
  "generated": "",
  "dimensions": [
    {
      "key": "growth",
      "label": "Growth",
      "question": "Is the business getting bigger?",
      "score": 6,
      "verdict": "Mixed",
      "confidence": "HIGH",
      "evaluable_rules": 3,
      "rules": [],
      "trend": "stable",
      "summary": "6/10 — ...",
      "peer_group": null,
      "peer_group_level": null,
      "peer_group_size": null,
      "reason": null
    }
  ],
  "overall": "Mixed",
  "disagreements": [],
  "methodologies": [{"name": "graham", "verdict": "AVOID", "tier": null,
                     "score": 0.0, "confidence": "HIGH", "red_flags": 0}],
  "data_quality": "HIGH",
  "notes": []
}
```

Notes:
- `dimensions[].rules` contains `rule_id`, `label`, `status`
  (`PASS`/`WATCH`/`FAIL`/`INSUFFICIENT`/`N/A`), `value`, `threshold`,
  `reason`, source fields and optional peer columns.
- `dimensions[].reason` is set when the dimension is `N/A` (banks, insurers,
  capital-markets firms, REITs).
- `overall` is a label (`Strong`/`Mixed`/`Weak`/`Insufficient data`/`N/A`),
  never a number.

### `vi financials --json`

```json
{
  "ticker": "AAPL",
  "company_name": "Apple Inc.",
  "fiscal_period": "FY",
  "fiscal_year": 2025,
  "assets": {
    "current": [{"concept": "CashAndCashEquivalentsAtCarryingValue",
                 "label": "Cash and cash equivalents", "value": "35.9B"}],
    "non_current": [],
    "total_current": 147960000000.0,
    "total_non_current": 211280000000.0,
    "total": 359240000000.0
  },
  "liabilities_equity": {
    "current": [],
    "non_current": [],
    "equity": [],
    "total_current": 165630000000.0,
    "total_non_current": 119880000000.0,
    "total_equity": 73730000000.0,
    "total": 359240000000.0
  },
  "derived": {"liabilities": false, "equity": false},
  "balanced": true,
  "delta": 0.0,
  "balance_sheet": [
    {"concept": "Revenues", "label": "Revenue", "unit": "USD",
     "values": {"2026": "—", "2025": "416.2B"}}
  ]
}
```

Notes:
- `derived.liabilities = true`: liabilities computed as assets − equity.
- `derived.equity = true`: equity rebuilt from partial components (the text
  output shows a "partial equity" caption).
- `balanced` is true when `|delta|` is under 1% of total assets.

### `vi rank --json`

Single methodology (`--by`): a list of rows.

```json
[
  {"ticker": "AES", "verdict": "AVOID", "tier": null, "score": 57.14,
   "family": "DEEP_VALUE", "n_a_reason": null}
]
```

Combination (`--combine`): a list of combined rows.

```json
[
  {"ticker": "AAPL", "verdict": "BUY", "score": 82.0,
   "rationale": "...",
   "per_methodology": {
     "graham": {"ticker": "AAPL", "verdict": "AVOID", "tier": null,
                "score": 0.0, "family": "DEEP_VALUE", "n_a_reason": null}
   }}
]
```

### `vi refresh --json`

```json
{
  "ticker": "AAPL",
  "facts_synced": true,
  "prices_synced": true,
  "facts_error": null,
  "prices_error": null,
  "duration_seconds": 6.73
}
```

Notes:
- `prices_synced = true`: current Yahoo price fetched (in memory, **not**
  persisted to FDB).
- `facts_synced = true`: SEC facts synced to FDB.
- With `--facts-only`/`--prices-only`, the other domain stays `false`.

### `vi backtest --json` (methodology mode)

```json
{
  "methodology": "graham",
  "verdict_filter": "BUY",
  "universe": {"name": "sp500", "evaluated": 25, "total": 25,
               "sample_of": 500},
  "years": [{"year": 2021, "complete": true},
            {"year": 2025, "complete": false, "label": "YTD"}],
  "verdicts_by_year": {
    "2021": {"BUY": 0, "WATCH": 0, "HOLD": 0, "AVOID": 11, "N/A": 7,
             "INSUFFICIENT_DATA": 1}
  },
  "weighting_method": "tier",
  "tier_counts": {"STRONG_BUY": 13, "BUY": 30, "WEAK_BUY": 22},
  "performance": {
    "portfolio_cagr": 0.0,
    "opportunity_set_cagr": -0.009,
    "spy_cagr": 0.11,
    "alpha_vs_opportunity_set": 0.009,
    "alpha_vs_spy": -0.11,
    "portfolio_sharpe": null,
    "opportunity_set_sharpe": -0.02,
    "spy_sharpe": 0.70,
    "complete_years": [2021, 2022, 2023, 2024]
  },
  "no_buy_reason": {"rules": [{"id": "...", "name": "..."}],
                    "closest": [{"ticker": "BIIB", "year": 2022,
                                 "failed": ["..."], "n_failed": 2}],
                    "counts": {"lt3_failed": 4, "lt5_failed": 47}},
  "skipped_tickers": [{"ticker": "GEHC", "reason": "..."}],
  "notes": ["..."],
  "per_year": []
}
```

`universe.total` is the sample size (`--limit`), `sample_of` the full named
universe. `alpha_*` is `portfolio_cagr − benchmark_cagr`.

### `vi dcf --json`

The payload is the `DCFResult` dataclass:

```json
{
  "ticker": "AAPL",
  "intrinsic_value_per_share": 140.35,
  "current_price": 342.37,
  "margin_of_safety": -1.411,
  "verdict": "OVERVALUED",
  "wacc": 0.0937,
  "fcf_base": 98700000000.0,
  "fcf_years": 3,
  "growth_1_5": 0.061,
  "growth_6_10": 0.03,
  "terminal_growth": 0.025,
  "shares_outstanding": 14840000000.0,
  "sensitivity": {"(0.0737, 0.061)": 150.2},
  "reasons": ["..."],
  "missing_inputs": [],
  "reason": null,
  "source": "not-from-canon",
  "variant": "standard",
  "preferred_dividend_adjusted": false
}
```

Known issue (v0.23.0): when a valuation is computable, `sensitivity` holds
tuple keys `(wacc, growth_1_5)` and `json.dumps` cannot serialize them, so
`vi dcf <ticker> --json` raises `TypeError: keys must be str...`. The
`INSUFFICIENT_DATA` case (empty `sensitivity`) works and includes `reason`.
Tracked for the next patch; until then use the table output for computable
valuations.
