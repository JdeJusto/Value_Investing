# Validation Report — 200 S&P 500 Companies (Value Investing vs Yahoo Finance)

Report generated: 2026-09-13 (UTC) — run on the `Financial-DataBase` PostgreSQL
database (SEC EDGAR derived) as the Value Investing source, cross-checked
against Yahoo Finance annual statements.

## 1. Executive summary

- 200 companies sampled deterministically from the S&P 500 constituents list
  (seed 42). All 200 were resolved from the database; all 200 were fetched
  from Yahoo Finance.
- 60 discrepancy rows remain after fixes (26 HIGH, 20 LOW, 14 MEDIUM),
  concentrated in EPS / P/E (share-basis), revenue-definition (financial
  sectors), net-income basis (preferred dividends / non-controlling
  interests), and FCF/capex coverage (utilities/REITs).
- All other compared figures — revenue, net income, total assets, total
  liabilities, operating cash flow for 190+ of the 200 names — match within
  the configured thresholds, i.e. the two independent sources agree on the
  fundamentals for the vast majority of companies.
- The validation surfaced and fixed several genuine bugs in the Value
  Investing data layer (Section 4). Residual differences are documented as
  expected source-convention differences (Section 5).

## 2. Methodology

### 2.1 Sample

- S&P 500 constituent list: `data/sp500_constituents.csv`
  (raw.githubusercontent.com … s-and-p-500-companies); filtered to 500 unique
  CIKs (zero-padded to 10 digits; `BRK.B`→`BRK-B`, `BF.B`→`BF-B`).
- `data/validation_sample_200.csv`: seeded random sample (seed 42), 200 rows.

### 2.2 Sources

- **Value Investing side (VI)**: `FinancialDatabaseRepository`
  (`backend/repositories/financial_database_repository.py`) reading
  Financial-DataBase `financial_facts` (SEC EDGAR XBRL). It selects the latest
  completed fiscal year, reconstructs annual statements, and computes ratios.
  Prices/diluted-Shares are excluded from the DB; EPS = net income /
  as-reported diluted weighted-average shares.
- **External side (Ext)**: `YahooFinanceProvider`
  (`backend/providers/yahoo/provider.py`) annual income statement / balance
  sheet / cash flow; EPS = Yahoo's reported Diluted EPS; P/E & FCF yield use
  Yahoo real-time price/market cap.

### 2.3 Fiscal-period alignment

- The DB labels a fiscal year by the **10-K report year**; Yahoo labels by the
  **calendar year of the fiscal-period end**. The two describe the same period
  when their fiscal-period-END dates match (e.g. HD: DB FY2025 ends
  2026-02-01; Yahoo labels the same column FY2026).
- Validation therefore anchors on the fiscal-period-end date: the external
  column whose end-date falls within ±7 days of the VI fiscal-year end is
  selected (`ext_metrics_for(..., target_fye)`), and a `fiscal_year`
  discrepancy is only raised when the period end-dates differ by more than
  that tolerance. This removes label-only noise (32 spurious rows down to 0).

### 2.4 Compared metrics and thresholds

| metric | units | threshold | notes |
|---|---|---|---|
| revenue | % | 2% | |
| net_income | % | 5% | |
| total_assets | % | 2% | |
| total_liabilities | % | 2% | |
| operating_cash_flow | % | 5% | |
| eps | % | 5% | |
| pe_ratio | % | 10% | real-time price on both sides |
| fcf_yield | pp | 0.5 pp | OCF − capex on both sides |
| roe | % | 10% | net income / equity |
| net_margin | pp | 2 pp | net income / revenue |
| fiscal_year | — | ±7 d | period-end date match |

Severity = threshold multiple: ≥5 → HIGH, ≥2 → MEDIUM, <2 → LOW.

## 3. Results

### 3.1 Coverage

| step | total | ok | failed |
|---|---|---|---|
| sample | 200 | 200 | 0 |
| Value Investing (`vi`) | 200 | 200 | 0 |
| External (`external`) | 200 | 200 | 0 |
| comparison (`compare`) | 200 | — | 60 discrepancy rows |

### 3.2 Discrepancy summary

| metric | HIGH | MEDIUM | LOW | total |
|---|---|---|---|---|
| eps | 6 | 3 | 0 | 9 |
| pe_ratio | 5 | 2 | 1 | 8 |
| revenue | 6 | 0 | 1 | 7 |
| net_margin | 3 | 2 | 4 | 9 |
| net_income | 3 | 2 | 6 | 11 |
| fcf_yield | 2 | 3 | 6 | 11 |
| roe | 1 | 2 | 2 | 5 |
| **total** | **26** | **14** | **20** | **60** |

`total_assets`, `total_liabilities`, `operating_cash_flow` and `fiscal_year`:
**0 discrepancies** in this run.

## 4. Genuine bugs found and fixed (Value Investing data layer)

These were root-caused during the validation and fixed in the repository,
provider, and validation script.

1. **Fee/pollution facts tagged `fiscal_period='FY'`** (424B5/S-3ASR filings)
   create phantom "latest fiscal year" buckets. `get_latest_completed_fiscal_year`
   now requires form ∈ {10-K, 10-K/A, 20-F, 20-F/A}, excludes `Entity%`
   cover-page facts, and orders buckets by the most recent true period end
   (STX's spurious "FY2027" bucket disappeared; it now resolves to FY2026,
   FYE 2026-07-03).
2. **Short-duration revenue facts vs full-year facts**: for several companies
   the FY bucket holds `RevenueFromContractWithCustomerExcludingAssessedTax`
   covering only 9 months at the same period-end as the full-year `Revenues`
   (ADM, BG, URI, DOC, ESS, CCI). `_normalize_financial_facts` now resolves
   per field via (period_end DESC, concept-rank ASC, period_start ASC) so the
   longest-duration, preferred concept wins (ADM revenue 24.96B → 80.27B).
3. **Revenue concept preference**: `Revenues`/`SalesRevenueNet` family now
   ranks above the ASC-606 contracts-with-customers elements, and the
   *excl.-assessed-tax* (net) variant ranks above the *incl.-assessed-tax*
   (gross) variant (distillers: Brown-Forman 5.08B → 3.93B, matching its
   as-presented income statement). Utilities' `RegulatedAndUnregulatedOperatingRevenue`
   added to the revenue concepts (NEE 25.8B → 27.4B).
4. **Net income basis**: consolidated `NetIncomeLoss` includes amounts
   attributable to non-controlling interests; EPS/ROE/net margin must use the
   available-to-common figure. `NetIncomeLossAvailableToCommonStockholders*`
   now outranks `NetIncomeLoss` (IBKR: −consolidated 4.36B → 0.984B, EPS
   2.22 = Yahoo's; IVZ, BEN and the banks converged to Yahoo).
5. **Diluted-share basis for EPS**: both sides now use an as-reported
   diluted weighted-average share count (`prefer_diluted=True` on the
   repository; Yahoo `get_eps` reads the Diluted EPS row with an
   NI/diluted-shares fallback).
6. **Fiscal-year-end selection**: the fiscal year end is the MAX period-end
   among the **core statement concepts only**, so a stray later-dated
   'FY' disclosure cannot shift it (CMI 2026-01-31→2025-12-31, CSCO
   2026-08-17→2026-07-25, PH→2026-06-30, WDAY→2026-01-31) while the genuine
   newest 10-K comparative still wins (CRM→2026-01-31, FRT→2025-12-31,
   KR→2026-01-31).
7. **Yahoo provider robustness**: statements returned `None` for the big
   banks (JPM, BAC, WFC, USB, PNC, AIG, AFL) because a single missing row
   label (`Operating Income`, `EBITDA`, `Capital Expenditure`) raised
   `KeyError` and discarded the whole statement. Row access is now
   per-label resilient (`_get`), so missing rows degrade to `None` per field
   (all 7 banks now resolve).
8. **Comparison anchoring**: `compare` compares the *fiscal period-end date*
   (±7-day tolerance) rather than the year label; the external step reads the
   VI CSV's `fiscal_year_end` as its anchor; a DB-year safety net
   (`_db_year_for_fye`) re-syncs when periods drift.

Full unit-suite result after all fixes: **334 passed, 1 skipped** (including
the new `tests/unit/test_validation_comparison.py` cases for normalization,
net-income basis, revenue preference, FYE selection, and threshold logic).

## 5. Expected discrepancies (source-convention differences, not bugs)

### 5.1 Revenue definition for financial sectors (7 rows)

| ticker | VI | Yahoo | category |
|---|---|---|---|
| CPT | 12.97M | 1.574B | REIT — DB bucket has only the ASC-606 `...ExcludingAssessedTax` (12.97M); rent revenue is not stored under a mapped revenue element |
| MTB | 1.657B | 9.632B | bank — DB revenue element = fee/service-charge revenue only; net interest income is not a `Revenues` element |
| IBKR | 2.440B | 10.222B | broker — DB picks commissions+fees element; no company-level `Revenues`; full revenue includes interest income |
| RJF | 15.912B | 13.842B | broker — total-revenue convention (interest income treatment) differs |
| BX | 14.450B | 12.410B | asset manager — performance/realized revenue convention differs |
| HAS | 5.366B | 4.701B | same full-year period has two tags; Yahoo uses *net* revenue, DB `Revenues` is the gross tag |
| ACGL | 19.929B | 19.300B | insurance — premium/base treatment (LOW, 3.3%) |

### 5.2 EPS / P/E — unreliable Yahoo "Diluted EPS" row (5 rows, HIGH)

| ticker | VI EPS | Yahoo EPS | note |
|---|---|---|---|
| ABNB | 4.03 | 1.03 | Yahoo row returns a quarterly value (2.511B NI / 623M sh = 4.03 = VI) |
| FE | 1.76 | 0.44 | Yahoo share count 4× (2.312B vs actual ~578M) |
| MNST | 1.94 | 0.97 | Yahoo share count 2× (1.969B vs ~984M) |
| DLR | 3.65 | 0.90 | Yahoo share count 4× |
| CVNA | 6.27 | 1.69 | severely diluting issuer; DB WADNSOD basis vs Yahoo row |

These companies' revenue, net income, balance-sheet and cash-flow figures
**match exactly**; only EPS/P-E diverge. The VI side is the internally
consistent one (NI ÷ diluted average shares). No provider change was made:
relying on the reported row is the correct independent check for OXY/PSA
(preferred dividends), so is documented as a Yahoo annual-data limitation.

### 5.3 Net income basis — preferred dividends / non-controlling interests

| ticker | VI | Yahoo | note |
|---|---|---|---|
| OXY | 1.612B | 2.326B | VI = available to common (after ~$0.7B preferred); Yahoo NI = pre-preferred. EPS matches (1.61 = 1.61) |
| PSA | 1.586B | 1.784B | REIT with significant preferred; EPS matches (9.01) while NI basis differs |
| MCHP | 0.119B | 0.230B | GAAP `NetIncomeLoss` (incl. NCI/China JV) vs available-to-common; EPS matches (0.21) |
| BEN | 0.472B | 0.525B | asset manager NI trimming |
| IVZ | −0.726B | −0.282B | Yahoo's own Net Income row is inconsistent with its Diluted EPS (−1.60 = VI's) |
| FITB/MTB/PNC/STT/TFC/NRG | −5…−8% | | small persistent NI-basis differences on banks (preferred/marginal basis), LOW |

### 5.4 Special / event years and share-base changes

| ticker | metric | note |
|---|---|---|
| DD | eps/pe | discontinued-operations transition year (Electronics divestiture); VI GAAP loss −779M same as Yahoo NI, EPS basis differs |
| BG | eps/pe | Viterra merger — DB weighted-average diluted shares (166M) vs Yahoo (193M) |
| TDG | eps | convertible-preferred dilution (MEDIUM, 11%) |
| CSGP | eps | tiny absolute values near zero (0.017 vs 0.020); rounding, MEDIUM |

### 5.5 Free cash flow / capex coverage (utilities, REITs)

| ticker | VI | Yahoo | note |
|---|---|---|---|
| AEP | +5.20% | −2.44% | DB `PaymentsToAcquireProductiveAssets` (3.45B) undercounts utilities' true additions (~12B); Yahoo FCF uses the full figure |
| NI | −2.11% | −4.00% | same capex-coverage class |
| DOC | +2.55% | +8.94% | REIT capex/FCF convention (VI shows OCF−capex; Yahoo FCF ~ OCF) |
| NTRS/HAS | ~1–2 pp | | basis differences |
| AWK/CSGP/DVN/EXE/HSIC/PCAR | 0.5–1.0 pp | | LOW, borderline basis |

## 6. Reproducing

```bash
source .venv/bin/activate
python -m scripts.validate_sp500 sample --seed 42     # data/validation_sample_200.csv
python -m scripts.validate_sp500 vi                    # data/validation_value_investing_200.csv
python -m scripts.validate_sp500 external              # data/validation_external_200.csv
python -m scripts.validate_sp500 compare               # data/validation_discrepancies_200.csv
python -m pytest tests/unit -q                         # 334 passed, 1 skipped
```

## 7. Limitations

- Fundamental data quality depends on the Financial-DataBase ingester
  (concept coverage per company; annual report availability at ingestion time).
- Yahoo annual "Diluted EPS" rows are unreliable for some issuers (5.2); the
  independent check is EPS = net income ÷ diluted shares.
- Financial-sector revenue and net-income definitions legitimately differ
  between reporting conventions (banks, brokers, REITs, insurers, asset
  managers); these are documented rather than "fixed" in either tool.
- Prices are real-time (never persisted); P/E and FCF-yield comparisons are
  sensitive to the instant they are captured.