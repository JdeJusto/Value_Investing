# Fisher rules — quantitative expansion (v2.0.0)

`fisher_quantitative_subset` is the quantitative edge of Philip Fisher's fifteen
points from *Common Stocks and Uncommon Profits* (1958). It is deliberately
**not** named `fisher`: eleven of the fifteen points (sales organization, labor
relations, executive relations, management depth, industry-specific factors,
long-range outlook, candor, integrity and the scuttlebutt method itself) need
qualitative research this system does not have. The four original quantitative
points (3, 5, 10, 13) are now aggregated with thirteen deep checks through the
weighted-rule framework introduced for Graham in v0.26.0.

Source labels follow `docs/books_notes/common-stocks-and-uncommon-profits.md`.
A page is cited only when the book states the idea; a numeric threshold Fisher
never set is labelled **public knowledge** with a caution naming the proxy. The
R&D/sales rule is the clearest example: Fisher calls the ratio a "crude
yardstick" (p. 54–55), so it is informational (weight 0).

## Weights and score

- **weight 2 (critical)**: latest revenue growth (the growth thesis, point 1)
  and positive free cash flow (growth must be self-funding, point 13).
- **weight 1 (normal)**: every other scored rule.
- **weight 0 (informational)**: R&D intensity and R&D growth pace. They are
  shown but never enter the score.

`weighted_score = Σ weight(passed) / Σ weight(evaluable)`; rules that cannot be
evaluated (`passed=None`) stay in the denominator as missing weight. Weight-0
rules never enter the denominator.

- **BUY ≥ 0.85**, **WATCH 0.70–0.85**, **HOLD 0.50–0.70**, **AVOID < 0.50**.
- More than **30%** of the weighted rules missing data returns
  `INSUFFICIENT_DATA`.
- Confidence is HIGH with no missing weight, MEDIUM up to 10% missing, else LOW.
- The base verdict feeds the v0.24 demote-only tiers unchanged.
- Legacy statuses convert conservatively: **PASS → passed**, **WATCH and
  FAIL → not passed**, **INSUFFICIENT_DATA → not evaluable**, **NOT_APPLICABLE
  → excluded**. WATCH is not a pass because the subset has no scuttlebutt to
  justify a near-miss.

## The 17 rules

### Original quantifiable Fisher points (4)

| # | Rule id | Category | W | Condition | Source |
|---|---|---|---:|---|---|
| 1 | `rule_1_rnd_intensity` | growth_potential | 1 | R&D / sales above the sector-aware PASS bar (innovation-led 8%, industrials 4%, low-R&D 2%; unknown 8%) | p. 54–55 (point 3) |
| 2 | `rule_2_profit_margin_quality` | profitability | 2 | net margin ≥ 10% and operating margin ≥ 15%; net < 5% fails | p. 63–64 (point 5) |
| 3 | `rule_3_cost_control_stability` | cost_efficiency | 1 | stdev of gross margin < 3pp over 5 years (WATCH < 5pp) | p. 69 (point 10) |
| 4 | `rule_4_share_dilution` | capital_discipline | 2 | share count flat or lower over 10 years (split-adjusted); +10% WATCH, above fails | p. 75 (point 13) |

### Deep checks (13)

| # | Rule id | Category | W | Condition | Source |
|---|---|---|---:|---|---|
| 5 | `deep_revenue_growth_15` | growth_potential | 2 | latest year-over-year revenue growth > 15% | p. 47; the book asks for multi-year sales potential, the 15% annual bar is a proxy |
| 6 | `deep_revenue_growth_consistent_5y` | growth_potential | 1 | revenue up in ≥ 4 of the last 5 years **and** 5y CAGR ≥ 10% | p. 47–48; 4/5-years and 10% bars are proxies |
| 7 | `deep_rnd_intensity` | growth_potential | 0 | R&D / sales above the sector-aware PASS bar (informational) | p. 54–55; Fisher calls the ratio a "crude yardstick" |
| 8 | `deep_net_margin_15` | profitability | 1 | net margin > 15% | p. 63–64; 15% net bar is a proxy for a "worthwhile" operating margin |
| 9 | `deep_margin_improvement` | profitability | 1 | latest net margin > oldest margin in the 5y window by more than 0.5pp | p. 63 (point 6, margin direction); 0.5pp floor is an approximation |
| 10 | `deep_gross_margin_40` | profitability | 1 | gross margin > 40% | public knowledge: gross-margin level as a quality proxy; point 5 is operating margin |
| 11 | `deep_sga_ratio_stable` | cost_efficiency | 1 | stdev of SG&A / revenue < 2pp over 5 years | p. 69 (point 10); SG&A stability is an accounting proxy |
| 12 | `deep_operating_leverage` | cost_efficiency | 1 | operating-income CAGR > revenue CAGR over the available window (≥ 3 years) | public knowledge: operating leverage is a cost-control proxy |
| 13 | `deep_no_dilution_5y` | capital_discipline | 1 | split-adjusted share count change ≤ +2% over 5 years | p. 75 (point 13) |
| 14 | `deep_buybacks_3_of_5y` | capital_discipline | 1 | share count fell or stock was repurchased in ≥ 3 of the last 5 periods | p. 75 (point 13, observable mirror) |
| 15 | `deep_fcf_positive_5y` | capital_discipline | 2 | free cash flow > 0 in every available year of the last 5 | public knowledge: point 13 implies self-funding but sets no FCF bar |
| 16 | `deep_roic_15` | capital_discipline | 1 | ROIC > 15% (latest year) | public knowledge: NOPAT / (debt + equity − cash) |
| 17 | `deep_rnd_growth_pace` | growth_potential | 0 | R&D CAGR ≥ revenue CAGR over 3 years (informational) | public knowledge: spend growth cannot measure research effectiveness |

Total weighted denominator when every rule is evaluable: **19** (6 from the
legacy rules + 13 from the deep checks).

## Data and computation notes

- FCF = direct free cash flow, else operating cash flow − |capex|.
- Split-adjusted share counts use `split_adjustment_factor`; the 10-year legacy
  rule looks up the exact fiscal year ten years back, while the 5-year deep rule
  uses the newest six rows.
- Gross-margin stability uses the sample standard deviation over exactly five
  years; the buffett_clark methodology uses population stdev — the two books
  are allowed to differ.
- The R&D/sales tiers are shared between the legacy rule and the deep
  informational rule (`rnd_thresholds_for` in `deep_checks.py`).
- No price, no DCF and no market multiple is consulted: Fisher is a quality
  screen, not a valuation method.

## Company-type policy

- **Banks and insurers** return `NOT_APPLICABLE` before any rule runs: Fisher's
  points assume inventory, gross margin and R&D.
- **REITs** run the screen; gross margin is `NOT_APPLICABLE` when the business
  model has no such line, and the REIT flag is attached externally. FFO-based
  analysis is deferred.
- If fewer than half of the four original Fisher points apply, the whole
  methodology returns `NOT_APPLICABLE` (preserved from v1.x). Rules whose line
  item does not exist in the business model (R&D in an E&P) are excluded from
  the weighted denominator; data gaps are not.

## Deferred rules (the eleven qualitative points)

| Point | Topic | Why deferred |
|---|---|---|
| 1 (qualitative part) | Multi-year market potential / new-market determination | Needs product and market data outside FDB |
| 2 | Management determination to develop new markets | Qualitative |
| 4 | Above-average sales organization | Qualitative |
| 7 | Outstanding labor and personnel relations | Needs turnover/strike data |
| 8 | Outstanding executive relations | Qualitative |
| 9 | Management depth / succession | Needs governance data |
| 11 | Industry-specific factors (patents, credit, real estate skill) | Industry-specific data outside FDB |
| 12 | Long-range vs short-range profit outlook | Needs forward guidance/transcripts |
| 13 (qualitative part) | Whether growth needs equity that cancels the shareholder's benefit | The 10y/5y dilution rules are the observable proxy |
| 14 | Management candor | Needs transcripts and disclosure history |
| 15 | Management integrity | Needs governance/related-party data |

The scuttlebutt method itself (competitors, suppliers, customers, ex-employees)
is the engine behind points 4 and 7–15 and is out of scope by design
(`docs/methodology_decisions.md`, decision 1).

## Known limitations

- The book sets **no numeric thresholds at all**; every bar in the deep table is
  a documented proxy, not a Fisher criterion.
- Fisher explicitly refuses a valuation discipline (p. 111). This methodology
  therefore never scores price, and a high-multiple grower is not penalized.
- The growth rules reward a single strong year (weight 2) even when the 5-year
  record is uneven; the consistent-growth rule balances that only partially.
- The SG&A rule needs a reported SG&A line; filers that bury it in cost of sales
  read `N/A`.

## Measured distribution (SP500, 2026-11-11)

Base verdicts from the one-pass evaluation of 500 SP500 tickers (tiering is a
separate cross-sectional step: `vi rank --by fisher`).

| Verdict | Count |
|---|---:|
| STRONG_BUY / BUY / WEAK_BUY (base) | 12 / 0 / 0 |
| WATCH | 77 |
| HOLD | 142 |
| AVOID | 160 |
| N/A (banks/insurers) | 71 |
| INSUFFICIENT_DATA | 38 |

The R&D rules are N/A for sectors that do not report R&D; the weighted score excludes them from the denominator.
