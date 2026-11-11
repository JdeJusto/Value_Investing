# Buffett/Clark rules — deep expansion (v2.0.0)

`buffett_clark` implements the durable-competitive-advantage (DCA) screen of
Mary Buffett & David Clark, *Warren Buffett and the Interpretation of Financial
Statements* (2001). The seven original statement-signature rules are now
aggregated with sixteen deep checks through the weighted-rule framework
introduced for Graham in v0.26.0. The verdict is no longer an all-pass gate or
a passed/7 count.

Source labels follow `docs/books_notes/buffett-clark-financial-statements.md`:
a page is cited only when the book states the idea. ROIC, owner earnings,
book-value-per-share compounding, P/E bands and the DCF are **public-knowledge
derivations** and carry `page="public knowledge"` plus a caution naming the
approximation — the book has no valuation chapter (§9 of the notes).

## Weights and score

- **weight 2 (critical)**: ROIC (current and 5-year persistence) and the DCF
  margin of safety.
- **weight 1 (normal)**: every other rule, legacy and deep.
- **weight 0 (informational)**: none currently; the field exists for future
  qualitative rules.

`weighted_score = Σ weight(passed) / Σ weight(evaluable)`; rules that cannot be
evaluated (`passed=None`) stay in the denominator as missing weight. Weight-0
rules never enter the denominator.

- **BUY ≥ 0.85**, **WATCH 0.70–0.85**, **HOLD 0.50–0.70**, **AVOID < 0.50**.
- More than **30%** of the weighted rules missing data returns
  `INSUFFICIENT_DATA`.
- Confidence is HIGH with no missing weight, MEDIUM up to 10% missing, else LOW.
- The base verdict feeds the v0.24 demote-only tiers unchanged: a
  WATCH/HOLD/AVOID is never promoted; only a base BUY can become
  `STRONG_BUY`/`BUY`/`WEAK_BUY` relative to the universe.
- A legacy WATCH (gross margin between 20% and 40%, interest burden between 10%
  and 50%) is treated conservatively as **not passed** (`False`), never as a
  pass.

## The 23 rules

### Original statement-signature rules (7)

| # | Rule id | Category | W | Condition | Source |
|---|---|---|---:|---|---|
| 1 | `rule_1_gross_margin` | durable_advantage | 2 | gross margin ≥ 40% (≥ 20% is N/A, < 20% fails) | p. 55–56 |
| 2 | `rule_2_interest_burden` | durable_advantage | 1 | interest expense ≤ 10% of operating income (≥ 50% fails) | p. 73–74 |
| 3 | `rule_3_margin_durability` | durable_advantage | 1 | gross margin not down more than 5% over 5 years | p. 56 |
| 4 | `rule_4_debt` | durable_advantage | 1 | total debt / book equity ≤ 0.50 | p. 38, 41 |
| 5 | `rule_5_cash` | durable_advantage | 1 | cash ≥ 10% of total assets | p. 41 |
| 6 | `rule_6_capex` | durable_advantage | 1 | capex ≤ 50% of free cash flow | p. 41 |
| 7 | `rule_7_retained_earnings` | owner_earnings | 1 | retained earnings higher than the prior year | p. 34 |

### Deep checks (16)

| # | Rule id | Category | W | Condition | Source |
|---|---|---|---:|---|---|
| 8 | `deep_roic_current` | durable_advantage | 2 | ROIC ≥ 15% (latest year) | public knowledge: NOPAT / (debt + equity − cash); the book discusses ROE/ROA, not ROIC |
| 9 | `deep_roic_5y` | durable_advantage | 2 | ROIC ≥ 15% in each of the last 5 years | public knowledge: 5-year persistence quantifies the DCA durability thesis (p. 29, 56) |
| 10 | `deep_roe_15` | durable_advantage | 1 | ROE ≥ 15% | p. 34 (ROE/ROA discussion); 15% bar is an approximation |
| 11 | `deep_low_capex` | durable_advantage | 1 | capex / net income < 25% | p. 41; 25% bar is an approximation |
| 12 | `deep_predictable_earnings` | durable_advantage | 1 | stdev of yearly EPS growth < 15% (10y window, ≥ 5 years) | public knowledge: predictability proxy |
| 13 | `deep_low_debt` | durable_advantage | 1 | long-term debt / equity < 0.50 (total debt when the split is missing) | p. 38, 41; 0.50x bar is an approximation |
| 14 | `deep_gross_margin_stability` | durable_advantage | 1 | stdev of gross margin < 3pp over 5 years | p. 56; quantification of "stable or rising" |
| 15 | `deep_owner_earnings_positive` | owner_earnings | 1 | NI + D&A − capex > 0 | public knowledge: owner-earnings definition, total capex as maintenance-capex proxy |
| 16 | `deep_owner_earnings_growing` | owner_earnings | 1 | owner-earnings CAGR > 0 over 5 years | public knowledge: rising underlying value (p. 29) quantified |
| 17 | `deep_bvps_growth_10y` | owner_earnings | 1 | book value per share CAGR > 10% over 10 years | public knowledge: retained-earnings compounding (p. 34) |
| 18 | `deep_dcf_margin_of_safety_50` | valuation | 2 | price ≤ 0.50 × DCF intrinsic value | p. 34 (buy at a fair price); DCF and 50% margin are not-from-canon |
| 19 | `deep_pe_below_20` | valuation | 1 | price / 3-year average EPS ≤ 20 | public knowledge: the book has no P/E bar |
| 20 | `deep_pe_below_5y_average` | valuation | 1 | current P/E below its own fiscal-year-end 5y average | public knowledge: relative valuation from historical prices |
| 21 | `deep_revenue_cagr_5` | growth | 1 | revenue CAGR ≥ 5% over the available decade (≥ 5 years) | p. 29, 31 (10–20 year horizon); 5% bar is an approximation |
| 22 | `deep_eps_cagr_10` | growth | 1 | split-adjusted EPS CAGR ≥ 10% | public knowledge: per-share compounding proxy |
| 23 | `deep_positive_earnings_10y` | growth | 1 | every available year in the last decade profitable (≥ 5 years) | public knowledge: earnings-durability proxy |

Total weighted denominator when every rule is evaluable: **27** (8 from the
legacy rules + 19 from the deep checks).

## Data and computation notes

- ROIC uses NOPAT / (total debt + book equity − cash) with the effective tax
  rate when available, else 21%.
- Owner earnings are net income + D&A − total capex. FDB has no
  maintenance-capex line, so total capex is a conservative proxy.
- Book value per share, EPS and share counts are split-adjusted with
  `split_adjustment_factor`.
- `deep_pe_below_5y_average` calls the injected price service's
  `get_price_at_fiscal_year_end`; when the service does not expose it (the
  batch screener and backtest adapters do not) the rule is `N/A` rather than a
  failure.
- The DCF reuses the not-from-canon two-stage valuation. A missing beta or
  degenerate inputs degrade the rule to `N/A`; nothing is fabricated.

## Company-type policy

- **Banks and insurers** return `NOT_APPLICABLE` before any rule runs. The
  gross-margin, interest-burden, debt and owner-earnings rules read a
  financial's business model as weakness.
- **REITs** are evaluated and flagged `[REIT]` externally by the caller. FFO
  accounting makes net income, capex and owner earnings poor fits, so the score
  is a rough quality check, not a REIT valuation. FFO/AFFO analysis is
  deferred.
- **REIT/bank exception:** a REIT that is not caught by the company-type
  detector still runs the industrial rules; the flag is informational only.

## Deferred rules

- **Consumer-monopoly / brand evidence**: the book's qualitative core (Coca-Cola,
  See's, Moody's) needs brand-strength and pricing-power evidence that FDB does
  not carry. It is documented here rather than faked with a ratio.
- **Exact maintenance capex** for owner earnings.
- **REIT FFO/AFFO** valuation.
- **Industry-specific gross-margin bars**: the 40%/20% thresholds are
  explicitly "not infallible" in the book (p. 55); SaaS, biotech and
  distributors can structurally sit outside them.
- **A page-cited valuation method**: the book has none. The valuation block is
  deliberately labelled public knowledge.

## Known limitations

- The 10-year rules need a long history. Younger filers lose coverage and can
  read `INSUFFICIENT_DATA` because missing weight crosses 30%.
- `deep_low_debt` and the legacy `rule_4_debt` overlap on purpose: the debt
  signal is deliberately double-weighted (legacy total-debt test + deep
  long-term-debt test).
- The interest-burden examples are US airlines/tires from 2001.
- The historical-P/E rule depends on a live price history; in batch contexts it
  is often `N/A`, which slightly reduces coverage but not the direction of the
  score.

## Measured distribution (SP500, 2026-11-11)

Base verdicts from the one-pass evaluation of 500 SP500 tickers (tiering is a
separate cross-sectional step: `vi rank --by buffett_clark`).

| Verdict | Count |
|---|---:|
| STRONG_BUY / BUY / WEAK_BUY (base) | 4 / 0 / 0 |
| WATCH | 48 |
| HOLD | 109 |
| AVOID | 173 |
| N/A (banks/insurers) | 71 |
| INSUFFICIENT_DATA | 95 |

The 95 INSUFFICIENT readings are data coverage: the DCA/owner-earnings rules need capex, D&A and 10-year history that some filers do not carry.
