# Methodology expansion — consolidated summary (v0.32.0)

All eight book methodologies now use the same framework introduced for Graham
in v0.26.0:

- explicit rules with a category, a weight (2 critical, 1 normal, 0
  informational) and a source;
- weighted score `Σ passed weight / Σ evaluable weight`;
- verdict thresholds **BUY ≥ 0.85, WATCH ≥ 0.70, HOLD ≥ 0.50, else AVOID**;
- more than **30%** of the weighted rules missing → `INSUFFICIENT_DATA`;
- the base verdict feeds the v0.24 demote-only tiers;
- banks/insurers keep `N/A`; REITs are scored with a `[REIT]` badge.

## Rule counts and book references

| Methodology | Rules | Reference book | Available? | Notes |
|---|---:|---|---|---|
| `graham` | 22 | *The Intelligent Investor* (1973) | yes | ch. 14 criteria + deep extensions; NCAV cites *Security Analysis* |
| `graham_dodd` | 26 | *Security Analysis* (1934) | yes | net-net, balance sheet, EPV, asset value, margin of safety |
| `buffett_classic` | 20 | *The Warren Buffett Way* / letters | **no** | public-knowledge reconstruction; source audit in v0.29.0 |
| `buffett_clark` | 23 | *Warren Buffett and the Interpretation of Financial Statements* (2001) | yes | DCA, owner earnings, valuation, growth |
| `fisher_quantitative_subset` | 17 | *Common Stocks and Uncommon Profits* (1958) | yes | quantitative subset; 11 qualitative points deferred |
| `lynch_garp` | 24 | *One Up on Wall Street* / *Beating the Street* | **no** | public knowledge; six-category classifier preserved |
| `marks` | 17 | *The Most Important Thing* (2011) | **no** | public knowledge; company-level proxies only |
| `greenblatt` | 15 | *The Little Book That Beats the Market* (2005) | **no** | public knowledge overlay around the existing ranking |

The curated notes and the exact citation policy live in
`docs/books_notes/README.md`.

## Measured distribution (SP500, one-pass base verdicts, 2026-11-11)

These are **base** verdicts from evaluating all 500 tickers once. The
`STRONG_BUY` / `BUY` / `WEAK_BUY` split is a separate cross-sectional step
(`vi rank --by <methodology>`).

| Methodology | BUY | WATCH | HOLD | AVOID | N/A | INSUFFICIENT |
|---|---:|---:|---:|---:|---:|---:|
| `graham` | 0 | 3 | 95 | 310 | 71 | 21 |
| `graham_dodd` | 0 | 0 | 22 | 363 | 71 | 44 |
| `buffett_classic` | 9 | 62 | 178 | 152 | 71 | 28 |
| `buffett_clark` | 4 | 48 | 109 | 173 | 71 | 95 |
| `fisher_quantitative_subset` | 12 | 77 | 142 | 160 | 71 | 38 |
| `lynch_garp` | 1 | 21 | 107 | 264 | 71 | 36 |
| `marks` | 3 | 54 | 185 | 170 | 71 | 17 |
| `greenblatt` | 3 | 4 | 187 | 63 | 99 | 144 |

Reading notes:

- **Graham & Dodd is deliberately the strictest** (0 positive): the net-net
  and 2/3 NCAV tests rarely trigger on modern large caps. Do not relax it.
- **Buffett/Clark's 95 INSUFFICIENT** readings are data coverage (capex, D&A
  and 10-year history), not an applicability guard.
- **Greenblatt's N/A (99)** includes the 71 banks/insurers plus 28 tickers
  outside the SP500 ranking file; its INSUFFICIENT (144) is ranking-file
  coverage and requires the weekly refresh.
- **Marks** is the most qualitative methodology; only company-level proxies
  are measured (no market-temperature or credit-cycle signal).
- The 71 `N/A` in every row except Greenblatt are the banks/insurers that
  abstain by design.

## Backtests (PoC, 5-year window, 100-ticker sample)

The period covered is 2021–2024 (four complete years; 2025 is YTD and excluded from CAGR/Sharpe). The harness is `vi backtest --methodology <name> --years N --limit M`.
Greenblatt is excluded by design (its ranking file is not point-in-time, so a
historical backtest would be look-ahead). The long-run Graham/Buffett
baselines remain: Graham 4.2% CAGR / 0.50 Sharpe (v0.26.0, 5y/400); Buffett
23.8% CAGR / 1.53 Sharpe (v0.27.1, 10y/400).

| Methodology | CAGR | Sharpe | Opportunity set | Evaluated |
|---|---:|---:|---:|---:|
| `buffett_clark` | -2.6% | -0.58 | 8.7% | 100 |
| `lynch_garp` | 0.9% | 0.20 | 8.7% | 100 |
| `graham_dodd` | 0.0% (all cash) | — | 8.7% | 100 |
| `fisher_quantitative_subset` | 16.1% | 0.78 | 8.7% | 100 |
| `marks` | 23.4% | 0.89 | 8.7% | 100 |
| `greenblatt` | — | — | — | excluded (look-ahead) |

The PoC has no dividends, transaction costs or survivorship correction; treat
the numbers as indicative.

## Deferred rules and data gaps

| Methodology | Deferred | Reason |
|---|---|---|
| `graham` | utility-specific history, full 20-year dividends | FDB history ~16 years; utility branch implemented with total debt |
| `graham_dodd` | cash+receivables net-net, inventory write-downs, dynamic EPV/WACC | no receivables/inventory detail or policy WACC |
| `buffett_classic` | exact maintenance capex, insider ownership, qualitative moat | not in FDB |
| `buffett_clark` | brand/consumer-monopoly evidence, maintenance capex, REIT FFO | qualitative / not in FDB |
| `fisher` | 11 qualitative/scuttlebutt points | require research beyond filings |
| `lynch` | point-in-time P/E history, qualitative story, multi-year inventory trend | no point-in-time prices in batch |
| `marks` | market temperature, credit cycle, second-level thinking | macro/qualitative |
| `greenblatt` | sector-relative ROC, percentile-aware rank cutoffs | ranking payload limitation |

## Specialized analyzers (v0.33+)

The bank and REIT lenses remain the next structural improvement: banks stay
`N/A` on the industrial scorecard, and REITs are scored with industrial rules
plus a `[REIT]` badge. See `docs/backlog.md` → "Specialized analyzers".
