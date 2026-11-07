# `INSUFFICIENT_DATA` and absurd chart values — diagnostic report

- **Date:** 2026-11-06
- **Baseline:** Value Investing v0.20.2 (`834b502`), Financial-DataBase 0.2.1
- **Sample:** the 30 audit tickers from `docs/usage_notes.md`
- **Mode:** read-only diagnosis. No production code, FDB schema/data, release or tag
  changes were made. This document is the only artifact added.
- **User notes:** `docs/usage_notes.md` is modified in the working tree and was
  **not** touched.

---

## 0. Executive summary

The complaint is reproducible, but it is not one bug. It is a small number of
repeated causes amplified by the number of paths that report a verdict.

**Totals (30 tickers):**

| Path | User-visible `INSUFFICIENT_DATA` | Underlying signals | Other |
|---|---:|---:|---|
| `scorecard` | **34 dimensions** | 288 rule-level `INSUFFICIENT` statuses | — |
| `methodologies` / `compare-methodologies` | **56 verdicts** (of 240) | — | 56 `N/A`, 128 other verdicts |
| `dcf` | **14 verdicts** (of 30) | — | 16 `OK`, 0 errors |
| **Distinct user-visible labels** | **104** | — | — |

- All 30 tickers have at least one `INSUFFICIENT_DATA` somewhere; 15/30 have at
  least one insufficient **scorecard dimension**.
- The 288 rule statuses are the underlying rule-level signals; many are the
  reason a dimension falls below the two-evaluable-rule threshold, but they are
  not 288 separate user-facing labels. The 56 methodology verdicts and the 14
  DCF verdicts are one per (ticker, methodology) and one per ticker.
- The 56 `N/A` methodology verdicts are the **7 financial companies × 8
  methodologies** (SAN, TD, JPM, BAC, BNS, MRX, AAMI). That is correct by
  design and must not be counted as a bug.
- **C3 (threshold too strict) = 0** in the sample. Thresholds produce `FAIL` /
  `WATCH`, not `INSUFFICIENT_DATA`.
- **Top 3 causes**, in priority order:
  1. **C4 — scorecard applicability/aggregation gaps.** The scorecard has no
     `is_financial`/REIT guard, `current_ratio` is hardcoded `INSUFFICIENT`, and
     Fisher turns 3 missing rules into a whole-methodology `INSUFFICIENT_DATA`.
     70 of the 288 rule statuses (11 of 34 dimensions) are the five banks alone;
     12/12 Fisher verdicts are triggered by the 3-of-4 aggregation.
  2. **C1-M — VI concept-mapping gaps.** The FDB fact exists but VI does not map
     it: IFRS OCF/capex/current assets/dividends/debt, US telecom capex
     (`PaymentsToAcquireOtherProductiveAssets`), and NCI equity in the insights
     path. This is 7 of the 14 DCF verdicts plus large scorecard blocks.
  3. **C2 — fiscal-year window off-by-one.** `_min_fiscal_year` uses
     `MAX(fiscal_year)` including stray FY2026 buckets, so a 10-year window
     starts at 2017 instead of 2016. This breaks 8 Fisher dilution cases, 1
     Graham-Dodd 10-year case (NEE; BJRI is a missing-year data gap) and the
     share/EPS rule block.
- **P/E 5,600:** the exact value is **not reproducible** for the four real-use
  tickers named in the notes (META, ESE, GOOGL, ACN). Their maxima are 1,652.9,
  2,149.7, 57.3 and 33.1. The closest current live-chart value is **TRC FY2025
  P/E 5,659.7** (~1% above the reported 5,600; net income $75k, mathematically
  correct near-zero earnings).
  A separate **genuine scale bug** produces COP FY2011 4,874.9 and BTI FY2019
  10,881,343. The Historical chart plots raw P/E with no cap or outlier filter,
  so any of these destroys the y-axis. See Part B.

The expected effect of the proposed fixes is roughly **104 → ~65** after the
cheap C4 fixes, **~45** after C2, and **~20** after C1-M. The remainder is real
insufficiency (C5) or FDB backfill (C1-T).

---

## Part A — `INSUFFICIENT_DATA`

### A.1 Totals per command

| Command | Tickers | User-visible `INSUFFICIENT_DATA` | Underlying signals | `N/A` | Notes |
|---|---:|---:|---:|---:|---|
| `scorecard` | 30 | 34 dimensions | 288 rule statuses | — | 15 tickers have ≥1 insufficient dimension |
| `methodologies` | 30 | 56 verdicts | — | 56 | 240 verdicts (8 methodologies × 30) |
| `dcf` | 30 | 14 verdicts | — | — | 16 OK, 0 errors |
| `compare-methodologies` | 30 | 56 verdicts | — | 56 | Same 8 evaluators as `methodologies`; not counted twice |
| **Distinct user-visible** | 30 | **104** | — | **56** | 34 dimensions + 56 methodologies + 14 DCF |

The `compare-methodologies` command is not an independent path: it evaluates
the same eight methodology classes as `methodologies show`. Counting both would
double-count the 56.

### A.2 Scorecard by dimension

| Dimension | Count | Tickers |
|---|---:|---|
| Shareholder Returns | 12 | SAN, TD, BNS, SNY, TTE, BTI, RACE, AZN, MRX, BRUN, SKT, BJRI |
| Financial Health | 10 | SAN, TD, BNS, SNY, TTE, AZN, MRX, AAMI, BRUN, SKT |
| Management/Moat | 8 | SAN, TD, JPM, BAC, BNS, MRX, BRUN, SKT |
| Valuation | 2 | BRUN, SKT |
| Growth | 1 | BRUN |
| Profitability | 1 | SKT |
| **Total** | **34** | |

A dimension becomes `Insufficient` when fewer than two of its rules are
evaluable (`score_rules` in `backend/services/scorecard_service.py`). It is
never scored as zero.

### A.3 Scorecard by rule

| Rule | Count | Tickers | Dominant cause family |
|---|---:|---|---|
| `current_ratio` | 30 | all 30 | **C4-P** (hardcoded) |
| `fcf_cagr_5y` | 21 | VZ, ADM, SAN, TD, JPM, BAC, BNS, SNY, TTE, BTI, RACE, AZN, PLD, DUK, NEE, MRX, AAMI, BRUN, SKT, BJRI, APA | C1-M / C1-T / C5 |
| `interest_coverage` | 20 | AAPL, JNJ, CAT, ADM, SAN, TD, JPM, BAC, BNS, SNY, TTE, AZN, NEE, PCAR, MRX, AAMI, BRUN, SKT, BJRI, APA | C1-M / C1-T / C5 |
| `debt_to_equity` | 20 | JNJ, CAT, T, VZ, CSX, ADM, PG, SAN, TD, BNS, SNY, TTE, BTI, RACE, AZN, PCAR, MRX, AAMI, BRUN, SKT | C1-M / C1-T / C5 |
| `dividend_cover` | 17 | SAN, TD, JPM, BAC, BNS, SNY, TTE, BTI, RACE, AZN, PLD, NEE, MRX, AAMI, BRUN, SKT, BJRI | C1-M / C5 |
| `fcf_conversion` | 16 | SAN, TD, JPM, BAC, BNS, SNY, TTE, BTI, RACE, AZN, PLD, NEE, MRX, AAMI, BRUN, SKT | C1-M / C5 |
| `fcf_positive` | 16 | same as `fcf_conversion` | C1-M / C5 |
| `fcf_yield` | 16 | same as `fcf_conversion` | C1-M / C5 |
| `gross_margin_level` | 15 | T, CSX, SAN, TD, JPM, BAC, BNS, BTI, PLD, NEE, MRX, AAMI, BRUN, SKT, APA | C1-T / C5 / C4-B |
| `gross_margin_stability` | 15 | same as `gross_margin_level` | C1-T / C5 / C4-B |
| `dcf_margin_of_safety` | 14 | VZ, TD, SNY, TTE, BTI, RACE, AZN, DUK, NEE, MRX, AAMI, BRUN, SKT, APA | C1-M / C1-T / C5 |
| `eps_cagr_5y` | 13 | T, SAN, TD, BNS, SNY, TTE, BTI, RACE, AZN, MRX, BRUN, SKT, BJRI | C2 / C1-T / C5 |
| `per_share_accretion` | 13 | same as `eps_cagr_5y` | C2 / C1-T / C5 |
| `roic_persistence` | 12 | JNJ, ADM, SAN, TD, JPM, BAC, BNS, TTE, PCAR, MRX, BRUN, SKT | C1-M / C2 / C5 |
| `roic` | 11 | JNJ, ADM, SAN, TD, JPM, BAC, BNS, TTE, PCAR, MRX, SKT | C1-M / C5 |
| `share_dilution` | 11 | SAN, TD, BNS, SNY, TTE, BTI, RACE, AZN, MRX, BRUN, SKT | C2 / C1-T / C5 |
| `roe` | 9 | JNJ, CAT, T, VZ, CSX, ADM, PG, AAMI, SKT | C1-M / C5 |
| `dividend_growth` | 7 | TD, SNY, AZN, AAMI, BRUN, SKT, BJRI | C1-M / C5 |
| `revenue_cagr_5y` | 4 | SAN, MRX, BRUN, APA | C5 / C1-T |
| `net_margin` | 3 | BRUN, SKT, APA | C1-T / C5 |
| `revenue_trend` | 2 | BRUN, APA | C5 / C1-T |
| `pe_absolute` | 2 | BRUN, SKT | C1-T / C5 |
| `earnings_sign` | 1 | SKT | C1-T |
| **Total** | **288** | | |

### A.4 Methodologies

| Methodology | `INSUFFICIENT_DATA` | `N/A` | Other | Insufficient tickers |
|---|---:|---:|---:|---|
| `greenblatt` | 23 | 7 | 0 | AAPL, MSFT, JNJ, CAT, T, VZ, CSX, ADM, PG, SNY, TTE, BTI, RACE, AZN, AMT, PLD, DUK, NEE, PCAR, BRUN, SKT, BJRI, APA |
| `fisher_quantitative_subset` | 12 | 7 | 11 | T, VZ, CSX, TTE, AMT, PLD, DUK, NEE, PCAR, BRUN, SKT, APA |
| `graham` | 8 | 7 | 15 | SNY, TTE, BTI, RACE, AZN, PLD, BRUN, SKT |
| `graham_dodd` | 8 | 7 | 15 | SNY, TTE, AZN, NEE, BRUN, SKT, BJRI, APA |
| `lynch_garp` | 4 | 7 | 19 | RACE, AZN, BRUN, SKT |
| `marks` | 1 | 7 | 22 | BRUN |
| `buffett_clark` | 0 | 7 | 23 | — |
| `buffett_classic` | 0 | 7 | 23 | — |
| **Total** | **56** | **56** | **128** | |

The 23 Greenblatt verdicts are one cause: the newest ranking file is empty.
The 12 Fisher verdicts are all triggered by the 3-of-4 aggregation (C4-A); the
missing rules underneath are C1/C2/C5. The Graham/Graham-Dodd verdicts are a
mix of IFRS history/mapping gaps and the 10-year check (window or missing
year).

### A.5 DCF

| Ticker | Missing input | Reason | Category |
|---|---|---|---|
| VZ | free cash flow | no usable FCF year; OCF/capex missing | **C1-M** (capex tag) |
| SNY | free cash flow | no usable FCF year; OCF/capex missing | **C1-M** (IFRS cash flow) |
| TTE | free cash flow | no usable FCF year; OCF/capex missing | **C1-M** (IFRS cash flow) |
| BTI | free cash flow | no usable FCF year; OCF/capex missing | **C1-M** (IFRS cash flow) |
| RACE | free cash flow | no usable FCF year; OCF/capex missing | **C1-M** (IFRS cash flow) |
| AZN | free cash flow | no usable FCF year; OCF/capex missing | **C1-M** (IFRS cash flow) |
| NEE | free cash flow | no usable FCF year; OCF/capex missing | **C1-T** (no capex tag) |
| TD | dividends per share | bank DDM; no dividends in last 5 years | **C1-M** (dividend tag) |
| MRX | dividend history ≥3 years | 1 year found, 3 required | **C5** |
| AAMI | dividends per share | no dividends in last 5 years | **C5** |
| SKT | funds from operations | no FFO; net income/depreciation missing | **C1-T/C5** |
| DUK | positive free cash flow | 3-year average −$1.457B | **C5** |
| APA | positive free cash flow | 3-year average −$397M | **C5** |
| BRUN | free cash flow | 2 fiscal rows | **C5** |

Six of the 14 DCF verdicts (VZ, SNY, TTE, BTI, RACE, AZN) are the **same**
capex/OCF mapping gap. TD is a dividend mapping gap. NEE is a true missing
capex tag. DUK/APA/BRUN/MRX/AAMI are real insufficiency. SKT is a REIT FFO
gap plus an ingestion gap.

### A.6 Per-ticker counts

| Ticker | Scorecard dims | Scorecard rules | Methodology `INSUFFICIENT` | Methodology `N/A` | DCF | Total |
|---|---:|---:|---:|---:|---:|---:|
| BRUN | 5 | 20 | 6 | 0 | 1 | 12 |
| SKT | 5 | 21 | 5 | 0 | 1 | 11 |
| AZN | 2 | 13 | 4 | 0 | 1 | 7 |
| TTE | 2 | 14 | 4 | 0 | 1 | 7 |
| SNY | 2 | 13 | 3 | 0 | 1 | 6 |
| RACE | 1 | 11 | 3 | 0 | 1 | 5 |
| APA | 0 | 9 | 3 | 0 | 1 | 4 |
| BTI | 1 | 13 | 2 | 0 | 1 | 4 |
| MRX | 3 | 17 | 0 | 8 | 1 | 4 |
| NEE | 0 | 10 | 3 | 0 | 1 | 4 |
| TD | 3 | 17 | 0 | 8 | 1 | 4 |
| BJRI | 1 | 7 | 2 | 0 | 0 | 3 |
| BNS | 3 | 15 | 0 | 8 | 0 | 3 |
| DUK | 0 | 3 | 2 | 0 | 1 | 3 |
| PLD | 0 | 8 | 3 | 0 | 0 | 3 |
| SAN | 3 | 16 | 0 | 8 | 0 | 3 |
| VZ | 0 | 5 | 2 | 0 | 1 | 3 |
| AAMI | 1 | 13 | 0 | 8 | 1 | 2 |
| AMT | 0 | 1 | 2 | 0 | 0 | 2 |
| CSX | 0 | 5 | 2 | 0 | 0 | 2 |
| PCAR | 0 | 5 | 2 | 0 | 0 | 2 |
| T | 0 | 7 | 2 | 0 | 0 | 2 |
| AAPL | 0 | 2 | 1 | 0 | 0 | 1 |
| ADM | 0 | 7 | 1 | 0 | 0 | 1 |
| BAC | 1 | 11 | 0 | 8 | 0 | 1 |
| CAT | 0 | 4 | 1 | 0 | 0 | 1 |
| JNJ | 0 | 6 | 1 | 0 | 0 | 1 |
| JPM | 1 | 11 | 0 | 8 | 0 | 1 |
| MSFT | 0 | 1 | 1 | 0 | 0 | 1 |
| PG | 0 | 3 | 1 | 0 | 0 | 1 |
| **Total** | **34** | **288** | **56** | **56** | **14** | **104** |

### A.7 Ten-case categorization (C1–C5)

The taxonomy is extended with three explicitly labelled C1 sub-cases, because
the original C1 (“the field is absent from `financial_facts`”) does not cover
them and calling them C4 would hide the root cause:

- **C1-T** — true missing fact in FDB.
- **C1-M** — the fact exists in `financial_facts`, but VI's concept map /
  normalization / insights path does not surface it.
- **C1-D** — the derived artifact VI reads is missing or empty.

| # | Case | Ticker(s) | Path | Required data | Evidence | Category |
|---:|---|---|---|---|---|---|
| 1 | Greenblatt ranking missing | ACN + 22 others | methodology | newest ranking payload | `data/rankings/greenblatt_2026-11-02.json` is 67 bytes with `rankings: {}` and `universe_size: 0`; the four newest files (10-12, 10-19, 10-26, 11-02) are all empty; only 2026-09-30 has 270 rankings. `_load_rankings` picks the newest file unconditionally. | **C1-D** |
| 2 | Fisher dilution window | T, VZ, CSX, AMT, PLD, DUK, NEE, PCAR | methodology | shares FY2015 | FDB has FY2015/FY2016 facts for all eight (T 631/625, VZ 1057/832, CSX 445/441, AMT 752/757, PLD 649/621, DUK 865/833, NEE 594/558, PCAR 519/542). The usable rows differ: T/VZ/PLD/DUK/NEE return 9 rows 2017–2025 (stray FY2026 makes `MAX(fiscal_year)` = 2026); CSX/PCAR return 10 rows 2016–2025, but the rule asks for `latest - 10 = 2015`, which is still outside a 10-row window; AMT returns 7 usable rows 2019–2025 (FY2017/2018 empty). The target FY2015 is outside in all three sub-cases. | **C2** (C2a/C2b/C2c) |
| 3 | Fisher dilution true missing | TTE | methodology | shares FY2015 | FDB `MIN(fiscal_year)` = 2017; 0 FY2015 and 0 FY2016 facts. The data never existed in FDB for this ADR. | **C1-T** |
| 4 | Fisher R&D / 3-of-4 aggregation | T, VZ, CSX, TTE, AMT, PLD, DUK, NEE, PCAR, BRUN, SKT, APA | methodology | R&D, gross margin, dilution | `_verdict` returns `INSUFFICIENT_DATA` when `insufficient >= 3`. For T: R&D not reported (telecom), 0 years of gross margin, no FY2015 shares → 3 insufficient. For AMT/PLD/SKT the R&D/gross-margin rules are not meaningful for REITs. The rules are structurally not applicable, but the aggregation treats them as missing evidence. | **C4-A** (underlying C5 / C4-B) |
| 5 | Graham current assets | SNY | methodology | current assets/liabilities | Raw FDB has `CurrentAssets` 42.588B / 30.952B and `CurrentLiabilities` 29.162B / 28.345B for FY2025. `financial_facts_normalized` has **no** `current_assets`/`current_liabilities` for SNY. `BALANCE_SHEET_CONCEPTS` maps `AssetsCurrent`/`LiabilitiesCurrent` only, not the IFRS tags `CurrentAssets`/`CurrentLiabilities`. | **C1-M** |
| 6 | Graham dividends | SNY | methodology | dividends paid | Raw FDB has `DividendsPaidOrdinarySharesPerShare` 3.92 / 3.76 / 3.56 and `DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities` 4.772B / 4.704B / 4.454B. Normalized SNY has no `dividends_paid` and no `dividends_per_share`. The cash-flow map only knows US-GAAP dividend tags. | **C1-M** |
| 7 | DCF VZ | VZ | DCF | free cash flow | VZ FY2019–FY2025 tags capex as `PaymentsToAcquireOtherProductiveAssets` (18.767B / 17.011B / 17.090B in FY2025). `CASH_FLOW_FIELD_PRIORITY["capital_expenditure"]` lists `PaymentsToAcquireProductiveAssets` but **not** `PaymentsToAcquireOtherProductiveAssets`. FY2018 and earlier use `PaymentsToAcquireProductiveAssets` and work; FY2019–FY2025 capex is `None`, so FCF is `None` and DCF stops. | **C1-M** |
| 8 | DCF TD | TD | DCF | dividends per share | Raw FDB has `DividendsPaidOrdinarySharesPerShare` 4.20 / 4.08 / 3.84 and `DividendsPaidClassifiedAsFinancingActivities` 7.663B / 7.162B. Normalized TD has no `dividends_per_share`; the DDM sees “No dividends paid in the last 5 fiscal years”. | **C1-M** |
| 9 | DCF DUK | DUK | DCF | positive FCF | FCF is negative every year: −1.418B (FY2017) to −1.694B (FY2025); 3-year average −1.457B. The DCF correctly refuses. This is real insufficiency, not a missing field. | **C5** |
| 10 | Scorecard `current_ratio` | all 30 | scorecard | current ratio | `_financial_health_rules` hardcodes `INSUFFICIENT` with the reason “Current ratio is not computed by backend/analytics yet (see backlog)”. Current assets/liabilities are already available in the normalized rows for many tickers (e.g. T 48.732B/53.780B, VZ 56.922B/62.370B, JNJ 55.624B/54.126B, CAT 52.485B/36.558B). | **C4-P** |

### A.8 Additional confirmed cases

| # | Case | Ticker(s) | Evidence | Category |
|---:|---|---|---|---|
| 11 | Scorecard D/E and ROE | T, VZ, JNJ, CAT, CSX, ADM, PG | The repository row/core data have equity (T 126.491B, JNJ 81.544B, CAT 21.318B), but `FinancialInsightsService` returns an **empty** `stockholders_equity` series for all seven. The raw facts carry `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` (T 126.491B, JNJ 81.544B, CAT 21.318B, ADM 22.740B), which is not in the insights `BALANCE_SHEET_CONCEPTS` map. The scorecard uses `metrics.latest("debt_to_equity")` / `roe` from the insights path, so it misses equity that the repository already has. | **C1-M + C4** (dual path) |
| 12 | Scorecard interest coverage | JNJ, ADM (no EBIT); CAT (no interest expense); AAPL (no interest) | JNJ/ADM do not tag `OperatingIncomeLoss`; they do tag `IncomeLossFromContinuingOperationsBeforeIncomeTaxes…` and `InterestExpense`/`InterestExpenseNonoperating`, so EBIT is derivable as pretax + interest. CAT has `OperatingIncomeLoss` but no `InterestExpense`; it does tag `InterestPaidNet` 1.842B. AAPL has no interest expense (net cash), so coverage is genuinely not applicable. | **C1-M / C1-T / C5** |
| 13 | Scorecard FCF CAGR / FCF conversion / FCF yield / FCF positive | VZ, SNY, TTE, BTI, RACE, AZN, NEE, banks | Same missing FCF as cases 7/8: VZ/IFRS/NEE have no mapped OCF/capex. Banks have no meaningful FCF; the scorecard has no `is_financial` guard. | **C1-M / C1-T / C4-B** |
| 14 | Scorecard dividend cover / dividend growth | TD, SNY, TTE, BTI, RACE, AZN, banks | Same dividend mapping gap as case 8; non-payers (BRUN, SKT) are C5. | **C1-M / C5** |
| 15 | DCF BRUN / MRX | BRUN, MRX | BRUN has 2 fiscal rows (2025, 2026); MRX has 1 row (2024). Not enough history for an FCF base. | **C5** |
| 16 | Graham / Graham-Dodd 10-year history | T (C2); SNY/TTE/BTI/RACE/AZN (C1-T); PLD (C2); BJRI (C1-T FY2022 missing); BRUN (C5); SKT (C1-T ingestion gap) | `needs 10 fiscal years` / `needs 10 years of data`. T has 9 rows 2017–2025 and FY2016 facts exist; SNY/TTE/BTI/RACE/AZN start at FY2017; PLD has 9 rows but FY2016 facts exist; BJRI has 9 rows because FY2022 is missing; BRUN is short; SKT is missing FY2024/2025 balance facts. | **C2 / C1-T / C5** |
| 17 | DCF NEE | NEE | NEE tags OCF (`NetCashProvidedByUsedInOperatingActivities` 12.485B FY2025) but **no capex tag at all**: only `CapitalExpendituresIncurredButNotYetPaid` and `ProceedsFromSaleOfProductiveAssets`. This is a true FDB gap, not a VI mapping gap. | **C1-T** |

### A.9 C3 = 0, and the C1 split

No sampled case is C3. Thresholds did not produce `INSUFFICIENT_DATA`; they
produced `FAIL`/`WATCH`:

- TTE Fisher R&D 0.4% vs 0.5% → `FAIL`, not insufficient.
- TTE Graham P/BV 1.66 vs 1.5 → `FAIL`, not insufficient.
- TTE Graham P/E 11.5 → `PASS`.

The insufficient verdicts are caused by missing/mapping/period/guard issues, not
by a threshold being too strict. If a future audit finds a C3, it will be in a
methodology that maps a present value to an `INSUFFICIENT` status; that is not
what the sample shows.

---

## Part B — Absurd values in charts

### B.1 Where the P/E chart comes from

The chart the user is describing is the **Analysis → Historical** tab:

```
ui/pages/02_analysis.py
  tabs[4] = "Historical"
  _historical(ticker)                                  # line 1026
    data = load_historical_valuation(ticker)           # ui/services.py:110
      HistoricalValuationService(...)
        .get_historical_valuation_summary(ticker)      # backend/services/historical_valuation_service.py:107
    pe_rows = [... if row.get("pe_ratio") is not None] # lines 1030-1034
    st.line_chart(pe_rows, x="Fiscal year", y="P/E")   # line 1051
```

There is **no cap, winsorization, log scale or outlier filter**. The chart
plots every non-`None` P/E, including negative values and near-zero-earnings
outliers. The same `_historical` function also plots FCF yield, which can be
extreme for the same reasons.

### B.2 The reported P/E 5,600

#### The four tickers named in `docs/usage_notes.md`

`META`, `ESE`, `GOOGL`, `ACN` are the real-use tickers in the notes. The exact
service output for them is:

| Ticker | Max abs(P/E) | Year | Net income | Shares used | EPS | Comment |
|---|---:|---:|---:|---:|---:|---|
| META | 1,652.9 | 2012 | $32.0M | 2.006B | $0.01595 | Correct near-zero earnings; display-hostile |
| ESE | 2,149.7 | 2014 | $410k | 26.699M | $0.01536 | Correct near-zero earnings; display-hostile |
| GOOGL | 57.3 | 2017 | $12.662B | 694.783M | $0.9112 | Normal |
| ACN | 33.1 | 2021 | $5.913B | 636.300M | $9.2933 | Normal |

None of them produces 5,600. If the user saw the Historical tab for one of
these four, the outlier is 1,652.9 (META) or 2,149.7 (ESE), not 5,600.

#### Exact-service candidates near 5,600

We replicated the service's own share selection (`repo.get_shares_outstanding`
+ `get_fiscal_year_end_date` + `get_price_at_fiscal_year_end`) rather than using
the normalized weighted-average shares. The candidates in the 4,000–7,000 band:

| Ticker | FY | Price | Net income | Shares used | EPS | P/E | Classification |
|---|---:|---:|---:|---:|---:|---:|---|
| **TRC** | 2025 | 15.77 | $75,000 | 26,916,837 | 0.002786 | **5,659.7** | Correct near-zero earnings; **best current match** to “5,600” |
| TTI | 2013 | 11.78 | $153,000 | 78,855,547 | 0.001940 | 6,071.1 | Correct near-zero earnings; display-hostile |
| COP | 2011 | 33.61 | $12.436B | 1,375,035,000,000 | 0.006894 | 4,874.9 | **Scale bug** (shares ×1,000; correct EPS ≈ $9.04, P/E ≈ 3.7) |
| AXON | 2019 | 73.28 | $882,000 | 59,497,759 | 0.014824 | 4,943.3 | Correct near-zero earnings; display-hostile |
| AXON | 2020 | 122.53 | −$1.724M | 63,766,555 | −0.027036 | −4,532.1 | Correct negative earnings; display-hostile |
| BTI | 2019 | 25.91 | $5.849B | 2,456,520,738,000,000 | 2.381e−6 | **10,881,343** | **Scale bug** (shares ×1,000,000; correct EPS ≈ $2.38, P/E ≈ 10.9) |
| SHW | 2009 | 17.12 | $435.848M | 109,436,869 | 1.3275 | 12.9 | Service repairs the batch value |
| SHW (batch) | 2009 | 21.12 | $435.848M | 115,422,933,000 | 0.003776 | 5,592.2 | Batch only; not what the chart shows |

The closest numeric value in the earlier batch scan was **SHW FY2009 5,592**,
but the actual chart service returns **12.9** for SHW because it prefers
`CommonStockSharesOutstanding` (109.4M) over the mis-scaled normalized
weighted-average count (115.4B). This is a useful negative result: not every
batch outlier reaches the chart.

#### Conclusion on the exact ticker

- The exact value **5,600 is not present** in the current service output for
  any of the 30 audit tickers, the four named real-use tickers, or the eight
  near-band candidates we tested.
- The **best current match is TRC FY2025 at 5,659.7** (~1% above the reported
  5,600). It is a mathematically correct near-zero-earnings point: $75k net
  income on 26.9M shares.
- A second, genuinely wrong case in the same band is **COP FY2011 4,874.9**,
  caused by a 1,000× share-scale error. **BTI FY2019 10,881,343** is the same
  class with a 1,000,000× error.
- If the user can provide the ticker or a screenshot, the exact case can be
  pinned. The fix does not depend on it: the Historical chart needs an outlier
  policy, and the share-selection layer needs a scale sanity check. Both cover
  the entire class.

**Do not claim the exact ticker without the screenshot.** The report should say
“best current match: TRC FY2025; exact ticker pending user confirmation.”

### B.3 Classification: correct-but-ugly vs bug

| Class | Examples | Is the math right? | What to do |
|---|---|---|---|
| Near-zero positive earnings | TRC 2025 5,659.7; TTI 2013 6,071.1; META 2012 1,652.9; ESE 2014 2,149.7; AXON 2019 4,943.3; JNJ 2017 234.5; BAC 2011 530.2 | Yes: P/E = price / (NI/shares) | Cap/flag in chart; keep exact value in table |
| Negative earnings | CAT 2016 −656.1; T 2020 −26.1; PLD 2012 −138.2; AXON 2020 −4,532.1; BJRI 2021 −230.7 | Yes: negative P/E is mathematically defined | Exclude from the line chart or use a separate “negative earnings” marker; table can show `n.m.` |
| Share-scale error | BTI 2019 10.88M; COP 2011 4,874.9; SHW batch 5,592; EEFT 5.28e16; NMR 3.54e15; KRG 6.69e13; NTRS 2.43e14; FOSL 5.23e13; EIX 3.41e14; CBT 6.42e13; ALC 3.01e14; AX 1.53e10; HAFC 3.15e10 | No: denominator is 10³–10⁹ too large | Fix at the share-selection/normalization layer; display cap as a safety net |
| Near-zero revenue margins | CRMD 2013 −27,861×; ALLO 2023 −16,444×; INBX 2024 8,437× | Yes: net income / tiny revenue | Same display policy as P/E |
| Gross profit > revenue | NPO 2016 986.75×; SLP 2012 840.14×; URG 2021 −436.5× | Usually no: units/mapping error | Data-quality flag; do not chart silently |
| Negative equity D/E | SNDA 2025 −62,703×; CTGO 2023 −1,750×; OPFI 2022 −697× | Arithmetic yes, meaning no | Mark `n.m.` / negative equity; do not plot |
| Extreme ROE | SNDA 2025 6,946×; AVR 2025 1,012×; NRGV 2020 −1,011× | Arithmetic yes, meaning no | Same |

The important distinction for the user’s complaint is the first two rows:
**most absurd P/E values are mathematically correct**; the chart is the problem.
The third row is a real calculation bug and needs a data-quality fix.

### B.4 Other absurd-metric families (universe scan)

The following scan is over the 2,451 files in `data/cache/analysis` (not just
the 30 audit tickers), so the frequencies are universe-level, not per-command.
The counts are not mutually exclusive: one ticker-year can appear in several
families.

| Family | Definition | Ticker-years | Tickers | Worst examples | Classification |
|---|---|---:|---:|---|---|
| Gross margin | `gross_profit/revenue > 1.5` or `< −0.5` | 102 | 51 | NPO 2016 986.75×; SLP 2012 840.14×; URG 2021 −436.5× | Data/units bug |
| Net margin | `net_income/revenue > 1.0` or `< −1.0` | 1,764 | 514 | CRMD 2013 −27,861×; ALLO 2023 −16,444×; INBX 2024 8,437× | Correct near-zero revenue / display |
| Negative D/E | `total_debt/equity < 0` | 1,088 | 292 | SNDA 2025 −62,703×; CTGO 2023 −1,750×; OPFI 2022 −697× | Negative equity; meaningless; flag |
| Extreme ROE | `abs(net_income/equity) > 2` | 1,020 | 436 | SNDA 2025 6,946×; AVR 2025 1,012×; NRGV 2020 −1,011× | Near-zero/negative equity; display |
| Peer P/E max | `max` in `data/peer_stats/*.json` | — | — | Healthcare 25,244,391; Utilities 20,522; Real Estate 1,870; Software Infrastructure 911; Software Application 823.6 | Outlier contamination; **median is sane** (20–38), so the peer-median bar is not the 5,600 source |

The peer-median bar in the Scorecard tab uses the median, not the max, so the
peer chart is not the source of the 5,600. The Historical line chart is.

### B.5 Display strategy (proposal, not implemented)

1. **Cap or exclude in the chart, keep the table exact.**
   - P/E: chart only values in `[-100, 100]`; keep the full series in the
     underlying table/JSON. Add a caption: “N outlier year(s) outside
     [−100, 100] hidden; see table.”
   - FCF yield: same policy with a `[-100%, 100%]` band.
   - Margins/ROE: same policy; use `n.m.` for denominators near zero.
2. **Mark near-zero earnings.**
   - If `|EPS| < 0.05` or `|P/E| > 100`, show `n.m.` in the table and exclude
     from the line chart. The exact raw value can stay in the JSON.
3. **Fix the share scale at the source.**
   - In `get_shares_outstanding` / normalization, compare the chosen count with
     the prior and next fiscal year. If it is >10× or <0.1× the neighbor, try
     dividing by 10³/10⁶/10⁹ to bring it into range; if no plausible factor,
     fall back to the neighbor and flag the company.
   - This fixes BTI, COP, EEFT, NMR, KRG, NTRS, FOSL, EIX, CBT, ALC, AX, HAFC
     and SHW at the source. The display cap remains a safety net.
4. **Peer stats.**
   - Winsorize P/E at the 1st/99th percentile (or exclude `|P/E| > 100`) before
     computing `max`/`median`. The median is already robust; the `max` field is
     not used by the bar but contaminates the artifact.
5. **Do not “fix” negative P/E by taking absolute value.** A negative P/E means
   negative earnings; it should be shown as `n.m.` or as a separate marker, not
   as a positive multiple.

---

## Part C — Top 3 causes and fix plan

### C.1 C4 — scorecard applicability and aggregation gaps (largest frequency, cheapest)

**Evidence.**

- **C4-B (banks/REITs treated as industrials):** the five banks alone account
  for **70 of 288 rule statuses** (including their 5 `current_ratio` statuses)
  and **11 of 34 dimensions**:
  - SAN 16 rules / 3 dims; TD 17 / 3; JPM 11 / 1; BAC 11 / 1; BNS 15 / 3.
  - The same 11 rules are insufficient for all five banks:
    `fcf_cagr_5y`, `roic`, `gross_margin_level`, `fcf_conversion`,
    `interest_coverage`, `current_ratio`, `fcf_positive`, `fcf_yield`,
    `dividend_cover`, `roic_persistence`, `gross_margin_stability`.
  - All eight methodologies already use `is_financial()` and return `N/A` for
    these seven companies. The scorecard does **not** import or call
    `is_financial` (`grep` in `backend/services/scorecard_service.py`: no
    matches). So the methodology layer says “N/A, bank” while the scorecard
    says “INSUFFICIENT, no FCF/current ratio/gross margin”.
  - REITs add AMT 1, PLD 8, SKT 21 rule statuses; not all are applicability
    (SKT also has missing FY2024/2025 balance facts), but the R&D/gross-margin
    rules are not meaningful for REITs.
- **C4-P (`current_ratio` hardcoded):** 30/30. `_financial_health_rules`
  appends a rule with status `INSUFFICIENT` and the reason “Current ratio is not
  computed by backend/analytics yet (see backlog)”. The data is already there
  for many tickers (T, VZ, JNJ, CAT, CSX, ADM, PG, etc.).
- **C4-A (Fisher 3-of-4):** all 12 Fisher `INSUFFICIENT_DATA` verdicts are
  triggered by `_verdict`: `if insufficient >= 3: return INSUFFICIENT_DATA`.
  For T, the three missing rules are R&D (not reported by telecom), gross
  margin (not reported), and dilution (window). The first two are “not
  applicable”, not “missing evidence”.

**Fix.**

1. Add a scorecard applicability layer that reuses `is_financial()`:
   - For the seven financial companies, either mark the industrial rules `N/A`
     (and let the dimension verdict be `N/A` / a bank-specific scorecard) or
     add bank-specific rules (e.g. ROE, NIM, efficiency ratio, CET1, dividend
     cover from net income). This is a **product decision**; the cheap version
     is `N/A`.
   - For REITs, skip R&D and gross-margin rules; use FFO-based metrics where
     available.
2. Implement `current_ratio` from `current_assets / current_liabilities` with a
   `CurrentRatioCalculator` and a `None` guard. For banks/IFRS without a current
   split, the applicability layer should return `N/A`, not `INSUFFICIENT`.
3. Change Fisher aggregation so “not applicable” is a `SKIP`, not
   `INSUFFICIENT`, and require at least two evaluable rules. The verdict should
   be `INSUFFICIENT_DATA` only when the *evaluable* evidence is insufficient,
   not when the industry does not report the metric.

**Cost / risk.**

- 1–2 days for the `N/A` version + current ratio + Fisher aggregation.
- Risk: **medium** for the bank/REIT product decision (changes scores for 7
  financials and 3 REITs); low for `current_ratio` and Fisher aggregation.
- Expected effect: `current_ratio` 30 → 0; 11 bank dimensions disappear or
  become a bank scorecard; Fisher 12 → ~2–4. The 104 total drops to ~65.

### C.2 C1-M — VI concept-mapping gaps (largest breadth across paths)

**Evidence.**

- **DCF:** 6 of 14 verdicts are the same capex/OCF mapping gap:
  - VZ: `PaymentsToAcquireOtherProductiveAssets` exists FY2019–FY2025 but is
    not in `CASH_FLOW_FIELD_PRIORITY["capital_expenditure"]`; capex is `None`
    from FY2019.
  - SNY/TTE/BTI/RACE/AZN: IFRS `CashFlowsFromUsedInOperatingActivities` and
    `PurchaseOfPropertyPlantAndEquipment…` exist in FDB (SNY FY2025: OCF
    10.258B, capex 2.906B) but the cash-flow map only knows US-GAAP tags.
  - TD: `DividendsPaidOrdinarySharesPerShare` and
    `DividendsPaidClassifiedAsFinancingActivities` exist; the DDM sees no
    dividends.
- **Scorecard D/E and ROE:** 7 large caps (T, VZ, JNJ, CAT, CSX, ADM, PG) have
  raw `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`
  and repository/core equity, but `FinancialInsightsService` returns an empty
  `stockholders_equity` series because its `BALANCE_SHEET_CONCEPTS` map lacks
  the NCI tag. The scorecard reads D/E and ROE from that path.
- **Scorecard current assets/dividends:** SNY raw `CurrentAssets` /
  `CurrentLiabilities` and dividends exist; the normalized layer has neither.
- **Scorecard IFRS debt:** `total_debt` is `None` for SNY/TTE/BTI/RACE/AZN;
  the debt map only knows US-GAAP `DebtCurrent`/`LongTermDebt` tags.
- **Rule-family counts (overlapping, not disjoint):** FCF block 21+16+16+16 =
  69; D/E+ROE+ROIC block 20+9+11+12 = 52; dividend block 17+7 = 24; gross
  margin 15+15 = 30 (partly C1-M, partly C5); IFRS current assets appears in the
  Graham verdicts (SNY/TTE/BTI/RACE/AZN); DCF 8 C1-M/C1-T.

**Fix.**

1. Extend `CASH_FLOW_FIELD_PRIORITY` with:
   - `PaymentsToAcquireOtherProductiveAssets` (VZ).
   - IFRS OCF: `CashFlowsFromUsedInOperatingActivities`,
     `CashFlowsFromUsedInOperatingActivitiesContinuingOperations`.
   - IFRS capex: `PurchaseOfPropertyPlantAndEquipment…`,
     `AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment`,
     and the other IFRS variants present in FDB.
2. Extend `BALANCE_SHEET_CONCEPTS` with:
   - `CurrentAssets` / `CurrentLiabilities` (IFRS).
   - `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`.
   - IFRS debt tags (`Borrowings`, `CurrentBorrowings…`, `NoncurrentBorrowings…`)
     for total debt.
3. Extend the dividend map with:
   - `DividendsPaidOrdinarySharesPerShare` (per-share DDM input).
   - `DividendsPaidClassifiedAsFinancingActivities`,
     `DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities`,
     `DividendsRecognisedAsDistributionsToOwnersOfParent`.
4. Make `FinancialInsightsService` read the same normalized/core fields as the
   repository, or at least share one concept map. The dual path is the reason
   the repository has equity but the scorecard does not.
5. Add regression tests with the exact FDB facts above (VZ FY2025, SNY FY2025,
   TD FY2025, T FY2025) so the mapping cannot silently regress.

**Cost / risk.**

- 2–3 days including tests and a validation run over the 30 tickers.
- Risk: **medium**. Concept collisions and duplicate tags are the main risk
  (e.g. IFRS `CurrentAssets` vs US `AssetsCurrent`, `Equity` vs
  `StockholdersEquity`); the priority lists already have a pattern for this.
- Expected effect: DCF 14 → ~7 (the 7 C1-M cases resolve; the C5 and NEE C1-T
  cases remain); scorecard D/E/ROE/FCF/dividend blocks shrink substantially;
  total 104 → ~20–30 after this and C4/C2.

### C.3 C2 — fiscal-year window off-by-one (cheap, broad)

**Evidence.**

- `_min_fiscal_year` (`backend/repositories/fdb_mixins/facts_mixin.py:181`)
  does `SELECT MAX(fiscal_year) … fiscal_period='FY'` and returns
  `latest - max_years + 1`.
- T and VZ have a stray FY2026 bucket (only a few Q facts, no FY row), so
  `MAX(fiscal_year)` = 2026 and the 10-year window starts at **2017**. The
  usable rows are 2017–2025 (9 years), and FY2016 exists in FDB (T 625 facts,
  VZ 832 facts).
- This breaks:
  - **Fisher dilution:** 8 of 12, via three sub-mechanisms:
    - **C2a — stray FY2026 bucket:** T, VZ, PLD, DUK, NEE return 9 rows
      2017–2025 instead of 2016–2025.
    - **C2b — 10 rows vs 10 years:** CSX and PCAR return 10 rows 2016–2025,
      but the rule asks for `latest - 10 = 2015`; a 10-row window spans only
      nine year-over-year intervals.
    - **C2c — empty rows:** AMT returns 7 usable rows 2019–2025 even though
      FDB has FY2015/FY2016 facts; the intermediate rows are empty/dropped.
    - The dilution rule becomes evaluable in all eight; all eight Fisher
      verdicts flip because each has exactly three missing rules.
  - **Graham-Dodd 10-year:** 1 of 8 (NEE) has FY2015/2016 facts but the window
    drops one year; BJRI is C1-T (FY2022 is missing), not a window case.
  - **Scorecard share block:** `share_dilution` 11, `per_share_accretion` 13,
    `eps_cagr_5y` 13 (overlapping tickers).
- The true-missing cases are different: SNY/TTE/BTI/RACE/AZN start at FY2017 in
  FDB (C1-T); BRUN/MRX/APA are short (C5); BJRI is missing FY2022 (C1-T); SKT
  has an ingestion gap.

**Fix.**

- Anchor the window on the newest **usable** fiscal year, not the raw
  `MAX(fiscal_year)`. Options:
  - `MAX(fiscal_year)` over rows with a non-empty FY row (the same
    `_row_is_empty` predicate the repository uses), or
  - `MAX(fiscal_year)` over rows with at least one core financial field, or
  - `MAX(period_end)` of the latest usable year minus `max_years - 1`.
- For a 10-years-ago comparison, fetch **11** rows (or expose the FY 10 years
  before the latest); a 10-row window only spans nine intervals. This fixes
  C2b for CSX/PCAR without changing `max_years=10` for other callers.
  Alternatively, change the dilution rule to compare `latest` with the earliest
  available row and label the comparison as 9-year rather than 10-year.
- Add tests: stray FY2026 + FY2016 facts → `list_years(..., max_years=10)`
  returns 2016–2025; CSX/PCAR-style max 2025 + FY2015 facts → the 11-row
  dilution lookup finds FY2015; AMT-style empty intermediate rows are reported
  as a data gap, not silently treated as 10 years.
- Keep the behavior for companies whose history genuinely starts in 2017 (SNY
  etc.); the fix must not invent years.

**Cost / risk.**

- ~0.5–1 day including the regression tests (window anchor + 11-row fetch).
- Risk: **low–medium**. The only risk is changing which year is considered
  “latest” for companies with an in-progress bucket; the `_row_is_empty` filter
  already defines the usable rows, so the fix is consistent with it.
- Expected effect: Fisher dilution 8 C2 → 0 (all 8 verdicts flip; TTE/APA
  remain C1-T/C5); Graham-Dodd 1 C2 (NEE) → 0; BJRI remains C1-T; share/EPS
  block shrinks. Total 104 → ~45 after C4+C2.

### Why this order

- **C4 first** because it is the largest single frequency (70 bank rules, 30
  current_ratio, 12 Fisher verdicts) and the cheapest. It directly addresses
  the “1–2 per stock” feeling: JPM/BAC each show 11 rule-level insufficients
  today, almost all from bank-inapplicable industrial rules.
- **C1-M second** because it is the largest breadth across DCF and scorecard,
  but it needs careful concept-priority work and regression tests.
- **C2 third** because it is a small, well-understood change (window anchor
  plus an 11-row fetch for the 10-years-ago check) with broad effect. It can be
  done in parallel with C1-M.

---

## Part D — Out of scope

These are real, but they are not VI code fixes in this session:

1. **C1-T true missing FDB facts.**
   - NEE has no capex tag at all (only `CapitalExpendituresIncurredButNotYetPaid`
     and `ProceedsFromSaleOfProductiveAssets`). Needs an FDB ingestion/backfill
     decision.
   - SNY/TTE/BTI/RACE/AZN have no FY2016 and earlier annual facts in FDB
     (`MIN(fiscal_year)=2017`). Needs FDB backfill or accepting a 9-year history.
   - SKT has no FY2024/2025 balance facts (ingestion gap) and no FFO tag. Needs
     `sec sync` / FDB investigation.
2. **C5 real insufficiency.**
   - DUK/APA negative FCF (capex-heavy utilities/energy); DCF correctly
     declines.
   - BRUN/MRX too little history (2/1 fiscal rows).
   - AAMI/MRX no dividend stream for the bank DDM.
   - AAPL no interest expense (net cash); interest coverage is not applicable.
   - Banks have no current/non-current split; current ratio is not applicable.
3. **Bank/REIT scorecard treatment.** The `N/A` version is cheap; a
   bank-specific scorecard (ROE, NIM, efficiency, CET1, dividend cover from net
   income) and a REIT-specific scorecard (FFO, AFFO, occupancy, leverage) are
   product decisions. Do not silently score banks with industrial rules.
4. **FDB share-scale repair at ingestion.** The VI-side display cap and
   share-selection sanity check are safety nets; the root fix belongs in FDB
   (the `EntityCommonStockSharesOutstanding` / weighted-average tags are stored
   with 10³–10⁹ scale errors for BTI, COP, EEFT, NMR, KRG, NTRS, FOSL, EIX,
   CBT, ALC, AX, HAFC). That is a separate FDB task.
5. **Peer-stats regeneration.** The peer artifacts are from 2026-10-16; the
   `max` fields are contaminated by outliers. The bar uses the median, so this
   is not the 5,600 source, but a winsorized regeneration is a separate run.
6. **Full-universe count.** This audit is the 30-ticker sample. The 2,451-file
   cache scan gives universe-level anomaly frequencies, but the
   `INSUFFICIENT_DATA` totals are for the 30 tickers only. A full-universe
   count would be a separate, longer run.

---

## Part E — Next session proposal

The session order puts the 0.5-day C2 fix before the larger C1-M work; this is
a sequencing choice (C2 is cheap and can land while the mapping work is
prepared), not a change in priority. Priority-wise the order remains C4 → C1-M
→ C2, as in Part C.

### Session 1 — C4 (1–2 days)

1. Add a scorecard applicability helper that reuses `is_financial()` and a REIT
   check. For the seven financials, return `N/A` for the industrial rules (or a
   bank-specific subset if product approves).
2. Implement `CurrentRatioCalculator` and wire `current_ratio` into
   `_financial_health_rules`; return `N/A` when the current split is absent.
3. Change Fisher `_verdict` to treat not-applicable as `SKIP` and require at
   least two evaluable rules.
4. Tests: bank scorecard, REIT scorecard, current ratio with/without split,
   Fisher with 3 not-applicable rules.
5. Re-run the 30-ticker audit and record the before/after counts.

**Expected:** `current_ratio` 30 → 0; 11 bank dimensions → N/A or bank-specific;
Fisher 12 → ~2–4; total 104 → ~65.

### Session 2 — C2 (0.5–1 day)

1. Anchor `_min_fiscal_year` on the newest usable FY (non-empty row).
2. For the 10-years-ago dilution check, fetch 11 rows (or the target FY row)
   so CSX/PCAR-style 10-row windows include FY2015.
3. Tests: stray FY2026 + FY2016 facts → 10 years; CSX/PCAR-style max 2025 →
   FY2015 found; genuine 2017-start company still returns 9 years.
4. Re-run the 30-ticker audit.

**Expected:** Fisher dilution 8 C2 → 0 (all 8 verdicts flip); Graham-Dodd 1 C2
(NEE) → 0; BJRI remains C1-T; share/EPS block shrinks; total → ~45.

### Session 3 — C1-M (2–3 days)

1. Extend the cash-flow, balance-sheet and dividend maps with the exact tags
   from A.7/A.8.
2. Unify `FinancialInsightsService` with the normalized/core fields (or share
   one concept map).
3. Add regression fixtures for VZ, SNY, TD, T, NEE.
4. Re-run the 30-ticker audit and a small cross-source validation.

**Expected:** DCF 14 → ~7; D/E/ROE/FCF/dividend blocks shrink; total → ~20–30.

### Session 4 — display and data-quality (0.5–1 day, separate)

1. Historical P/E/FCF-yield chart: cap/exclude outliers, add caption, keep
   exact values in the table/JSON.
2. Share-selection sanity check (neighbor comparison, 10³/10⁶/10⁹ normalization).
3. Peer-stats winsorization at p1/p99.
4. Tests: TRC 5,659.7 hidden from the chart but present in the table; BTI 2019
   corrected or flagged; normal META/ACN charts unchanged.

### Acceptance criteria for the fix sessions

- Re-run the same 30 tickers with the same collection script; publish a
  before/after table per command, dimension, methodology and ticker.
- No new `N/A` for the seven financials beyond the intended bank/REIT policy.
- No regression in the 2,540 unit tests / 125 API tests.
- The Historical chart is readable for META, ESE, TRC, BTI and a normal ticker
  (ACN); the exact P/E remains available in the table/JSON.
- Every mapping change has a test with the exact FDB concept and value.

---

## Appendix — evidence and code references

### A. Collection

- `/tmp/insufficient_diag/summary.json` — structured results for all 30 tickers
  (30/30, no collection errors).
- `/tmp/insufficient_diag/collect.py` — collection script mirroring the
  scorecard, methodology and DCF services.
- FDB: `FINANCIAL_DATABASE_URL` from `.env`; `core_financials` 336,196 rows;
  `financial_facts_normalized` 18,383,506 rows.

### B. Key code references

| Topic | File / line |
|---|---|
| Scorecard dimension verdict | `backend/services/scorecard_service.py` (`score_rules`, ~line 171) |
| `current_ratio` hardcoded | `backend/services/scorecard_service.py` ~line 568 |
| Interest coverage from rows | `backend/services/scorecard_service.py` `_ic_latest`, ~line 433 |
| FCF CAGR rule | `backend/services/scorecard_service.py` ~line 376 |
| Dividend cover rule | `backend/services/scorecard_service.py` ~line 797 |
| Fiscal-year window | `backend/repositories/fdb_mixins/facts_mixin.py` `_min_fiscal_year`, ~line 181 |
| Cash-flow concept priority | `backend/repositories/fdb_concept_mapping.py` ~line 224 |
| Balance-sheet concept map | `backend/repositories/fdb_concept_mapping.py` ~line 310 |
| Debt priority | `backend/repositories/fdb_concept_mapping.py` ~line 289 |
| Insights equity / D/E | `backend/services/financial_insights_service.py` ~lines 147–150, 239–242 |
| Share selection | `backend/repositories/fdb_mixins/shares_mixin.py` ~lines 61–120 |
| Fisher verdict | `backend/methodologies/fisher_quantitative_subset/methodology.py` `_verdict`, ~line 412 |
| Greenblatt ranking load | `backend/methodologies/greenblatt/methodology.py` `_load_rankings`, ~line 205 |
| Historical P/E calculation | `backend/services/historical_valuation_service.py` ~lines 107–196 |
| Historical chart | `ui/pages/02_analysis.py` `_historical`, ~line 1026; `st.line_chart` ~line 1051 |
| Peer P/E chart | `ui/charts.py` ~line 195; `data/peer_stats/*.json` |

### C. Representative queries

```sql
-- VZ: capex tag exists but is not mapped
SELECT fiscal_year, concept, value
FROM financial_facts f
JOIN company_listings cl ON cl.company_id = f.company_id
WHERE cl.ticker = 'VZ' AND f.fiscal_period = 'FY'
  AND f.fiscal_year BETWEEN 2018 AND 2025
  AND f.concept ILIKE '%ProductiveAssets%'
ORDER BY fiscal_year DESC, concept;

-- SNY: IFRS current assets/liabilities and dividends exist in raw facts
SELECT concept, value
FROM financial_facts f
JOIN company_listings cl ON cl.company_id = f.company_id
WHERE cl.ticker = 'SNY' AND f.fiscal_period = 'FY' AND f.fiscal_year = 2025
  AND (f.concept IN ('CurrentAssets','CurrentLiabilities')
       OR f.concept ILIKE '%Dividend%')
ORDER BY concept;

-- T: NCI equity, operating income and interest exist in raw facts
SELECT concept, value
FROM financial_facts f
JOIN company_listings cl ON cl.company_id = f.company_id
WHERE cl.ticker = 'T' AND f.fiscal_period = 'FY' AND f.fiscal_year = 2025
  AND f.concept IN (
    'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest',
    'OperatingIncomeLoss', 'InterestExpenseNonoperating'
  );

-- Minimum fiscal year and FY2015/2016 facts per ticker
SELECT cl.ticker, MIN(f.fiscal_year), MAX(f.fiscal_year),
       COUNT(*) FILTER (WHERE f.fiscal_year = 2015) AS fy2015,
       COUNT(*) FILTER (WHERE f.fiscal_year = 2016) AS fy2016
FROM financial_facts f
JOIN company_listings cl ON cl.company_id = f.company_id
WHERE cl.ticker IN ('T','VZ','CSX','AMT','PLD','DUK','NEE','PCAR',
                    'SNY','TTE','BTI','RACE','AZN','APA','BRUN')
  AND f.fiscal_period = 'FY'
GROUP BY cl.ticker;
```

### D. Limitations

- The exact P/E 5,600 ticker is not confirmed. The best current match is TRC
  FY2025 (5,659.7); the four real-use tickers do not produce 5,600. A
  screenshot or ticker from the user would close this gap.
- The 30-ticker sample is not the full universe. The 2,451-file cache scan is
  used only for anomaly frequencies, not for the `INSUFFICIENT_DATA` totals.
- Prices come from Yahoo Finance on demand; historical P/E values can change
  slightly with the price source and the split-adjustment factor.
- The `N/A` count for financials is correct by design; it is reported
  separately and is not part of the 104.
- The diagnostic itself made no code or FDB changes. The Session 2a fixes are
  recorded below.

---

## Fixes applied (Session 2a)

Three approved fixes were applied; C4a-2 was explicitly deferred. No FDB
changes, no release.

### C2 — fiscal window

- `_min_fiscal_year` now anchors on the latest **usable** fiscal year
  (`core_financials` with Assets + Equity, same criterion as
  `effective_year`) and falls back to raw `MAX(fiscal_year)` only when the core
  layer has no usable row.
- Dimensions keep 10 rows. `ScorecardService._evaluate_methodologies` and
  `methodology_ranking_service` request **11** rows, so the `latest - 10`
  checks have FY2015.
- Actual flips: **all 8** C2 Fisher cases — T, VZ, CSX, PLD, DUK, NEE, PCAR,
  **AMT**. AMT was not a data gap after the anchor: the 11-row window exposes
  its FY2015 row.
- Graham 8 → 7 (PLD); Graham-Dodd 8 → 6 (NEE, BJRI); Fisher 12 → 4
  (TTE, BRUN, SKT, APA remain C1-T/C5).
- Tests: `tests/unit/test_fiscal_window.py` (anchor, fallback, 11-row
  methodology fetch).
- Known side effect: NEE's extra FY2016 fact changed the tie-break for a
  duplicated FY2020 diluted-EPS fact (0.00 vs 1.48). `eps_cagr_5y` and
  `per_share_accretion` became INSUFFICIENT, but the Growth dimension verdict
  did not change. This is a data-dedup issue to fix with C1-M, not a C2
  failure.

### C4a-1 — `current_ratio`

- New `CurrentRatioCalculator`; `N/A` is a first-class scorecard status,
  excluded from the dimension denominator and from the skipped-evidence
  confidence count.
- Statuses on the 30 tickers: **10 FAIL, 4 WATCH, 7 N/A, 9 INSUFFICIENT**.
  - PASS/WATCH/FAIL for non-banks with a current split (AAPL 0.89 FAIL,
    CAT 1.44 WATCH, MSFT 1.23 WATCH, etc.).
  - N/A for SAN, TD, JPM, BAC, BNS, MRX, AAMI (banks/financials without a
    current/non-current split).
  - INSUFFICIENT for SNY, TTE, BTI, RACE, AZN (IFRS split exists in FDB but VI
    has not mapped it — C1-M), and for PLD/PCAR/BRUN/SKT (no usable split in
    the normalized layer).
- The task's Phase 2.4 text expected N/A for the IFRS names. The implementation
  keeps INSUFFICIENT there because the split **does** exist in FDB and the
  mapping is recoverable; acceptance #7 says INSUFFICIENT when the rule should
  apply and the normalized data is missing. A one-line policy change can switch
  them to N/A if product prefers that.
- `current_ratio` rule statuses fell from 30/30 INSUFFICIENT to 9/30, but **no
  dimension crossed the two-evaluable-rule threshold**: the 34 dimension count
  is unchanged. The remaining dimensions are banks (N/A or industrial rules),
  IFRS (C1-M), and BRUN/SKT/MRX.
- Tests: computed AAPL/CAT ratios, bank N/A, N/A denominator, missing-data
  INSUFFICIENT.

### Display — P/E and shares

- Historical chart excludes `|P/E| > 100` and captions the number of hidden
  years; the table/JSON keep the exact value.
- CLI tables render `n.m.` when `|net income| < 1e6`; JSON remains numeric.
- `HistoricalValuationService` neighbor sanity rejects share counts more than
  100× away from the adjacent years:
  - BTI FY2019: 2,456,520,738,000,000 → 2,456,591,597 (P/E 10.88).
  - COP FY2011: 1,375,035,000,000 → 1,479,330,000 (P/E 5.24).
- Tests: COP/BTI neighbor fallback, TRC `n.m.` table / exact JSON, ±100 chart
  filter.

### Measurement

Baseline **104** = 34 dimensions + 56 methodologies + 14 DCF.

After **93** = 34 dimensions + 45 methodologies + 14 DCF.

- Methodologies: greenblatt 23, graham 7 (−1), graham_dodd 6 (−2), fisher 4
  (−8), lynch 4, marks 1.
- DCF unchanged at 14; C2 did not flip a DCF verdict.
- Tickers that improved most: PLD 3→1, NEE 4→2, T 2→1, VZ 3→2, CSX 2→1,
  AMT 2→1, DUK 3→2, PCAR 2→1, BJRI 3→2.
- The 75–85 estimate was not reached because `current_ratio` alone does not
  flip a dimension: the remaining 34 dimensions are banks/IFRS/BRUN/SKT/MRX,
  where current ratio is N/A by design or still missing (C1-M). The 11-point
  drop is entirely C2. Reaching 75–85 needs C4b (bank/REIT scorecard policy)
  and/or C1-M (mapping), both out of this session.

### Verification

- Unit: **2556 passed, 2 skipped, 0 failed** (2540 baseline + 16 new).
- API: **125 passed, 0 failed**.
- Ruff: **0 errors, 0 format issues**.
- Theme: 26 pass / 4 known metric-card gaps (analysis, screener, reports,
  consensus) — unchanged from baseline.
- Streamlit demo: HTTP **200** on port 8510.

### Pending

- **C4a-2:** deferred; Fisher aggregation lives in
  `backend/methodologies/fisher_quantitative_subset/methodology.py` and needs
  explicit permission to touch it.
- **C4b:** banks/REITs scorecard policy (N/A with reason vs adapted rules).
- **C1-M:** mapping gaps (IFRS current assets/capex/dividends/debt, NCI equity,
  VZ capex, TD dividends).
- **NEE EPS duplicate** (0.00 vs 1.48 FY2020): deterministic dedup in the
  insights path.
- **v0.20.3:** human decision; no release in this session.

---

## C1-M — concept mapping gaps (2026-11-07)

### What changed

| Gap | Cause | Fix |
|---|---|---|
| IFRS current split (SNY, BTI, AZN) | FDB stores unprefixed IFRS concepts; only `AssetsCurrent`/`LiabilitiesCurrent` were mapped | `CurrentAssets` → `current_assets`, `CurrentLiabilities` → `current_liabilities` |
| IFRS net PPE (SNY, AZN) | `PropertyPlantAndEquipment` (carrying amount) unmapped | mapped to `net_ppe` |
| TTE net PPE | FY2025 files only the ROU-inclusive variant | `PropertyPlantAndEquipmentIncludingRightofuseAssets` → `net_ppe` |
| T / AMT / APA net PPE | post-2020 filings use the PP&E + finance-lease ROU tag | `...AfterAccumulatedDepreciationAndAmortization` → `net_ppe` (gross sibling → `ppe_gross`) |
| APA net PPE | the generic net tag is surface assets only (146M) | `CapitalizedCostsOilAndGasProducingActivitiesNet` → `net_ppe` with a balance-field priority so an E&P uses producing properties (12.5B) |
| IFRS debt (SNY, BTI, AZN, TTE) | only US-GAAP debt tags were summed | `CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings` / `ShorttermBorrowings` (current) and `LongtermBorrowings` (non-current) |
| EBIT (JNJ, ADM, PCAR, TTE) | no `OperatingIncomeLoss` tag in the latest filings | `ebit = pretax_income + interest_expense`; pretax alone when interest is absent; last resort `net_income + tax + interest` |
| IFRS pretax / tax / interest | `AccountingProfit`, `ProfitLossBeforeTax`, `IncomeTaxExpenseContinuingOperations`, `FinanceCosts` unmapped | mapped (FinanceCosts ranked after dedicated interest tags) |

The net-PPE concept priority (`BALANCE_FIELD_PRIORITY`) was added because
several balance concepts now map to `net_ppe`: a plain net tag wins over the
ROU-inclusive proxy, and producing oil & gas properties win over a residual
surface PP&E line.

### Measured (30-ticker audit set)

- Greenblatt `INSUFFICIENT_DATA`: **15 → 1** (PCAR).
  - Resolved by mapping + regenerated S&P 500 ranking: JNJ, T, ADM, APA.
  - N/A by design: AMT, PLD, SKT (REITs), TD/SAN/JPM/BAC/BNS (financials),
    SNY, TTE, BTI, RACE, AZN, BRUN, BJRI (outside the S&P 500 ranking universe).
  - PCAR: unclassified balance sheet (large finance subsidiary), so net working
    capital cannot be computed. Documented, not forced.
- IFRS filers now carry current assets/liabilities, net PPE and total debt:
  SNY, BTI, AZN (complete); TTE (complete, EBIT from AccountingProfit +
  FinanceCosts).
- Ranking regenerated: **386** companies (was 284). APA moved from a bogus
  ROC of 2114% (residual 146M PP&E) to 24.6% (12.5B producing properties).

### Still open

- **RACE** (Ferrari) files an unclassified IFRS balance sheet: no
  `CurrentLiabilities` concept, so Greenblatt stays N/A (out of the S&P 500
  ranking anyway).
- **PCAR** unclassified balance sheet — no mapping can invent the split.
- **BRUN / SKT**: too few facts (early-stage / partial REIT data); REIT and
  out-of-universe guards already return N/A.
- **VZ capex**: Verizon files network capex only as
  `PaymentsToAcquireOtherProductiveAssets`; mapped (FY2025 17.0B).
- **TD dividends**: TD Bank files `DividendsPaidClassifiedAsFinancingActivities`;
  mapped (FY2025 7.66B). JNJ's equity already uses the NCI-inclusive subtotal
  from v0.20.2 (81.5B), so no further change was needed there.

### Tests

`tests/unit/test_fdb_ifrs_mappings.py` (10 cases): IFRS split/PPE, IFRS debt,
TTE ROU-inclusive PP&E, US PP&E+ROU variant, EBIT fallback (pretax + interest,
pretax only, IFRS AccountingProfit + FinanceCosts), "filed operating income
wins", VZ network capex and TD bank dividends.
`tests/unit/test_methodology_greenblatt.py` adds the REIT and out-of-universe
N/A cases.

---

## C4b — banks and REITs scorecard N/A (2026-11-07)

### Decision

All six scorecard dimensions return `N/A` with a visible reason for banks,
insurers, capital-markets firms and REITs. No adapted valuation rules.

- financials: "Banks and insurers use different valuation frameworks (no
  current/non-current split, leverage is the business model)".
- REITs: "REIT — rules do not apply (FFO, not net income)".

The guard uses `detect_financial_subtype` on sector **and industry**, so
"Banks - Diversified" resolves to BANK even though the sector is shared with
payment networks and asset managers. V/MA (industry "Credit Services") and BLK
("Asset Management") keep the standard scorecard; DUK/NEE (utilities) keep it
too. Reversible by deleting `_dimension_na_reason`'s guard in
`backend/services/scorecard_service.py`.

### Measured (30-ticker audit set)

| Metric | v0.20.3 | now |
|---|---|---|
| Dimensions `Insufficient` | 34 | **12** |
| Methodology verdicts `INSUFFICIENT_DATA` | 37 | **17** |
| Methodology verdicts `N/A` | 56 | **66** |
| DCF `INSUFFICIENT_DATA` | 14 | 14 |
| **Total (dims + methodologies)** | **71** | **29** |

The remaining dimension gaps are concentrated in BRUN (5, early-stage with
almost no history), plus one each in SNY, TTE, BTI, RACE, AZN, AAMI and BJRI.
Greenblatt is down to 1 (PCAR, documented in C1-M); the other methodology
insufficients are graham 4, graham_dodd 4, fisher 4, lynch 3, marks 1.

Banks/REITs now show `overall = N/A` in the scorecard, CLI and JSON instead of
a misleading "Insufficient data" or a 0-10 score.

---

## Company category visibility (2026-11-07)

The real-usage note "META / ESE / GOOGL: falta la categoría" was a CLI display
gap, not a data gap: Financial-DataBase already had `sector` and `industry` for
all three (and for ACN). `vi company` now prints both, read from
`companies.sector` / `companies.industry` through the new public
`get_company_sector` / `get_company_industry` lookups. No FDB write was needed.

- META → Communication Services · Internet Content & Information
- ESE → Technology · Scientific & Technical Instruments
- GOOGL → Communication Services · Internet Content & Information
- ACN → Technology · Information Technology Services

ACN's Greenblatt `INSUFFICIENT_DATA` disappeared with the regenerated
S&P 500 ranking (C1-M): it now ranks WATCH (ROC 101.4%). ESE is outside the
S&P 500 ranking universe, so Greenblatt returns N/A "ticker not in universe".
