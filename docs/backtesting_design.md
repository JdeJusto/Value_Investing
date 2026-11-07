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
2. Hold every BUY for one year, equal-weighted.
3. Compare the compounded return with an equal-weight benchmark of the same
   evaluated universe.

Greenblatt is **excluded**: its verdict is a lookup in the current
`data/rankings/greenblatt_<date>.json`, which did not exist in past years.
Using today's ranking to label a 2021 company would be pure look-ahead.

## Definitions

Per signal year `Y`:

```text
buy_set(Y)       = tickers whose verdict is BUY with rows up to fiscal year Y
forward(Y, t)    = price(t, FY_end(Y+1)) / price(t, FY_end(Y)) - 1
portfolio(Y)     = mean(forward(Y, t) for t in buy_set(Y))   # 0 if empty (cash)
benchmark(Y)     = mean(forward(Y, t) for every priced ticker)
```

Aggregates over the signal years `Y` that had at least one priced ticker:

| Metric | Definition |
|---|---|
| **CAGR** | `(∏ (1 + portfolio(Y)))^(1 / #years) − 1`, cash years included at 0% |
| **Benchmark CAGR** | same compounding over `benchmark(Y)` |
| **Hit rate** | share of **invested** years (`buy_set(Y)` non-empty) with `portfolio(Y) > 0` |
| **Sharpe** | `mean(portfolio(Y)) / pstdev(portfolio(Y))`, **no risk-free rate** |
| **BUYs** | total BUY signals across ticker-years |
| **Signals** | count per verdict (`BUY/WATCH/HOLD/AVOID/N/A/INSUFFICIENT_DATA`) |

Cash years are included in CAGR and Sharpe (the strategy really was out of the
market) but excluded from the hit rate (a cash year is neither a hit nor a
miss).

## Data

- **Fundamentals:** `FinancialDatabaseRepository.list_all(ticker)`; rows are
  sorted by fiscal year and truncated to `fiscal_year <= Y` before evaluation,
  so the methodology never sees a later year. At least 3 rows are required.
- **Prices:** `PriceService.get_price_at_fiscal_year_end` (Yahoo, on demand,
  never persisted). It uses the exact fiscal-year-end date from FDB, else
  December 31, and picks the closest trading day within ±15 days.
- **Market cap for the methodologies:** the evaluation row's
  `shares_outstanding × split_adjustment_factor × price(Y)`, so past share
  counts line up with split-adjusted Yahoo prices.
- **Universe:** `config/universe.csv`, `--universe sp500` by default.
  `--limit N` takes an **evenly spaced deterministic sample** of the sorted
  tickers (not the first N alphabetically, which would bias towards A-tickers).

## Run

```bash
./vi backtest --methodology graham --years 5
./vi backtest --methodology graham --methodology buffett_classic --years 10 --limit 50
python -m scripts.backtest_methodologies --all --years 10 --limit 50
python -m scripts.backtest_methodologies --tickers AAPL,MSFT,JNJ --all
```

Output: table on stdout and `data/backtest/backtest_<date>.json` (git-ignored,
one payload with every methodology, the tickers and the per-year rows).

## Limitations (explicit)

1. **Price return only.** Dividends are excluded, so income strategies are
   understated relative to a total-return benchmark.
2. **Survivorship / selection bias.** The universe is today's index
   constituents; companies removed from the index or delisted are absent.
3. **Restatements.** FDB stores the current normalized facts, not the figures
   as originally filed. Truncating by fiscal year prevents future *years* from
   leaking, but restated *values* of past years still leak mildly.
4. **Annual granularity.** One price per year; a BUY in March and a 30%
   drawdown in June are invisible.
5. **No costs.** No commissions, slippage, taxes or borrow.
6. **Equal weight, yearly rebalance.** No position sizing, no caps.
7. **Sharpe without a risk-free rate** and on ≤10 observations: it is a
   dispersion indicator, not an investable Sharpe ratio.
8. **Benchmark is equal-weight, not the S&P 500 index.**
9. **Small default sample (25 tickers).** Raise `--limit` for a wider run; the
   PoC is CPU/network bounded, not statistically powered.
10. **Greenblatt excluded** (see above). Its ranking file is point-in-time.
11. **Network dependence.** Without Yahoo the price series is empty and the
    run returns no years for that ticker (it degrades, never raises).

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
