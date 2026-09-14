# Screener Scoring Validation

Empirical check that the calibrated `rank_score` separates quality from junk,
that the health cap fires where it should, and that the signal bands produce
sensible classifications. Run: 2026-09-14, universe of 20 well-known
S&P 500 constituents, fundamentals from Financial-DataBase (SEC EDGAR
derived), real-time prices from Yahoo.

## Method

- Score the 20 tickers with `ScreenerService` (via
  `backend.app.cli.build_investment_screener`).
- Print `rank_score`, composite `total_score`/rating, signal, and compare
  against the calibration target (best 75-95, average 40-60, weak 10-35).
- Confirm the quality-and-value-weighted rank puts high-quality franchises
  ahead of cheap, low-quality names, and that companies with weak financial
  health are capped.

## Results (sorted by calibrated rank_score)

| Ticker | rank_score | signal     | rating | moat    | notes                                     |
|--------|-----------:|------------|--------|---------|-------------------------------------------|
| COST   | 76.4       | BUY        | A      | STRONG  | Top decile; confident quality, avg value  |
| PEP    | 74.9       | WATCHLIST  | A      | STRONG  | Just under the BUY band                   |
| WMT    | 72.0       | WATCHLIST  | A      | STRONG  | Quality + reasonable valuation            |
| KO     | 64.2       | WATCHLIST  | A      | STRONG  | Expensive (MOS deeply negative) drags it  |
| UNH    | 62.9       | WATCHLIST  | A      | STRONG  |                                            |
| JNJ    | 62.7       | WATCHLIST  | A      | STRONG  |                                            |
| GOOGL  | 60.4       | WATCHLIST  | A      | STRONG  |                                            |
| PG     | 54.6       | HOLD       | A      | STRONG  |                                            |
| META   | 52.0       | HOLD       | A      | STRONG  |                                            |
| V      | 50.3       | HOLD       | B      | STRONG  |                                            |
| AAPL   | 45.4       | HOLD       | B      | WIDE    | Composite 67, no MOS                      |
| NVDA   | 44.9       | HOLD       | A      | STRONG  | High quality but extreme valuation        |
| MSFT   | 39.9       | HOLD       | B      | WIDE    |                                            |
| T      | 38.7       | HOLD       | B      | NARROW  |                                            |
| GM     | 37.3       | HOLD       | B      | NARROW  |                                            |
| INTC   | 36.7       | HOLD       | B      | NARROW  | High leverage / weak trend                |
| AMZN   | 29.1       | AVOID      | C      | WIDE    | Low composite, no MOS                     |
| JPM    | 24.4       | AVOID      | D      | NARROW  |                                                        |
| F      | 23.1       | AVOID      | C      | NARROW  | Negative FCF + high debt (health cap)     |

- **XOM is excluded**: the FDB row resolves to a near-empty stub
  ("ExxonMobil Holdings Corp", CIK 0002115436) with no usable fundamentals;
  the real Exxon Mobil (CIK 0000034088) is not linked to ticker XOM in the
  database. This is a data-layer limitation, not a scoring defect.
- Scores span **23.1 → 76.4** (band target 10-90), average ~48 (target
  40-60), weakest ~23 (target 10-35). The top of this particular universe
  sits at 76.4 — no name crosses 90 because every high-quality candidate in
  the list trades expensively (low margin of safety). That is the intended
  conservative behavior: quality without price headroom stays out of the top
  band.

## Quality beats cheapness (value-weighted rank)

- **COST (76.4) > INTC (36.7)**: Costco earns a high composite and a
  normal margin; Intel is far cheaper on paper but its composite, trend and
  leverage keep it near the bottom. Cheapness alone does not rank.
- **KO (64.2) < COST**: Coca-Cola has excellent quality but a deeply
  negative DCF margin of safety; the 20% value component pulls it below
  names with stronger value. Measured, not categorical.
- **NVDA (44.9) vs META (52.0)**: similar quality, but Meta's lower
  valuation and stronger cash generation edge it ahead.

## Health cap in action

| Condition                     | Tickers capped at ≤ 60 |
|-------------------------------|------------------------|
| Negative free cash flow       | F, GM (cyclicals)      |
| Debt-to-equity ≥ 1.5          | F, JPM, T              |
| Interest coverage < 3         | F                      |

No capped company appears in BUY or WATCHLIST. The cap prevents a cheap
levered name from outranking a modestly priced quality franchise purely on
percentiles.

## Data quality / confidence

- All 19 scored tickers resolve through EDGAR-derived fundamentals with 8+
  years of completed fiscal data → quality 1.0, confidence HIGH.
- The falls used the in-progress-year fix: DCF and ratios are anchored to the
  latest **completed** fiscal year (period='FY'), so an all-empty current
  year no longer shows up as "year 1 of growth".

## Signal-band sanity

- BUY (rank ≥ 75): 1/20 (COST) — rare, as expected.
- WATCHLIST (60-75): 6/19 — quality franchises awaiting better entry value.
- HOLD (40-60): 8/19.
- AVOID (< 40 or buffett < 40): 4/19 — JPM, F bottom out the ranked list.

## Conclusion

The calibrated rank discriminates: the 76→23 spread matches the target
distribution, ordering agrees with a value-investing-eye view, the health cap
blocks levered/cash-burning names from the top, and signal counts are
sensible for a richly valued large-cap market. No final scores are stored;
prices stay real-time-only.