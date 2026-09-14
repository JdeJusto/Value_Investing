# Validation Methodology — S&P 500 Cross-Check

How `scripts/validate_sp500.py` checks the Value Investing data layer against
an independent external source (Yahoo Finance), and how to interpret the
resulting `data/validation_discrepancies_200.csv`.

Applies to the *full* run too: the script steps are parameterized, and the
sample is `data/validation_sample_200.csv` (200 rows, seed 42).

## 1. Pipeline

```
sample   -- deterministic sample of S&P 500 constituents (seed 42)
vi       -- compute Value Investing metrics from Financial-DataBase
external -- fetch the same metrics from Yahoo Finance
compare  -- align fiscal periods, flag discrepancies, apply exclusions
```

Run order:

```bash
python -m scripts.validate_sp500 sample --seed 42
python -m scripts.validate_sp500 vi
python -m scripts.validate_sp500 external
python -m scripts.validate_sp500 compare
```

Outputs:

| step | file |
|---|---|
| sample | `data/validation_sample_200.csv` |
| vi | `data/validation_value_investing_200.csv` |
| external | `data/validation_external_200.csv` |
| compare | `data/validation_discrepancies_200.csv` |

## 2. Sources and fiscal-period alignment

- **VI side** reads SEC EDGAR XBRL facts through
  `FinancialDatabaseRepository` (`backend/repositories/financial_database_repository.py`).
  Only annual ('FY') facts of the latest completed fiscal year are used; the
  fiscal year end is the MAX `period_end` among the **core statement
  concepts** (one-off 'FY' disclosures, fee schedules, `Entity%` cover-page
  facts are excluded).
- **External side** reads Yahoo Finance annual statements through
  `YahooFinanceProvider`.
- The DB labels a fiscal year by its **10-K report year**; Yahoo labels by the
  **calendar year of the period end**. The two describe the same period when
  their period-END dates match. `compare` anchors on the period-end date
  (`FYE_TOLERANCE_DAYS = 7`): a `fiscal_year` discrepancy is only raised when
  the period-end dates differ beyond that tolerance, and a DB-year safety net
  (`_db_year_for_fye`) re-syncs drifting periods.

## 3. Metrics and thresholds

| metric | units | threshold | comparison |
|---|---|---|---|
| revenue | % | 2% | relative difference |
| net_income | % | 5% | relative difference |
| total_assets | % | 2% | relative difference |
| total_liabilities | % | 2% | relative difference |
| operating_cash_flow | % | 5% | relative difference |
| eps | % | 5% | relative difference |
| pe_ratio | % | 10% | relative difference (real-time price both sides) |
| fcf_yield | pp | 0.5 pp | absolute difference in percentage points (stored as decimal fraction) |
| roe | % | 10% | relative difference |
| net_margin | pp | 2 pp | absolute difference in percentage points |
| fiscal_year | — | ±7 days | period-end date difference |

Severity buckets are multiples of the threshold: ratio ≥5 → HIGH, ≥2 →
MEDIUM, <2 → LOW.

VI-side conventions: EPS = available-to-common net income (diluted basis when
the diluted attribution is filed, otherwise basic available-to-common) ÷
as-reported diluted weighted-average shares; FCF = OCF − capex (with direct
`FreeCashFlow` preferred); ROE = net income / stockholders equity; net margin
= net income / revenue.

## 4. Concept-choice rules (revenue / net income / capex)

Revenue (highest rank wins):

1. `Revenues`, `Revenue`, `SalesRevenueNet`, `SalesRevenueGoodsNet`,
   `SalesRevenueServicesNet` (full-year preferred over short-duration facts at
   the same period end).
2. `RevenueFromContractWithCustomerExcludingAssessedTax` (net) ranks above the
   grossed-up *including*-assessed-tax variant.
3. Utilities: `RegulatedAndUnregulatedOperatingRevenue`.
4. `OperatingLeaseLeaseIncome` (*REIT rental income*) ranks last and is used
   as revenue only via a **value-based override**: it wins when it exceeds the
   contract-revenue tag, i.e. it is the whole top line (CPT 1,574M vs 13M
   contract tag). A small side rental never shadows a genuine contract-revenue
   figure (DD 6,849M sales vs 74M rental).
5. **Bank pair override**: when both `InterestIncomeExpenseNet` and
   `NoninterestIncome` are present, revenue = their sum. This reconstructs the
   net-of-interest top line for banks/brokers that file no `Revenues` element
   (RJF, MTB, IBKR, WFC, TFC, FITB). A single component alone never triggers
   it.

Net income: `NetIncomeLossAvailableToCommonStockholdersBasic` outranks
consolidated `NetIncomeLoss` (removes non-controlling interests). Diluted EPS
uses `NetIncomeLossAvailableToCommonStockholdersDiluted` when filed, anchored
to the fiscal-year `period_end` (a comparative prior-year column mislabeled
under the wrong `fiscal_year` must not be picked up).

Capital expenditure (highest rank wins):

1. `PaymentsToAcquirePropertyPlantAndEquipment`
2. `SegmentExpenditureAdditionToLongLivedAssets`
3. `PaymentsToAcquireProductiveAssets`
4. `PaymentsForConstructionInProcess`
5. `CapitalExpenditures`
6. `CapitalExpenditure`

## 5. Exclusion rules (`config/validation_exclusions.yaml`)

Discrepancies that are root-caused are not silently dropped: they are recorded
as rules so `compare` reproduces the same decision on every run.

Format (a minimal YAML subset the script parses itself — no PyYAML
dependency):

```yaml
validation_exclusions:
  - ticker: ABNB
    metric: eps            # or "*" for every metric of the ticker
    classification: EXTERNAL_SOURCE_ERROR
    reason: "free-text note"
```

Matching: a discrepancy row is marked `EXCLUDED` (and its `classification` and
`exclusion_reason` filled) when a rule matches its `(ticker, metric)`. The
`metric` value `*` matches any metric. Matching rows keep their original
severity recorded in the summary counts (e.g. "MEDIUM excluded: 1").

Classifications:

| classification | meaning |
|---|---|
| EXTERNAL_SOURCE_ERROR | external source (Yahoo) reports a value that does not match the as-filed figure; VI reproduces the filing |
| EXPECTED_DIFFERENCE | both sides correct but use a different accounting/definitional convention (REIT vs utility FCF; gross vs net revenue) |
| BUG_IN_VALUE_INVESTING | VI computed the metric wrong — fixed in code; rule kept only when the metric can still diverge for another reason |
| BUG_IN_FINANCIAL_DATABASE | Financial-DataBase ingestion is wrong |
| UNCERTAIN | root cause not yet determined |

Rules must never be added just to silence noise; each needs a `reason` that
explains the root cause.

## 6. Known expected differences

- **Financial-sector revenue**: banks/brokers present a net-of-interest top
  line; insurers use premium/base conventions; asset managers' realized/
  performance revenue differs by source (BX, IBKR have Yahoo-side errors; HAS
  is a permanent gross-vs-net convention).
- **EPS share basis**: diluted available-to-common NI ÷ diluted weighted
  average shares is the as-filed basis; Yahoo's annual Diluted EPS row is
  unreliable for some issuers (4×/2× share counts, quarterly values: ABNB, FE,
  MNST, DLR, CVNA, DD).
- **Net income basis**: preferred dividends / non-controlling interests
  (OXY, MCHP, IVZ, PSA, banks) make Yahoo's Net Income row inconsistent with
  its own EPS row.
- **FCF / capex**: REITs and utilities commonly diverge because sources
  disagree on whether to deduct acquisition/development spend and how to treat
  construction-in-progress (DOC is a REIT-convention difference; AEP/LNT are
  Yahoo capex/OCF errors).

## 7. Re-running and current status

Current run (200-sample): 60 discrepancy rows — 0 HIGH, 16 MEDIUM, 22 LOW,
22 EXCLUDED. See `docs/validation_report_200_sp500.md` for the breakdown and
the full classification of every excluded row. The repo's `AGENTS.md` policy
requires validations to respect `config/validation_exclusions.yaml`.