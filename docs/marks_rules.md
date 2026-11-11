# Marks rules — weighted expansion (v2.0.0)

`marks` evaluates **17 rules**: the four original measurable rules plus 13
deep checks, aggregated with the shared weighted framework (v0.26/v0.27
pattern). The verdict is the weighted pass ratio, with one documented
survival override.

> **Book availability.** *The Most Important Thing* (2011) was **not found**
> in `~/Descargas`, `~/Downloads`, `~/Descargados` or `~/books_analysis` (see
> `docs/books_notes/the-most-important-thing.md`). Every rule is a
> **public-knowledge reconstruction** with `page="public knowledge"`: no
> quote, page number or page-level paraphrase is claimed.

## Weights and score

- **weight 2 (critical)**: resilience, margin of safety, quality persistence,
  DCF margin of safety, ROIC, five-year FCF and no dilution.
- **weight 1 (normal)**: the remaining valuation, quality, risk-control and
  cycle checks.
- **weight 0 (informational)**: none in this methodology.
- `weighted_score = Σ weight(passed) / Σ weight(evaluable)`.
- Verdict: **BUY ≥ 0.85**, **WATCH 0.70–0.85**, **HOLD 0.50–0.70**,
  **AVOID < 0.50**. More than **30%** of the weighted rules missing data
  returns `INSUFFICIENT_DATA`.
- **Hard risk gate:** net debt/EBITDA > 4× forces `AVOID` even when the
  weighted ratio is comfortable. The score still shows the weighted ratio;
  the red flag explains the override. Survival comes before the score.

## The 17 rules

### Legacy rules (converted to weighted results)

| # | Rule id | Category | W | Condition | Source |
|---|---|---|---:|---|---|
| 1 | `marks.rule_1_cycle_position` | cycle_position | 1 | not at a peak (margin/ROIC vs own history) | public knowledge |
| 2 | `marks.rule_2_resilience` | risk_control | 2 | net debt/EBITDA ≤ 2.5, coverage ≥ 4×, FCF > 0 | public knowledge |
| 3 | `marks.rule_3_margin_of_safety` | valuation | 2 | FCF yield ≥ 4% **or** EV/EBIT ≤ 12 | public knowledge |
| 4 | `marks.rule_4_quality_persistence` | quality | 2 | 5y average ROIC ≥ 10%, positive in ≥ 4 of 5 | public knowledge |

### Deep checks

| # | Rule id | Category | W | Condition | Source |
|---|---|---|---:|---|---|
| 5 | `marks.deep_price_below_intrinsic_20` | valuation | 2 | DCF intrinsic value ≥ 1.20 × price | public knowledge (not-from-canon DCF) |
| 6 | `marks.deep_pe_below_own_5y_average` | valuation | 1 | P/E below its own 5y average (constant-price proxy) | public knowledge |
| 7 | `marks.deep_pb_below_2` | valuation | 1 | P/B < 2 | public knowledge |
| 8 | `marks.deep_earnings_yield_5` | valuation | 1 | 3y-average EPS / price ≥ 5% | public knowledge |
| 9 | `marks.deep_roic_15` | quality | 2 | EBIT / (debt + equity − cash) ≥ 15% | public knowledge |
| 10 | `marks.deep_fcf_positive_5y` | quality | 2 | FCF > 0 in every available year of the last 5 | public knowledge |
| 11 | `marks.deep_margin_stability` | quality | 1 | operating-margin stdev < 5pp over 5y | public knowledge |
| 12 | `marks.deep_revenue_growth_positive` | quality | 1 | revenue CAGR > 0 | public knowledge |
| 13 | `marks.deep_low_debt` | risk_control | 1 | net debt/EBITDA ≤ 2.5× | public knowledge |
| 14 | `marks.deep_interest_coverage_10` | risk_control | 1 | EBIT / interest ≥ 10× (debt-free passes) | public knowledge |
| 15 | `marks.deep_no_dilution_5y` | risk_control | 2 | split-adjusted shares flat or lower over 5y | public knowledge |
| 16 | `marks.deep_pe_percentile_10y` | cycle_position | 1 | P/E ≤ 80th percentile of its own 10y history | public knowledge |
| 17 | `marks.deep_not_peak_margin` | cycle_position | 1 | operating margin not > 3pp above its own prior mean | public knowledge |

## Approximations and known limitations

- **P/E versus its own history** (rules 6 and 16) uses a constant-price
  proxy: FDB rows carry a fiscal year but no period-end date, and the batch
  pipeline fetches no point-in-time price history. The current P/E is
  compared with the multiples implied by each historical year's EPS at
  today's price. The detail string says so.
- **ROIC** is pre-tax EBIT / (debt + equity − cash), matching the
  methodology's existing `roic` metric; a NOPAT definition would produce two
  different ROICs in the same result.
- The **DCF rule reuses the not-from-canon two-stage DCF** and degrades to
  `N/A` when the price service cannot provide its inputs. It is never
  fabricated.
- **Cycle position is company-level only.** A high reading means "above its
  own trend", not "the market is late-cycle".
- Financials abstain (leverage, coverage and EV/EBIT are not comparable for
  banks and insurers). At least 3 fiscal years are required for a cycle
  reading.
- No rule claims page-level fidelity: the book was unavailable.

## Deferred rules

- **Market temperature** — the market-wide cycle position (credit spreads,
  issuance, valuations across the market) needs macro data this system does
  not collect.
- **Credit cycle** — availability and terms of credit, default rates.
- **Second-level thinking** — what the consensus believes versus what the
  price implies; not measurable from filings.
- **The pendulum of psychology** — investor sentiment and risk appetite.
- **Distressed-debt and special-situation analysis** — outside the equity
  fundamentals pipeline.
- **True point-in-time price history** for the P/E percentile — needs a
  dated-price adapter that stays batch-safe.

## Measured distribution (SP500, 2026-11-11)

Base verdicts from the one-pass evaluation of 500 SP500 tickers (tiering is a
separate cross-sectional step: `vi rank --by marks`).

| Verdict | Count |
|---|---:|
| STRONG_BUY / BUY / WEAK_BUY (base) | 3 / 0 / 0 |
| WATCH | 54 |
| HOLD | 185 |
| AVOID | 170 |
| N/A (banks/insurers) | 71 |
| INSUFFICIENT_DATA | 17 |

Marks is the most qualitative of the eight; the measured subset is company-level only (no market-temperature or credit-cycle signal).
