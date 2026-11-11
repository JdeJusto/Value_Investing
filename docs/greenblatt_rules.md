# Greenblatt rules — Magic Formula overlay (v2.0.0)

`greenblatt` is **cross-sectional**: it reads the weekly ranking file produced
by `scripts/compute_greenblatt_rankings.py` and never recomputes the ranking
inside a single-ticker evaluation.

**The ranking remains the primary input.** v2.0.0 replaces the old percentile
cut (top 10% BUY / top 30% WATCH / top 50% HOLD / below AVOID) as the *source*
of the verdict with a transparent weighted overlay around the rank. The rank
checks are the largest single block of weight, and a top-50 combined rank is
the normal path to BUY, but the overlay can fail a highly ranked company on
quality grounds and can keep a bottom-half company in HOLD when its
fundamentals are clean.

Source: *The Little Book That Beats the Market* (Greenblatt, 2005). The book
was **not available** (see
`docs/books_notes/the-little-book-that-beats-the-market.md`), so every rule
below cites `page="public knowledge"` and its threshold is an approximation,
not a page citation.

## Weights and score

- **weight 2 (critical)**: presence in the ranking file, top-50 rank, top-100
  rank.
- **weight 1 (normal)**: the ROC / earnings-yield decomposition and the
  quality overlay.
- **weight 0 (informational)**: capital turnover and the bank scope guard.
- `weighted_score = Σ weight(passed) / Σ weight(evaluable)`; `N/A` rules are
  excluded from the denominator and weight-0 rules never enter it.
- Verdict: **BUY ≥ 0.85**, **WATCH 0.70–0.85**, **HOLD 0.50–0.70**,
  **AVOID < 0.50**. More than **30%** of the weighted rules missing data makes
  the verdict `INSUFFICIENT_DATA`.

## The 12 overlay rules

| # | Rule id | Category | W | Condition | Source |
|---|---|---|---:|---|---|
| 1 | `rank_in_file` | ranking | 2 | the ticker has an entry in the newest ranking file | public knowledge |
| 2 | `rank_top_50` | ranking | 2 | combined rank = rank_ROC + rank_EY ≤ 50 | public knowledge |
| 3 | `rank_top_100` | ranking | 2 | combined rank ≤ 100 | public knowledge |
| 4 | `roc_ebit_positive` | return_on_capital | 1 | EBIT (the ROC numerator) > 0 | public knowledge |
| 5 | `roc_above_20` | return_on_capital | 1 | ROC ≥ 20% | public knowledge |
| 6 | `roc_capital_turnover_computable` | return_on_capital | 0 | revenue / (max(CA − CL, 0) + net PPE) computable | public knowledge |
| 7 | `ey_above_8` | earnings_yield | 1 | EBIT / EV ≥ 8% | public knowledge |
| 8 | `ey_above_12` | earnings_yield | 1 | EBIT / EV ≥ 12% | public knowledge |
| 9 | `ey_ev_positive` | earnings_yield | 1 | enterprise value > 0 | public knowledge |
| 10 | `quality_market_cap_above_100m` | quality | 1 | market cap > $100M | public knowledge |
| 11 | `quality_revenue_positive` | quality | 1 | revenue > 0 | public knowledge |
| 12 | `quality_not_a_bank` | quality | 0 | informational scope guard (financials abstain before the overlay) | public knowledge |

The three original explicit rule ids (`rule_1_roc`, `rule_2_earnings_yield`,
`rule_3_combined_rank`) are kept in `passed_rules` / `failed_rules` for
compatibility. They are **reporting-only** and are not double-counted in the
weighted score; `rule_3` reports whether the percentile is inside the top 50%.

## Where the overlay gets its inputs

- **ROC and EY** come from the ranking entry (`roc`, `earnings_yield`); they are
  not recomputed from the row. `roc_above_20` deliberately reads the ranking so
  a single-ticker run cannot disagree with the weekly universe run.
- **Market cap** is taken from `entry["market_cap"]` when a future ranking
  payload provides it. The current script does not, so the overlay derives it
  from the ranking's own earnings yield: `EV = EBIT / EY`, then
  `market cap = EV − total debt + cash`. This keeps the methodology hermetic
  (no price-service call) at the cost of inheriting the ranked row's rounding.
- **Revenue, working capital and net PPE** come from the fundamentals row that
  matches the ranking entry's `fiscal_year` (latest row as fallback).

## Ranking file behaviour (unchanged)

- The newest `data/rankings/greenblatt_*.json` is used; files older than
  **14 days** are stale and return `INSUFFICIENT_DATA`.
- A ticker outside the S&P 500 ranking universe returns `NOT_APPLICABLE`
  (`ticker not in ranking universe (SP500)`).
- A ticker in the universe but missing from the file returns
  `INSUFFICIENT_DATA` and asks to regenerate the ranking.
- Non-positive ROC or earnings yield in the ranking returns
  `INSUFFICIENT_DATA` (the ranking script already excludes those rows).
- Financials and REITs return `NOT_APPLICABLE` (the ROC denominator assumes a
  classified industrial balance sheet).

## Relationship to the old percentile verdict

With a top-50 rank and clean fundamentals the weighted score is in BUY range.
A rank outside the top 50 loses 2 of 13 weight; outside the top 100 loses 4,
which moves a clean company to WATCH/HOLD. The overlay is **more forgiving at
the bottom** than the old `AVOID` cut: a company that is ranked with positive
ROC/EY and clean quality checks lands in HOLD, not AVOID, because AVOID now
requires fundamental failures as well as a poor rank. The docs and tests treat
this as the intended v2.0.0 behaviour, not an accident.

## Data limits and deferred rules

- **Absolute rank cutoffs scale with the universe.** `combined_rank` ranges
  from 2 to 2N, so "top 50" is ~5% for a 500-name run and ~25% for a 100-name
  run. The old percentile mapping was scale-free; a percentile-aware version
  is a backlog item.
- **The ranking payload has no market cap**, so the $100M floor is derived
  from `EV = EBIT / EY`. A payload that stores market cap is used directly.
- **Book pages are unavailable**, so no page-level fidelity is claimed.
- **Deferred**: sector-relative ROC (the book excludes financials/utilities),
  a payload field for market cap, and a book-backed review of the exact ROC/EY
  definitions once the reference text is available.
- No full S&P 500 distribution was measured for this change; run
  `scripts/compute_greenblatt_rankings.py` and the screener to calibrate before
  treating the new bands as production thresholds.

## Measured distribution (SP500, 2026-11-11)

Base verdicts from the one-pass evaluation of 500 SP500 tickers (tiering is a
separate cross-sectional step: `vi rank --by greenblatt`).

| Verdict | Count |
|---|---:|
| STRONG_BUY / BUY / WEAK_BUY (base) | 3 / 0 / 0 |
| WATCH | 4 |
| HOLD | 187 |
| AVOID | 63 |
| N/A (banks/insurers) | 99 |
| INSUFFICIENT_DATA | 144 |

N/A includes the 71 banks/insurers plus 28 tickers outside the SP500 ranking file; INSUFFICIENT is dominated by the ranking-file coverage (the ranking must be refreshed weekly).
