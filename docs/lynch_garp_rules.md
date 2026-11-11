# Lynch GARP rules — weighted expansion (v2.0.0)

`lynch_garp` evaluates **24 rules**: the five original rules plus 19 deep
checks, aggregated with the shared weighted framework introduced for Graham in
v0.26.0 and Buffett in v0.27.0. The verdict is the weighted pass ratio, not an
all-pass gate.

> **Book availability.** *One Up on Wall Street* (1989) and *Beating the
> Street* (1993) were **not found** in `~/Descargas`, `~/Downloads`,
> `~/Descargados` or `~/books_analysis` (see
> `docs/books_notes/one-up-on-wall-street.md`). Every rule is a
> **public-knowledge reconstruction** with `page="public knowledge"`: no
> quote, page number or page-level paraphrase is claimed.

## Weights and score

- **weight 2 (critical)**: the three original verdict rules (PEG, growth
  consistency, debt conservatism), the deep PEG/growth/positive-earnings
  checks and positive FCF.
- **weight 1 (normal)**: the remaining valuation, balance-sheet, inventory
  and category-specific checks.
- **weight 0 (informational)**: none in this methodology.
- `weighted_score = Σ weight(passed) / Σ weight(evaluable)`.
- Verdict: **BUY ≥ 0.85**, **WATCH 0.70–0.85**, **HOLD 0.50–0.70**,
  **AVOID < 0.50**. More than **30%** of the weighted rules missing data
  returns `INSUFFICIENT_DATA`.
- The legacy `WATCH` outcome counts as **not passed** (conservative), `FAIL`
  as not passed and `INSUFFICIENT_DATA` as missing (`passed=None`).

## The 24 rules

### Legacy rules (converted to weighted results)

| # | Rule id | Category | W | Condition | Source |
|---|---|---|---:|---|---|
| 1 | `lynch_garp.rule_1_peg` | legacy | 2 | PEG ≤ 1.0 (WATCH ≤ 1.5) | public knowledge |
| 2 | `lynch_garp.rule_2_growth_consistency` | legacy | 2 | EPS grew in ≥ 7 of 10 years | public knowledge |
| 3 | `lynch_garp.rule_3_debt_conservatism` | legacy | 2 | debt ≤ 2× net income (WATCH ≤ 4×) | public knowledge |
| 4 | `lynch_garp.rule_4_inventory_vs_sales` | legacy | 1 | inventory not growing > 1.5× sales (no inventory = WATCH) | public knowledge |
| 5 | `lynch_garp.rule_5_dividend_adjusted_peg` | legacy | 1 | PEGY ≤ 1.0 (only dividend payers) | public knowledge |

### Deep checks

| # | Rule id | Category | W | Condition | Source |
|---|---|---|---:|---|---|
| 6 | `lynch.deep_peg_below_1` | core_garp | 2 | PEG ≤ 1 (P/E ÷ earnings CAGR) | public knowledge |
| 7 | `lynch.deep_pe_below_30` | core_garp | 1 | P/E < 30 | public knowledge |
| 8 | `lynch.deep_earnings_growth_above_10` | core_garp | 2 | earnings CAGR > 10% | public knowledge |
| 9 | `lynch.deep_positive_earnings_5y` | core_garp | 2 | positive earnings in every available year of the last 5 | public knowledge |
| 10 | `lynch.deep_revenue_growth_positive_5y` | core_garp | 1 | revenue grew in every available YoY period (up to 5y) | public knowledge |
| 11 | `lynch.deep_debt_equity_below_0_8` | financial_health | 1 | total debt / book equity < 0.8 | public knowledge |
| 12 | `lynch.deep_current_ratio_1_5` | financial_health | 1 | current ratio > 1.5 | public knowledge |
| 13 | `lynch.deep_fcf_positive` | financial_health | 2 | OCF − capex > 0 | public knowledge |
| 14 | `lynch.deep_inventory_vs_revenue` | financial_health | 1 | inventory growth ≤ revenue growth (no inventory passes with a note) | public knowledge |
| 15 | `lynch.deep_cash_vs_debt` | financial_health | 1 | cash > 0.5 × total debt | public knowledge |
| 16 | `lynch.deep_pb_below_3` | valuation | 1 | market cap / book equity < 3 | public knowledge |
| 17 | `lynch.deep_pe_below_own_5y_average` | valuation | 1 | P/E below its own five-year average (constant-price proxy) | public knowledge |
| 18 | `lynch.deep_slow_grower_dividend` | category_specific | 1 | slow grower paid a dividend in ≥ 4 of 5 years | public knowledge |
| 19 | `lynch.deep_fast_grower_profile` | category_specific | 1 | fast grower: revenue CAGR 20–25% **and** PEG < 0.5 | public knowledge |
| 20 | `lynch.deep_stalwart_profile` | category_specific | 1 | stalwart: revenue CAGR 10–12% **and** P/E < 15 | public knowledge |
| 21 | `lynch.deep_slow_grower_income` | category_specific | 1 | slow grower: yield > 5% **and** payout < 80% | public knowledge |
| 22 | `lynch.deep_cyclical_position` | category_specific | 1 | cyclical: no inventory build **and** P/E ≤ 15 | public knowledge |
| 23 | `lynch.deep_turnaround_progress` | category_specific | 1 | turnaround: debt down YoY **and** FCF > 0 | public knowledge |
| 24 | `lynch.deep_asset_play_discount` | category_specific | 1 | asset play: P/B < 1 **and** tangible assets ≥ 50% of market cap | public knowledge |

## Lynch category logic

The six categories are unchanged (v1.2.0 behaviour). Precedence, first match
wins: **Turnaround > Fast Grower > Cyclical > Asset Play > Stalwart > Slow
Grower > UNKNOWN**.

| Category | Detection (unchanged) |
|---|---|
| Turnaround | ≥ 2 loss years in the last 5 and the latest earnings improve |
| Fast Grower | revenue CAGR ≥ 20%, positive EPS in ≥ 4 of 5 years, positive net margin (no size gate) |
| Cyclical | cyclical sector keyword **and** 10y earnings volatility (stdev/|mean|) > 0.5 |
| Asset Play | market cap / book < 0.7 without fast-grower growth |
| Stalwart | revenue CAGR 8–20%, market cap ≥ $10B, positive earnings in ≥ 4 of 5 |
| Slow Grower | revenue CAGR 0–8%, dividend paid all 5 years, market cap ≥ $10B |
| UNKNOWN | none of the above; only the generic rules apply |

The category is recorded as `metrics["lynch_category"]` and
`metrics["lynch_category_label"]`. Rule 1 keeps its category substitution
(`dividend_stability` for slow growers, `price_to_book` for asset plays,
`turnaround_peg` for turnarounds) and `metrics["rule_1_criterion"]` names it.

**Category-specific scoring.** Only the rules for the ticker's own category
enter the weighted denominator. The other five stay visible as `N/A` but are
excluded: otherwise five inapplicable weight-1 rules would push every company
over the 30% missing-weight guard.

## Approximations and known limitations

- **P/E versus its own five-year average** uses a constant-price proxy: FDB
  rows carry a fiscal year but no period-end date, and the batch pipeline
  fetches no point-in-time price history. The rule compares the current P/E
  with the P/E implied by each historical year's EPS at today's price, so it
  isolates the earnings trend rather than the historical multiple.
- The growth rate is a geometric CAGR over the available profitable years;
  its precision depends on the data span.
- The methodology is written for product companies; banks and insurers stay
  `N/A` (the shared company-type guard). REITs are evaluated and flagged
  externally (`flags={"reit"}`).
- Rule 3 uses total debt when long-term debt is not reported (stricter than
  the book's comparison).
- No rule claims page-level fidelity: the books were unavailable.

## Deferred rules

- **Point-in-time P/E history** (true historical multiples) — needs dated
  prices per fiscal year and a batch-safe adapter.
- **Story/qualitative checks** (what the company does, insider buying, store
  visits, "the story") — not measurable from filings.
- **Multi-year inventory trend** beyond the latest YoY comparison.
- **Category-specific follow-through** such as turnaround management quality
  and asset-play appraisal of individual hidden assets.

## Measured distribution (SP500, 2026-11-11)

Base verdicts from the one-pass evaluation of 500 SP500 tickers (tiering is a
separate cross-sectional step: `vi rank --by lynch_garp`).

| Verdict | Count |
|---|---:|
| STRONG_BUY / BUY / WEAK_BUY (base) | 1 / 0 / 0 |
| WATCH | 21 |
| HOLD | 107 |
| AVOID | 264 |
| N/A (banks/insurers) | 71 |
| INSUFFICIENT_DATA | 36 |

Category-specific rules are filtered out of the denominator when they do not apply to the ticker’s Lynch category.
