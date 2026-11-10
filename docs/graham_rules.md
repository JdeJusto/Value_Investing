# Graham rules — deep expansion (v0.26.0)

The Graham screen now evaluates **22 rules** across six categories and
aggregates them with a weighted score. The original eight criteria are kept
verbatim; the new rules are quantitative checks derived from *The Intelligent
Investor* (ch. 14–15) and documented as public-knowledge approximations where
the book's formulation needs data the pipeline does not hold.

## Weights and score

- **weight 2 (critical)**: the valuation gates, earnings growth, positive
  earnings, current ratio and the P/E × P/BV product.
- **weight 1 (normal)**: supporting balance-sheet, growth and dividend checks.
- **weight 0 (informational)**: the enterprising-investor P/E ≤ 10 bar; it is
  shown but never scored.
- `weighted_score = Σ weight(passed) / Σ weight(evaluable)`, where
  `N/A`/`INSUFFICIENT` rules are excluded from the denominator and weight-0
  rules never enter it.
- Verdict: **BUY ≥ 0.85**, **WATCH 0.70–0.85**, **HOLD 0.50–0.70**,
  **AVOID < 0.50**. More than **30%** of the weighted rules missing data makes
  the verdict `INSUFFICIENT_DATA`.
- This base verdict feeds the v0.24 demote-only tier assignment: a Graham
  `WATCH`/`HOLD`/`AVOID` is never promoted; a Graham `BUY` can become
  `STRONG_BUY`/`BUY`/`WEAK_BUY` relative to the universe.

## The 22 rules

| # | Rule id | Category | W | Condition | Source |
|---|---|---|---:|---|---|
| 1 | `criterion_1_size` | financial_strength | 1 | revenue ≥ $100M (or utilities assets ≥ $50M; era adjustment ×5.6) | Ch. 14 |
| 2 | `criterion_2_current_ratio` | financial_strength | 2 | current ratio ≥ 2.0 | Ch. 14 |
| 3 | `criterion_3_debt_vs_working_capital` | financial_strength | 1 | total debt ≤ working capital | Ch. 14 |
| 4 | `criterion_4_dividend_history` | dividends | 1 | ≥ 20 years with a dividend (capped by available history) | Ch. 14 |
| 5 | `criterion_5_earnings_growth` | growth | 2 | EPS +33% over the decade (3-year averages) | Ch. 14 |
| 6 | `criterion_6_pe` | valuation | 2 | P/E ≤ 15 on 3-year average earnings | Ch. 14 |
| 7 | `criterion_7_pbv` | valuation | 2 | P/BV ≤ 1.5 | Ch. 14 |
| 8 | `criterion_8_pe_pbv_product` | valuation | 2 | P/E × P/BV ≤ 22.5 | Ch. 14 |
| 9 | `deep_debt_to_equity` | financial_strength | 1 | total debt / equity < 1 | public (conservative) |
| 10 | `deep_interest_coverage` | financial_strength | 1 | EBIT / interest ≥ 5x (debt-free passes) | Ch. 14 criterion 2 |
| 11 | `deep_positive_working_capital` | financial_strength | 1 | current assets > current liabilities | Ch. 14 criterion 2 |
| 12 | `deep_positive_earnings_10y` | earnings_quality | 2 | every available year of the last 10 profitable | Ch. 14 criterion 5 |
| 13 | `deep_earnings_stability` | earnings_quality | 1 | stdev of yearly EPS growth < 15% | Ch. 14 criterion 5 |
| 14 | `deep_net_income_growing_3y` | earnings_quality | 1 | latest net income > previous two years | public (short-term growth) |
| 15 | `deep_positive_eps` | earnings_quality | 1 | latest EPS > 0 | Ch. 14 criterion 5 |
| 16 | `deep_graham_number` | valuation | 2 | price ≤ √(22.5 × EPS × BVPS) | public (Graham Number) |
| 17 | `deep_pe_below_10` | valuation | 0 | P/E ≤ 10 (informational, enterprising) | Ch. 15 |
| 18 | `deep_revenue_growth` | growth | 1 | revenue CAGR ≥ 3% | public (inflation proxy) |
| 19 | `deep_payout_ratio` | dividends | 1 | payout < 80% | public (dividend safety) |
| 20 | `deep_no_dividend_suspension` | dividends | 1 | no zero-dividend year in the available history | Ch. 14 criterion 4 |
| 21 | `deep_epv_margin` | margin_of_safety | 1 | price ≤ 2/3 × EPV (EBIT × (1−tax) / 9%) | public (EPV, 9% fixed discount) |
| 22 | `deep_ncav_margin` | margin_of_safety | 1 | NCAV/share > 1.5 × price | Ch. 14 / net-net |

## Measured distribution (SP500, 2026-11-10)

| Verdict | Before v0.26 | After v0.26 |
|---|---:|---:|
| BUY | 0 | 0 |
| WATCH | 2 | 3 |
| HOLD | 54 | 95 |
| AVOID | 419 | 310 |
| N/A (financial/REIT) | 71 | 71 |
| INSUFFICIENT_DATA | 8 | 21 |

The three WATCH names are the closest to the BUY line: VICI (84.21), LEN
(80.0) and SMCI (77.27). No company clears 0.85 in the current market; that is
the honest result, not a bug. The deep rules mostly turn a flat AVOID into a
more informative HOLD/WATCH/AVOID gradient.

Backtest (`--years 5 --limit 400`): 2022 has one STRONG_BUY; portfolio CAGR
4.2% vs opportunity set 21.2% and SPY 14.3% (the strategy sat in cash most
years). The high `INSUFFICIENT` counts in 2021–2022 reflect the deep rules
needing history (EBIT/interest/current split) that older fiscal years do not
always carry; the backtest's `INSUFF` column makes that visible instead of
silently guessing.

## Data limits and deferred rules

Implemented with the columns available in `NormalizedFinancials` /
`core_financials`. The following cannot be computed without a data-pipeline
change and stay in `docs/backlog.md`:

- **Long-term debt separately**: `long_term_debt` is not populated by the
  repository; criterion 3 uses `total_debt`, which is stricter.
- **Full 20-year dividend record**: FDB history is ~16 years; the deep
  no-suspension rule checks every available year and the original rule keeps
  the 20-year bar (it fails when the history is shorter).
- **Dynamic EPV/WACC**: EPV uses a fixed 9% discount rate; a WACC-aware EPV
  needs a price/risk policy.
- **Insider ownership / management quality**: qualitative, not in FDB.
- **True net-net NCAV** (cash + receivables − all liabilities): the
  approximation uses current assets − total liabilities.
