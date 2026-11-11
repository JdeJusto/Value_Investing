# Graham & Dodd rules — deep expansion (v2.0.0)

`graham_dodd` now evaluates **26 rules** across five categories and aggregates
them with the shared weighted score. The original five rules are kept verbatim
(now weighted); the 21 new rules come from *Security Analysis* (Graham & Dodd,
1934) and are labelled as public-knowledge derivations where the curated notes
do not support a page citation.

Source notes: `docs/books_notes/security-analysis.md` (1st Spanish edition,
1,097 pp.). Pages used: 5 (NWC / net-net, margin of safety), 101 (earnings
stability, intrinsic value), 38/41 (balance-sheet strength), 230 (bond
standards: fixed-charge coverage, dividend record).

## Weights and score

- **weight 2 (critical)**: the net-net bargain, current ratio, debt < equity,
  positive earnings (10y), P/B < 1 and the Graham Number.
- **weight 1 (normal)**: supporting balance-sheet, earnings-power and
  asset-value checks.
- **weight 0 (informational)**: `rule_5_margin_of_safety`,
  `net_net_ncav_positive` (gate shown but scored by the net-net rules) and
  `asset_coverage_2x` (a bond standard, not an equity criterion).
- `weighted_score = Σ weight(passed) / Σ weight(evaluable)`; `N/A` rules are
  excluded from the denominator and weight-0 rules never enter it. Scored
  weight: 35 (8 from the original rules, 27 from the deep checks).
- Verdict: **BUY ≥ 0.85**, **WATCH 0.70–0.85**, **HOLD 0.50–0.70**,
  **AVOID < 0.50**. More than **30%** of the weighted rules missing data makes
  the verdict `INSUFFICIENT_DATA`.

The base verdict feeds the v0.24 demote-only tier assignment unchanged.

## The 26 rules

### Original rules (kept, weighted)

| # | Rule id | Category | W | Condition | Source |
|---|---|---|---:|---|---|
| 1 | `rule_1_nwc` | net_net | 2 | price < 2/3 of working capital per share (CA − CL) | p. 5 |
| 2 | `rule_2_fixed_charge_coverage` | earnings_power | 2 | operating income / interest ≥ 1.5x in 5 of the last 6 years | p. 230 |
| 3 | `rule_3_earnings_stability` | earnings_power | 2 | net income positive in ≥ 7 of the last 10 years | p. 101 |
| 4 | `rule_4_balance_sheet_strength` | balance_sheet | 2 | total liabilities / total assets ≤ 0.5 | p. 38, 41 |
| 5 | `rule_5_margin_of_safety` | margin_of_safety | 0 | qualitative summary of rules 1–4; never scored | p. 5, 101 |

### Deep checks

| # | Rule id | Category | W | Condition | Source |
|---|---|---|---:|---|---|
| 6 | `net_net_ncav_positive` | net_net | 0 | NCAV = current assets − total liabilities > 0 | p. 5 |
| 7 | `net_net_ncav_above_market_cap` | net_net | 2 | NCAV > market cap (price × split-adjusted shares) | p. 5 |
| 8 | `net_net_ncav_1_5x_market_cap` | net_net | 2 | NCAV ≥ 1.5 × market cap | p. 5 |
| 9 | `net_net_price_le_two_thirds_ncav` | net_net | 2 | price ≤ 2/3 × NCAV per share | p. 5 |
| 10 | `balance_current_ratio_2` | balance_sheet | 2 | current ratio ≥ 2.0 | public knowledge (derived) |
| 11 | `balance_debt_below_equity` | balance_sheet | 2 | total debt < book equity (negative equity fails) | public knowledge (derived) |
| 12 | `balance_positive_working_capital` | balance_sheet | 1 | current assets > current liabilities | p. 5 |
| 13 | `balance_debt_le_half_equity` | balance_sheet | 1 | total debt ≤ 50% of book equity | public knowledge (derived) |
| 14 | `balance_debt_le_working_capital` | balance_sheet | 1 | total debt ≤ working capital (total-debt proxy) | public knowledge (derived) |
| 15 | `earnings_positive_5y` | earnings_power | 1 | every available year of the last five profitable | p. 101 |
| 16 | `earnings_positive_10y` | earnings_power | 2 | every available year of the last decade profitable (≥ 5 years required) | p. 101 |
| 17 | `earnings_stability_20pct` | earnings_power | 1 | stdev of yearly EPS growth < 20% | p. 101 (dispersion is an extension) |
| 18 | `earnings_eps_growth_10y` | earnings_power | 1 | 10-year EPS CAGR ≥ 10% (10 years required) | public knowledge (derived) |
| 19 | `earnings_epv_above_market_cap` | earnings_power | 1 | EPV = EBIT × (1 − tax) / 9% > market cap | public knowledge (derived) |
| 20 | `asset_pb_below_1` | asset_value | 2 | price / BVPS < 1.0 | public knowledge (derived) |
| 21 | `asset_pb_below_067` | asset_value | 1 | price / BVPS < 0.67 | public knowledge (derived) |
| 22 | `asset_tangible_book_positive` | asset_value | 1 | book equity > 0 (tangible-book proxy) | public knowledge (derived) |
| 23 | `asset_coverage_2x` | asset_value | 0 | total assets / debt ≥ 2x (bond standard) | public knowledge (derived) |
| 24 | `margin_price_below_graham_number` | margin_of_safety | 2 | price ≤ √(22.5 × EPS × BVPS) | public knowledge (derived) |
| 25 | `margin_price_below_ncav` | margin_of_safety | 1 | price < NCAV per share | p. 5 |
| 26 | `margin_dividend_record_10y` | margin_of_safety | 1 | no interrupted dividend in the available decade (≥ 5 years required) | p. 230 (bond standard) |

`public knowledge (derived)` means the rule follows from the book's principles
but the curated notes do not print the threshold; the `SourceRef.page` says
`public-knowledge derivation` and the caution field states the approximation.
No page is invented.

## Strictness

Graham & Dodd is deliberately strict. On a modern large-cap universe the
net-net, P/B < 1 and Graham Number gates rarely pass, so most companies land in
HOLD/AVOID even with a clean balance sheet. Thresholds are **not** relaxed to
produce positives; the score measures the distance from a 1934 bargain.

## Data limits and deferred rules

- **Two NCAV definitions coexist.** The original rule 1 uses *working capital*
  (current assets − current liabilities); the deep net-net rules use the book's
  stricter *net current asset value* (current assets − **total** liabilities,
  p. 5). A company can pass rule 1 and still fail the deep NCAV tests.
- **Long-term debt is proxied by `total_debt`.** `NormalizedFinancials` carries
  `long_term_debt`, but FDB does not populate it reliably for every filer;
  using total debt makes `balance_debt_le_working_capital` stricter than the
  printed rule.
- **Tangible book value** uses book equity: FDB has no intangible-assets line.
- **EPV** uses a fixed 9% discount rate (public-knowledge convention) and the
  row's effective tax rate when available (21% otherwise); a WACC-aware EPV
  needs a price/risk policy.
- **Decade rules** need history: `earnings_eps_growth_10y` requires 10 fiscal
  years; `earnings_positive_10y` and `margin_dividend_record_10y` evaluate the
  available years when at least five are present (the FDB history is ~16
  years).
- **Market cap** is `price × split-adjusted shares` from the price service; no
  live price makes every market-cap rule N/A (never a silent pass).
- **Deferred** (needs a data-pipeline change): cash + receivables net-net
  (a stricter liquidation view), inventory write-downs, separate long-term
  debt, dynamic EPV/WACC, and qualitative management/insider analysis.

## Measured distribution (SP500, 2026-11-11)

Base verdicts from the one-pass evaluation of 500 SP500 tickers (tiering is a
separate cross-sectional step: `vi rank --by graham_dodd`).

| Verdict | Count |
|---|---:|
| STRONG_BUY / BUY / WEAK_BUY (base) | 0 / 0 / 0 |
| WATCH | 0 |
| HOLD | 22 |
| AVOID | 363 |
| N/A (banks/insurers) | 71 |
| INSUFFICIENT_DATA | 44 |

Graham & Dodd is deliberately strict: 363 AVOID and no positive signal on the current large-cap universe is the honest result, not a calibration bug.
