# Buffett rules — deep expansion (v0.27.0)

`buffett_classic` evaluates **20 explicit rules** across six categories and
aggregates them with the weighted score introduced for Graham in v0.26.0. The
wrapper no longer delegates the verdict to the 4-pillar engine; the pillars
remain useful context but every scored criterion is now visible, sourced and
weighted.

## Weights and score

- **weight 2 (critical)**: ROIC (current and 10-year persistence), positive
  FCF (5y), net margin ≥ 10%, no dilution and the DCF margin of safety.
- **weight 1 (normal)**: the remaining moat, balance-sheet, earnings-quality,
  capital-allocation and valuation checks.
- **weight 0 (informational)**: insider ownership and R&D intensity; they are
  shown but never scored.
- `weighted_score = Σ weight(passed) / Σ weight(evaluable)`; `N/A` rules are
  excluded from the denominator and weight-0 rules never enter it.
- Verdict: **BUY ≥ 0.85**, **WATCH 0.70–0.85**, **HOLD 0.50–0.70**,
  **AVOID < 0.50**. More than **30%** of the weighted rules missing data
  returns `INSUFFICIENT_DATA`.
- The base verdict feeds the v0.24 demote-only tiers unchanged: a
  WATCH/HOLD/AVOID is never promoted; only a base BUY can become
  `STRONG_BUY`/`BUY`/`WEAK_BUY` relative to the universe.

## The 20 rules

| # | Rule id | Category | W | Condition | Source |
|---|---|---|---:|---|---|
| 1 | `roic_current` | moat | 2 | ROIC ≥ 15% (latest year) | public: NOPAT / (debt + equity − cash) |
| 2 | `roic_10y_persistence` | moat | 2 | ROIC ≥ 15% in every available year of the last 10 | 1987 letter (economic goodwill) |
| 3 | `gross_margin_stability` | moat | 1 | stdev of gross margin < 5pp over 5y | public: pricing-power proxy |
| 4 | `operating_margin_trend` | moat | 1 | latest operating margin not >2pp below the 5y base | public: moat-erosion check |
| 5 | `pricing_power` | moat | 1 | revenue CAGR ≥ 3% without a gross-margin drop >2pp | public: inflation pass-through |
| 6 | `debt_equity_below_1` | financial_strength | 1 | total debt / book equity < 1 | public: conservative leverage |
| 7 | `interest_coverage_10` | financial_strength | 1 | EBIT / interest ≥ 10x (debt-free passes) | 1990 letter |
| 8 | `current_ratio_1_5` | financial_strength | 1 | current ratio ≥ 1.5 | public: liquidity |
| 9 | `fcf_positive_5y` | financial_strength | 2 | FCF > 0 every available year of the last 5 | 1986 letter (owner earnings) |
| 10 | `net_margin_10` | earnings_quality | 2 | net margin ≥ 10% | 1979/1987 letters |
| 11 | `fcf_conversion_80` | earnings_quality | 1 | FCF / net income ≥ 80% | public: cash conversion |
| 12 | `earnings_consistency` | earnings_quality | 1 | stdev of yearly EPS growth < 20% (5y) | public: predictability |
| 13 | `owner_earnings_positive` | earnings_quality | 1 | NI + D&A − capex > 0 (proxy) | 1986 letter (approximation) |
| 14 | `no_dilution_5y` | capital_allocation | 2 | split-adjusted shares flat or lower over 5y | 1984/1996 letters |
| 15 | `buybacks_3_of_5y` | capital_allocation | 1 | share count fell or stock repurchased in ≥3 periods | 2011 letter |
| 16 | `dcf_margin_of_safety_20` | valuation | 2 | DCF intrinsic value ≥ 1.20 × price (margin ≥ 20%) | public: two-stage DCF, not-from-canon |
| 17 | `earnings_yield_5` | valuation | 1 | 3y-average EPS / price ≥ 5% | 1977 letter |
| 18 | `pe_below_20` | valuation | 1 | price / 3y-average EPS ≤ 20 | public (Buffett tolerates a higher multiple than Graham) |
| 19 | `insider_ownership` | management | 0 | informational; not in FDB | public: requires a supplementary source |
| 20 | `rd_ratio_3` | management | 0 | R&D / revenue ≥ 3% (informational, N/A if unreported) | public: sector-dependent |

## Measured distribution (SP500, 2026-11-10)

`v0.27.0` shipped with the DCF rule silently `N/A` in batch; `v0.27.1` fixes
the adapter and evaluates it. The corrected distribution is stricter:

| Verdict | v0.27.0 (DCF N/A) | v0.27.1 (DCF active) |
|---|---:|---:|
| STRONG_BUY | 12 | 8 |
| BUY | 9 | 0 |
| WEAK_BUY | 0 | 0 |
| WATCH | 73 | 63 |
| HOLD | 150 | 177 |
| AVOID | 148 | 153 |
| N/A (banks/insurers) | 71 | 71 |
| INSUFFICIENT_DATA | 37 | 28 |

**8 positive signals (1.6%)**, all STRONG_BUY: ZTS (95.83), LULU (95.65), NVR
(95.0), DECK (91.3), CTSH (90.91), ADBE (87.5), JKHY (86.96) and DHI
(86.36). The demote-only tier split puts all eight in the top percentile of
the universe, so no base BUY is left for the BUY tier.

The fix changed **84 verdicts** (75 downgrades, mostly BUY→WATCH and
WATCH→HOLD) and moved **9 unique tickers out of INSUFFICIENT_DATA**; across
the backtest's 2016–2024 signal-years it removed ~142 INSUFFICIENT rows. The
DCF is a critical rule (weight 2), and most quality names fail it in this
market, which is why the corrected score is tighter. There is no forced BUY.

REITs (28) with the DCF active: **0 positive, 6 HOLD, 17 AVOID and 5
INSUFFICIENT_DATA** (was 2/12/14). Banks (71) still return N/A before any
rule runs.

AAPL lands in WATCH (73.91, single-company analysis): the moat, FCF and
capital-allocation blocks pass; the valuation block fails at ~52× earnings.
KO lands in HOLD (58.33): 1.27× debt/equity, 8.3× interest coverage, 40% FCF
conversion and ~36× earnings fail, so calling it WATCH would require forcing
the verdict, which the policy forbids.

Batch rankings, the screener and the backtest now expose `get_beta` on their
price adapters, so the DCF rule is **evaluated** in every context instead of
degrading to `N/A` (v0.27.1). Rankings/screener pass the Yahoo market beta;
the backtest passes `None` on purpose (no point-in-time beta exists, so the
DCF applies its documented 1.0 fallback and the simulation stays free of
look-ahead). Single-company `vi analyze-buffett-classic` uses the Yahoo beta.

### Backtest (10 years, 400-ticker sample)

`vi backtest --methodology buffett_classic --years 10 --limit 400`
(2015–2024, 392 evaluated, 3,338 evaluable signal-years):

| Metric | v0.27.1 (DCF active) | v0.27.0 (DCF N/A) |
|---|---:|---:|
| Portfolio CAGR | **23.8%** | 13.8% |
| Portfolio Sharpe | **1.53** | 1.09 |
| Opportunity set CAGR | 15.2% | 15.2% |
| SPY CAGR | 14.7% | 14.7% |
| Alpha vs opportunity set | +8.6% | -1.4% |

Positive signals per complete year drop to 5–9 (all STRONG), with no WEAK
tier because the demote-only split assigns the top base BUYs to STRONG/BUY.
The activated DCF rule makes the basket smaller and more valuation-driven;
over this decade that concentration beat the equal-weighted opportunity set
by 8.6pp and SPY by 9.0pp. The result is a PoC (no dividends, costs or
survivorship correction), so treat the magnitude as indicative.

## Known limitations and deferred rules

Implemented with the columns in `NormalizedFinancials` / `core_financials`.
The following stay in `docs/backlog.md`:

- **Exact maintenance capex**: owner earnings use total capex as a proxy.
- **Insider ownership**: not in FDB (informational rule, weight 0).
- **Qualitative moat** (brand, switching costs, regulation): needs a
  supplementary source.
- **DCF with a policy-consistent discount rate**: the rule reuses the
  not-from-canon two-stage DCF. A missing beta falls back to 1.0 (documented
  in the DCF), so batch contexts evaluate the rule instead of skipping it;
  the rule is `N/A` only when the DCF's own inputs are missing.
- **REIT-specific lens**: REITs are scored with industrial rules and flagged
  `[REIT]`; FFO/AFFO analysis is a v0.28+ backlog item.

## Notes on the measured outcome

- The rules are deliberately strict: a quality name trading at a high multiple
  (e.g. KO at ~36× earnings, 2.8% earnings yield, 1.27× debt/equity) lands in
  HOLD, not WATCH. That is the intended "no forced BUY" behaviour.
- AAPL lands in WATCH (73.9): the moat, FCF and capital-allocation blocks pass;
  the valuation block fails at 52× earnings. The old 4-pillar engine called it
  BUY (77/100) because it barely looked at the price.
- Banks and insurers return N/A before any rule runs (unchanged from v0.23.0).
