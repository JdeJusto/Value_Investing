# Methodology backtesting — design (PoC)

Status: PoC shipped in v0.22.0. **Not research-grade.** It exists to answer
"do the BUY sets of these book methodologies beat an equal-weight basket over
the last N years?" with a deterministic, reproducible number, not to publish
performance claims.

## Question and scope

For each book methodology (Graham, Graham & Dodd, Buffett/Clark,
Buffett/Classic, Fisher, Lynch, Marks):

1. Re-evaluate the methodology at every fiscal-year end in the window using
   **only the fundamentals available at that fiscal year**.
2. Hold every selected verdict (positive tiers by default, or the
   `:VERDICT` filter) for one year. The default weighting is tier-based
   (STRONG 60% / BUY 30% / WEAK 10%, equal within a tier and re-normalized to
   the tiers present); `--equal-weight` restores the legacy equal weighting.
3. Compare the compounded return with two benchmarks: the **opportunity set**
   (equal-weighted same-sample basket) and **SPY** (market context).

Greenblatt is **excluded**: its verdict is a lookup in the current
`data/rankings/greenblatt_<date>.json`, which did not exist in past years.
Using today's ranking to label a 2021 company would be pure look-ahead.

## Definitions

Per signal year `Y`:

```text
selected_set(Y)  = tickers whose verdict matches the filter
                   (positive tiers by default) with rows up to fiscal year Y
forward(Y, t)    = price(t, FY_end(Y+1)) / price(t, FY_end(Y)) - 1
portfolio(Y)     = tier-weighted mean of forward(Y, t) over selected_set(Y)
                   (60/30/10 by STRONG/BUY/WEAK, equal within tier; 0 = cash)
opportunity(Y)   = mean(forward(Y, t) for every priced ticker)
spy(Y)           = SPY price(FY_end(Y+1)) / SPY price(FY_end(Y)) - 1
```

**Buy tiers (demote-only).** Each year, the evaluated tickers' scores are
ranked (score desc, ticker asc). Only tickers whose methodology verdict is
``BUY`` can be tiered: top 3% → STRONG_BUY, 3–10% → BUY, 10–15% → WEAK_BUY;
BUYs outside the top 15% are demoted to WATCH/HOLD/AVOID. WATCH/HOLD/AVOID
are never promoted, so a rule's rejection is preserved. A BUY without a
numeric score (e.g. some Lynch results) stays BUY with ``tier=None``. Small
universes (<50 scored) use absolute cut-offs: ≥80/60/50/40/30.

**Portfolio weighting.** ``weighting="tier"`` (default) weights STRONG_BUY
60%, BUY 30%, WEAK_BUY 10%, normalized to the tiers present that year
(BUY+WEAK → 75/25, STRONG+BUY → 66.7/33.3, only one tier → 100%).
``--equal-weight`` restores the legacy equal-weight behaviour (every positive
signal counts the same). In both modes an empty positive set is cash (0%).

**Complete vs YTD.** A year `Y` is complete only when `FY_end(Y+1)` has
already passed. An incomplete year is shown in the breakdown as `YTD` and is
**excluded from every CAGR/Sharpe** (including its return, so a partial year
cannot inflate the result).

Aggregates over the **complete** signal years:

| Metric | Definition |
|---|---|
| **CAGR** | `(∏ (1 + portfolio(Y)))^(1 / #years) − 1`, cash years included at 0% |
| **Opportunity set CAGR** | same compounding over `opportunity(Y)` |
| **SPY CAGR** | same compounding over `spy(Y)` |
| **Alpha** | `portfolio CAGR − benchmark CAGR` (opportunity set and SPY) |
| **Hit rate** | share of **invested** years (`selected_set(Y)` non-empty) with `portfolio(Y) > 0` |
| **Sharpe** | `mean(returns) / pstdev(returns)`, **no risk-free rate** |
| **Signals** | count per verdict (`BUY/WATCH/HOLD/AVOID/N/A/INSUFFICIENT_DATA`) |

Cash years are included in CAGR and Sharpe (the strategy really was out of the
market) but excluded from the hit rate (a cash year is neither a hit nor a
miss). The "closest" block ranks scored ticker-years by `len(failed_rules)`
from the methodology result; N/A companies do not participate.

## Data

- **Fundamentals:** `FinancialDatabaseRepository.list_all(ticker)`; rows are
  sorted by fiscal year and truncated to `fiscal_year <= Y` before evaluation,
  so the methodology never sees a later year. At least 3 rows are required.
  Since VI v0.33.0 / FDB v0.3.0, non-USD rows come from
  `core_financials.*_usd` (converted at the fiscal-year-end ECB rate) and
  carry the filing `currency` that drives the `[MIXED-CURRENCY]` badge. US
  rows keep the raw normalized USD history in the backtest (`list_years`) so
  historical results remain comparable; the analytical paths
  (`get_best_available`: scorecard, ranking, DCF) overlay the core USD fields
  for every ticker. A non-USD row with no FX rate is cleared, not mixed with
  the original value.
- **Prices:** `PriceService.get_price_at_fiscal_year_end` (Yahoo, on demand,
  never persisted). It uses the exact `period_end` from FDB, else December 31,
  and picks the closest trading day within ±15 calendar days.
- **Price adjustment:** the service calls `yf.Ticker(ticker).history()` with
  no `auto_adjust` argument. With the installed yfinance (1.7.0) the default
  is **`auto_adjust=True`**, so `Close` is already adjusted for splits **and
  dividends**; the frame has no `Adj Close` column. Returns are therefore
  close to total return (dividends reinvested at the ex-date), not raw price
  return. No separate dividend cash flow is modelled.
- **Cache:** `data/price_cache/<sha256(ticker)>_<start>_<end>.json`, a JSON
  list of `[ISO date, close]` pairs. It stores only the adjusted close, not
  OHLC/Adj Close. Historical ranges are permanent; a range ending within the
  last 7 days expires after one day. Legacy `<TICKER>_...json` files written
  before v0.32.1 remain on disk but are ignored by the hashed lookup.
- **Market cap for the methodologies:** the evaluation row's
  `shares_outstanding × split_adjustment_factor × price(Y)`, so past share
  counts line up with split-adjusted Yahoo prices.
- **Universe:** `config/universe.csv`, `--universe sp500` by default.
  `--limit N` takes an **evenly spaced deterministic sample** of the sorted
  tickers (not the first N alphabetically, which would bias towards A-tickers).


## Audit 2026-11-11 — prices, holdings and rebalancing

Read-only audit of the PoC semantics. The answers below refer to
`backend/services/price_service.py` and
`backend/services/methodology_backtest_service.py` at v0.32.0+.

### Prices

| # | Question | Answer |
|---|---|---|
| 1 | Is `auto_adjust` active? | **Yes, by default.** `history()` is called without the argument; yfinance 1.7.0 defaults to `auto_adjust=True`, so `Close` is split- and dividend-adjusted. A `history(auto_adjust=False)` call returns `Close` + `Adj Close`; the service never asks for that variant. |
| 2 | Fiscal year end on a weekend/holiday | `get_price_on_date` collects prices within **±15 calendar days** of `period_end` and picks the row with the smallest absolute day distance. A Saturday/Sunday therefore resolves to the preceding Friday (1 day) rather than Monday (2). On a mid-week holiday, the earlier trading day wins a tie because the series is chronological and `min()` keeps the first. No row within 15 days → `None` and the fiscal year is skipped. |
| 3 | ADR currency | Yahoo returns the **listing currency**: USD for SAN/TTE/BTI/AZN/SHEL on NYSE. FDB's normalized `currency` is **hardcoded "USD"** (`backend/repositories/fdb_mixins/normalization_mixin.py`, `TODO: Get from actual unit/currency data`), while raw facts for **SAN are EUR** and **BTI are GBP** (TTE/AZN/SHEL file USD). The return is a correct USD ADR price return, but valuation rules (P/E, P/B, FCF yield) mix EUR/GBP fundamentals with a USD price. This was a known bug until VI v0.33.0 (FDB v0.3.0): the repository now reads `core_financials.*_usd` and shows `[MIXED-CURRENCY]`. |
| 4 | yfinance failure | `_yf_call` retries up to 3 times with throttling and exponential backoff. On final failure `_fetch_historical_prices` records `_last_error` and returns `[]`; `get_price_on_date` returns `None`; `_price_series` omits that fiscal year. If fewer than 2 fiscal-year prices exist, the ticker is added to `skipped_tickers` (`no usable prices (N fiscal years)`). An empty series is cached in memory but **not written to disk**. |
| 5 | Exact date source | `FinancialDatabaseRepository.get_fiscal_year_end_date` derives `period_end` from the core FY facts (calendar-year match, annual span, latest `period_end`), then the price helper picks the closest trading day. If FDB has no date, the fallback is December 31 of the fiscal year. The return window is `FY_end(Y) → FY_end(Y+1)`, not calendar year-end. |

### Portfolio composition and rebalancing

| # | Question | Answer |
|---|---|---|
| 6 | STRONG_BUY in FY2022 → WATCH in FY2023 | The FY2022 signal is held for the FY2022→FY2023 forward window and earns that return. At the FY2023 boundary the portfolio is rebuilt from FY2023 verdicts; a WATCH is not selected (unless the filter is WATCH), so the position is effectively sold at that boundary. There is no explicit sell function and no carry-over. |
| 7 | Annual full rebalance or weight adjustment? | **Annual full rebalance, implicit.** Each signal year's selected set is a fresh one-year portfolio; the next year's set replaces it entirely. Weights are recomputed from that year's tiers. |
| 8 | Ticker leaves the universe/ranking or lacks a price | It is absent from the next year's evaluated set, so it is not held after the boundary (implicit sale). If `price(Y+1)` is missing, the signal year `Y` is skipped entirely (`if year + 1 not in prices: continue`), so no return is fabricated. |
| 9 | Return formula | `forward = price(FY_end(Y+1)) / price(FY_end(Y)) - 1`. With `auto_adjust=True`, that close-to-close ratio includes splits and dividends (approximate total return). No separate dividend cash flow. |
| 10 | Transaction costs / cash | **No** commissions, slippage, taxes or borrow. A year with no positive signal is **100% cash at 0%**. |
| 11 | Tier weighting | Fixed tier shares: STRONG 60%, BUY 30%, WEAK 10%, **normalized to the tiers present** (e.g. BUY+WEAK → 75/25; one tier → 100%). Within each tier, names are **equal-weighted** (`tier_weight / n_names`). It is not proportional to the number of names across tiers. |
| 12 | Opportunity set | **Recalculated every year** as the equal-weighted mean forward return of every evaluated ticker with both `price(Y)` and `price(Y+1)` that year; it is not a fixed basket from the initial sample. |

### Output and known gaps

- `--json` exposes `per_year` with `year`, `complete`, `buys`,
  `portfolio_return`, `benchmark_return` and `verdicts` counts, plus
  `tier_counts`/`signals`. It does **not** expose the holdings list per year.
  Positions must be inferred from the verdicts and the code above.
- `tier_counts` aggregates the **final, tiered** verdicts over all signal
  years (not per year); `verdicts_by_year` has the per-year counts.
- The cache had 501 hashed and 401 legacy ticker-named files on 2026-11-11;
  the legacy files are no longer read after the path-injection fix.
- The PoC notes still say "No dividends"; that is the historical wording. The
  actual `auto_adjust=True` behaviour embeds dividend adjustments in `Close`.
  The limitation is the *modelling* (no dividend cash flow), not the absence
  of income from the return.

## Run

```bash
./vi backtest --methodology graham --years 5
./vi backtest --methodology graham --methodology buffett_classic --years 10 --limit 50
python -m scripts.backtest_methodologies --all --years 10 --limit 50
python -m scripts.backtest_methodologies --tickers AAPL,MSFT,JNJ --all
```

Output: a context header (sample/evaluated/complete years), verdicts by year
with the three buy tiers, the weighting line, the performance table
(portfolio, opportunity set, SPY, alpha, Sharpe), the "closest to a signal"
block when the selected set is empty, skipped tickers and the PoC notes.
`--json` emits the same payload:

```text
methodology, verdict_filter, weighting_method, tier_counts,
universe {name, evaluated, total, sample_of},
years [{year, complete, label?}], verdicts_by_year, performance,
no_buy_reason, skipped_tickers, notes, per_year
```

The script writes `data/backtest/backtest_<date>.json` (git-ignored).

## Limitations (explicit)

1. **Total return is approximated by Yahoo's adjusted close.** With
   `auto_adjust=True`, `Close` includes splits and dividend adjustments, so
   income is not missing; it is embedded in the price rather than modelled as
   cash. The adjustment assumes dividends are reinvested at the ex-date.
2. **Survivorship / selection bias.** The universe is today's index
   constituents; companies removed from the index or delisted are absent.
3. **Restatements.** FDB stores the current normalized facts, not the figures
   as originally filed. Truncating by fiscal year prevents future *years* from
   leaking, but restated *values* of past years still leak mildly.
4. **Annual granularity.** One price per year; a BUY in March and a 30%
   drawdown in June are invisible.
5. **No costs.** No commissions, slippage, taxes or borrow.
6. **Tier weights, annual rebalance.** The default is STRONG 60 / BUY 30 /
   WEAK 10 (equal within a tier, re-normalized when a tier is empty), not
   equal weight. No position caps; `--equal-weight` is the legacy mode.
7. **Sharpe without a risk-free rate** and on ≤10 observations: it is a
   dispersion indicator, not an investable Sharpe ratio.
8. **Benchmark is equal-weight, not the S&P 500 index.**
9. **Small default sample (25 tickers).** Raise `--limit` for a wider run; the
   PoC is CPU/network bounded, not statistically powered.
10. **Greenblatt excluded** (see above). Its ranking file is point-in-time.
11. **Network dependence.** Without Yahoo the price series is empty and the
    run returns no years for that ticker (it degrades, never raises).
12. **Not bit-reproducible with live prices.** Prices are Yahoo adjusted-close
    snapshots cached under `data/price_cache/`. A cache-format change, an
    expired recent range or a Yahoo dividend/split adjustment revision can
    change one or two selected names' forward returns. The 2026-11-12 audit
    below shows a 23.76% → 22.14% drift with identical code and sample.


## Drift audit 2026-11-12 (v0.32.1 → v0.33.0)

A reported Buffett classic 10y/400 drift (23.76% → 22.14%) was investigated
read-only. Evidence:

- Re-running **v0.32.1** today and **v0.33.0** today with the same hashed
  price cache gives the **same result**: 22.1356% / 1.4888, identical
  `tier_counts` (63 STRONG + 4 BUY) and identical per-year returns.
- The 23.76% run predates the SHA-256 cache-key change and used the legacy
  `<TICKER>_2000-01-01_now.json` files. Comparing 401 legacy/hashed pairs:
  49 tickers have at least one day with >1% difference (max 3.8%), mostly
  small dividend-adjustment revisions.
- The difference is concentrated in selected-name years: 2019 37.94% →
  23.68% and 2017 29.82% → 26.05%; 2016, 2018, 2020–2024 are unchanged.
  The 400-ticker sample contains **0 non-USD filers**, so the currency fix is
  not involved.
- `financial_facts.max(updated_at)` is 2026-11-10, before both runs; P4
  (FDB data changed) is ruled out. `balance_effective` is not read by the
  backtest (P3 ruled out).

**Conclusion: P1 (price cache/adjusted-close drift), not a code bug.** The
v0.33.0 result is the reproducible one with the current cache; the old 23.76%
is not reproducible without the legacy price files. To make backtests
bit-reproducible, freeze the price series alongside the run artifact
(`docs/backlog.md`).

## Why this is enough for now

The PoC validates the plumbing (point-in-time fundamentals, forward returns,
per-year aggregation, deterministic artifacts) and produces a number a human
can sanity-check. A research-grade version would need a point-in-time
fundamentals store, delisted-price data, dividends, monthly rebalancing and a
proper factor model. That is a separate project, recorded in
`docs/backlog.md`.

## Tests

- `test_backtest_graham_returns_metrics`: a fake repository + fake prices run
  end-to-end and return a payload with `annualized_return`, `hit_rate`,
  `sharpe` and per-year rows.
- `test_backtest_truncates_future_rows`: the methodology only receives rows up
  to the signal year.
- `test_greenblatt_is_rejected`: explicit look-ahead error.
- `test_cli_backtest_methodology_prints_a_table`: the CLI dispatcher formats
  the result.
