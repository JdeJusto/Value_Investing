# Data gaps investigation — COLD and the REIT concept mapping

Date: 2026-10-06. Scope: Financial-DataBase (read-only inspection) plus the
Value Investing mapping, insights and filing-parser fixes. Every database
access here is a read; the only writes are the VI code changes below.

## COLD (Americold Realty Trust)

- CIK: `0001455863`
- Facts in FDB: **14,576**
- Distinct concepts: **542**
- Fiscal year range: **2018–2026**
- **Root cause: Case 5 — structural REIT concept gaps in the VI mapping, not
  an FDB ingestion gap.** FDB holds the full statements; VI did not map
  several tags COLD files.

### Evidence

FDB has plenty of data (query details in `## Universe survey`), and the
Analysis page loads 501 facts across 8 fiscal years. The visible gaps were
fields whose XBRL tags were missing from
`backend/repositories/fdb_concept_mapping.py`:

| Field / metric | Tag filed by COLD | In FDB facts | Mapped before |
| --- | --- | --- | --- |
| `pretax_income` | `IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest` | yes (FY, -135.7M) | no |
| `interest_expense` | `InterestExpenseNonoperating` | yes (FY, 147.8M) | no |
| `operating_expense` | `CostsAndExpenses` (REIT total operating costs) | yes (FY, 2,594.6M) | no |
| `total_debt` | `SecuredDebt` (mortgage/notes debt) | yes (FY, 3,792.1M) | no |
| Insights Gross Profit / Gross Margin | no `GrossProfit` tag; `CostOfRevenue` present | yes | derivation existed only in the repository, not in insights |

`current_assets` / `current_liabilities` stay empty because COLD (like most
REITs) files an **unclassified balance sheet**: no `AssetsCurrent` /
`LiabilitiesCurrent` facts exist in FDB. That is structural and not a
mapping gap.

### Statements tab (filing preview)

`filing-statement COLD --type income_statement` returned the **balance
sheet**. Root cause: COLD labels its bottom line `Net (loss) income`, which
contains neither `net income` nor `net loss`, so the real income-statement
table matched none of the required pairs. Meanwhile the balance-sheet table
matched `["net earnings", "revenue"]` by accident and, being larger, won the
"largest matching table" fallback.

## COLD before / after the fix

| Item | Before | After |
| --- | --- | --- |
| `pretax_income` (FY2025) | — | -135,733,000 |
| `interest_expense` (FY2025) | — | 147,776,000 |
| `operating_expense` (FY2025) | — | 2,594,612,000 |
| `total_debt` (FY2025) | — | 3,792,123,000 |
| Insights Gross Profit | — | $839,386,000 |
| Insights Gross Margin | — | 32.3% |
| Insights Operating Expenses | — | $2,594,612,000 |
| Insights Total Debt | $2,648,266,000 (stale FY2024 tag) | $3,792,123,000 (FY2025) |
| Insights Debt-to-Equity | 0.70 (FY2024) | 1.31 (FY2025) |
| `filing-statement --type income_statement` | balance sheet (46 lines) | income statement (35 lines) |

## Universe survey

Fact-count distribution across active listings:

| Bucket | Companies |
| --- | --- |
| `high` (≥ 10,000 facts) | 2,963 |
| `medium` (2,000–9,999) | 2,414 |
| `zero_facts` | 1,101 |
| `low` (500–1,999) | 730 |
| `very_low` (1–499) | 668 |

Low-data companies by sector: `(none)` 1,105, Financial Services 726,
Industrials 150, Healthcare 128, Technology 125, … Real Estate 15. The
`low`/`very_low` buckets are dominated by closed-end funds/trusts and recent
registrants: the five sampled companies (JHI, HBNB, AERO, PICS, PAYP) have
exactly **one** fact each (a cover-page share count or a fund metric), i.e.
statements were never filed/ingested. That is a different situation from
COLD and is expected for those vehicles.

REIT peers are all richly populated, so COLD is not an ingestion outlier:

| Ticker | Company | Facts |
| --- | --- | --- |
| AMT | American Tower | 32,626 |
| PLD | Prologis | 23,429 |
| SPG | Simon Property Group | 21,727 |
| O | Realty Income | 21,703 |
| COLD | Americold | 14,576 |

### Concepts present in FDB but unmapped (added by this fix)

| FDB concept | Companies | Years | Mapped to |
| --- | --- | --- | --- |
| `IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest` | 4,965 | 19 | `pretax_income` |
| `InterestExpenseNonoperating` | 2,308 | 6 | `interest_expense` (fallback after `InterestExpense`) |
| `CostsAndExpenses` | 1,497 | 21 | `operating_expense` (fallback after `OperatingExpenses`) |
| `SecuredDebt` | 466 | 19 | `total_debt` (ranked last) |
| `RealEstateRevenueNet` | 105 | 13 | `revenue` |
| `OperatingLeaseIncome` | 63 | 9 | `revenue` |
| `RentalRevenue` | 0 (no facts yet) | — | `revenue` (parity with the REIT family) |

`InterestIncomeExpenseNet` and `NoninterestIncome` were already handled by
the bank revenue reconstruction in `normalization_mixin.py`, so they were
left as-is.

Note: ~7,364 of the concepts stored for ≥ 20 companies are note/segment/
disclosure tags, not primary statement lines; a blanket mapping would mix
components into totals and is deliberately avoided.

## Fix applied

- `backend/repositories/fdb_concept_mapping.py` (commit `a92d1ea`): the
  aliases above plus priority lists for `interest_expense` and
  `operating_expense` so the primary tags keep winning.
- `backend/services/financial_insights_service.py` (commit `bcb3682`): the
  Summary panel now derives Gross Profit as `revenue - cogs` when no
  `GrossProfit` tag is filed, mirroring the repository.
- `backend/services/financial_statement_parser.py` (commit `7777b55`):
  per-type statement titles are preferred among matching tables, the
  `Net (loss) income` label is recognised, and `PARSER_VERSION` was bumped
  to 2 to invalidate the wrong cached parses.

## Known remaining limitations

- `current_assets` / `current_liabilities` / `working_capital` remain empty
  for unclassified balance sheets (COLD). No facts exist; not fixable by
  mapping.
- `total_debt` from `SecuredDebt` understates COLD's carrying amount
  (~3.79B vs 4.14B, which includes unsecured notes tagged only in note
  disclosures under `DebtInstrumentCarryingAmount`). Mapping the latter is
  unsafe because many filers tag it per instrument.
- `InterestPaidNet` (4,711 companies, cash-paid interest) was not added to
  `interest_expense` to avoid mixing accrual and cash concepts.

## Systematic coverage batch (2026-10-06)

The COLD case was generalized with `scripts/audit_concept_coverage.py`
(top 300 concepts, >= 50 companies). Before the batch: 42/300 concepts mapped
and 12 actionable concepts unmapped. The 17-concept batch added:

- **Bank revenue**: `RevenuesNetOfInterestExpense` plus
  `InterestIncomeOperating` / `InterestAndDividendIncomeOperating` (gross
  interest is netted with interest expense to reconstruct the bank top line).
- **Income fallbacks**: `GeneralAndAdministrativeExpense` (sga),
  `OtherNonoperatingIncomeExpense` (non-operating),
  `IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterest...`
  (pretax), `IncomeLossFromContinuingOperations` (net income, last).
- **Unclassified balance sheets**: `LiabilitiesAndStockholdersEquity`
  (total-assets identity fallback), `AccountsReceivableNet`,
  `AccountsPayableAndAccruedLiabilitiesCurrent`,
  `WeightedAverageNumberOfDilutedSharesOutstanding`,
  `WeightedAverageNumberOfShareOutstandingBasicAndDiluted`,
  `LongTermDebtCurrent` (current debt portion).
- **PP&E**: `PropertyPlantAndEquipmentGross` minus accumulated depreciation
  derives `net_ppe` when no net tag is filed.
- **Buybacks**: `PaymentsForRepurchaseOfCommonStock`,
  `StockRepurchasedDuringPeriodValue`.

Companies that gain coverage (filed only the new tag): repurchase +3,240,
sga +3,092, non-operating +1,430, current debt +1,022, accounts payable +536,
accounts receivable +301, pretax +162, net PP&E +20, shares +12. After the
batch the audit reports **actionable coverage 100%** (54/300 concepts mapped,
0 actionable unmapped, 246 informational note/disclosure tags).

## Periodic coverage audit

Run periodically to detect new XBRL concepts that Financial-DataBase gains
while the mapping does not cover them yet:

```bash
python -m scripts.audit_concept_coverage --top 300 --min-companies 50
```

The script is read-only, prints the sample table and writes the full report
to `docs/concept_coverage_audit.md`. It exits 0 when *actionable* coverage
(concepts with a known target field) is >= 95% and, when given,
`--fail-if-unmapped N` holds; `--no-gate` reports without enforcing.
Informational note/disclosure concepts have no target field and are reported
but not gated.

Latest run (2026-10-06, after the 17-concept batch): **54/300 concepts mapped,
actionable coverage 100%, 246 informational note/disclosure tags**.

Recommended cadence: monthly, or after each large `sec sync` run.

## Cross-source expected differences (monthly data-quality audit)

`scripts/audit_data_quality.py` compares Financial-DataBase fundamentals with
SEC EDGAR (and, optionally, Yahoo Finance) and classifies each difference. It is
the *why* companion to `scripts/validate_data_sample.py` (the *does it differ*
one). Run it with:

```bash
python -m scripts.audit_data_quality --sample 50 --sources sec,yahoo --out logs
```

Artifacts land in `logs/audit_data_quality_<YYYY-MM-DD>.{log,json,csv}`. Exit `0`
means "only expected differences", `1` means at least one `DATA_ERROR_FDB` (the
DB value traces to no SEC filing at all — a genuine defect), `2` means the audit
could not run. See `docs/runbook_daily.md` for the monthly cadence.

Baseline run — **2026-10-17**, 50 companies, 744 comparisons:

| Classification | Count | Meaning |
| --- | ---: | --- |
| `MATCH` | 658 | within tolerance (or a cash-flow sign convention) |
| `DIFFERENT_TAG` | 27 | the DB value is real but filed under another XBRL tag |
| `DIFFERENT_PERIOD` | 5 | the two sources anchor on different fiscal periods |
| `DATA_ERROR_EXTERNAL` | 10 | Yahoo contradicts a value SEC confirms |
| `UNCLASSIFIED` | 35 | no heuristic applies — manual review |
| `SKIPPED` | 9 | the SEC filing does not tag the line |
| **`DATA_ERROR_FDB`** | **0** | no database defect found |

**`DATA_ERROR_FDB` was zero across all 744 comparisons** — every flagged
difference below is a *definitional* one, and none of it is a bug in the
Financial-DataBase mapping.

### Expected difference classes, by root cause

1. **Revenue tag retired after ASC 606.** `Revenues` / `SalesRevenueNet` stopped
   being filed around 2018 while their old facts remain, so the audit's
   preferred tag returns a stale value and the classifier resolves it against
   `RevenueFromContractWithCustomerExcludingAssessedTax` (or the
   `...IncludingAssessedTax` variant). 16 of the 50 companies (AVGO, BALL, BEN,
   CCL, CRM, CTAS, JKHY, LUV, META, NEM, NOW, RMD, STLD, UNP, …) — all
   `DIFFERENT_TAG`, all expected. The classifier only accepts an alternative tag
   whose own period matches the audited fiscal year (a drift beyond
   `PERIOD_SHIFT_DAYS`, 400 days, is not a period artifact), so a retired tag can
   no longer hide a genuinely wrong value as `DIFFERENT_PERIOD`.
2. **Net-income attribution.** FDB matches
   `NetIncomeLossAvailableToCommonStockholdersBasic` where the preferred
   `NetIncomeLoss` fact is stale or absent (AEE, AEP, BALL, BEN, MET) — expected.
3. **CapEx and dividend-per-share tag variants.** `PaymentsToAcquireProductiveAssets`
   instead of `PaymentsToAcquirePropertyPlantAndEquipment` (CBRE, LUV) and
   `CommonStockDividendsPerShareCashPaid` instead of `...Declared` (AVGO, BALL,
   NEM) — expected.
4. **Shares outstanding is a market-data field, not an SEC one.** The 27
   `UNCLASSIFIED shares_outstanding` rows are the largest bucket and are *not*
   an FDB defect: FDB's `shares_outstanding` is a point-in-time market figure
   (see AGENTS.md — shares come from market data, aligned by
   `PriceService.get_split_adjustment`), while the SEC side is the 10-K share
   count. Two visible sub-patterns:
   - when the undimensioned `CommonStockSharesOutstanding` fact is absent the
     audit falls back to `CommonStockSharesIssued`, which includes treasury
     stock, so the gap is large (AZO 33.0%, BALL 59.7%, DOW 10.0%, GWW 56.2%,
     HAS 36.4%, JKHY 31.1%, LUV 37.2%, PSX 38.1%);
   - otherwise the drift is small (< 13%) and reflects the vintage difference
     (10-K cover/balance-sheet date vs the market-data date) and, for
     multi-class issuers, `companyfacts` carrying only one undimensioned class
     (AFL 3.1%, AIG 6.0%, AVGO 2.4%, AXON 2.7%, CPRT 2.7%, CRH 4.2%, CRM 2.9%,
     D 2.7%, EXPE 12.8%, HSIC 5.1%, LIN 7.2%, MET 2.7%, ON 3.8%, PFG 3.8%,
     PLTR 7.3%, RJF 4.3%, STLD 2.4%).
5. **A zero or partial SEC fact for an aggregate line.** AEP's
   `PaymentsToAcquirePropertyPlantAndEquipment` is filed as `0` for FY2025
   (capex sits under another tag) and CPT's
   `RevenueFromContractWithCustomerExcludingAssessedTax` carries a component
   (`12.97M` vs FDB's `1.57B` consolidated). Both `UNCLASSIFIED`, both expected
   concept-granularity differences.
6. **Period shifts.** 5 rows where one side is exactly one fiscal year back: the
   Yahoo side for CPRT (total liabilities, operating cash flow, capex) and the
   SEC comparative facts for AVGO (net income) and TT (shares outstanding).
   `DIFFERENT_PERIOD`, expected.
7. **`SKIPPED`, never guessed.** 9 rows where the SEC filing simply does not tag
   the line — diluted EPS (ABNB, CRM, FE, PEP, TT), dividends per share (AEE,
   CRM) and shares outstanding (ABNB, META). The audit reports the gap instead
   of inventing a comparison.
8. **Yahoo-side artifacts.** 10 `DATA_ERROR_EXTERNAL` rows (revenue x3, net
   income x2, capex x5) where Yahoo disagrees with a value SEC confirms. Action
   is "none, log": the FDB side is the corroborated one.

### Two endpoint findings uncovered by the first run

- **`companyconcept` returns an empty envelope for some issuers.** For one of the
  50 companies (CIK 0001126328) the per-tag endpoint answered `200` with
  `units: {"USD": {}}` — no facts at all — for every tag while `companyfacts`
  held them. Reading that emptiness as "no filing carries the figure" invented
  4 `DATA_ERROR_FDB` rows (Coca-Cola, CIK 0000021344, showed the same shape in
  the pre-fix smoke run). `SecFallbackFetcher` now switches such an issuer to
  `companyfacts` once and records the substitution in the report's `notes`.
- **A retired tag is not a period artifact.** See root cause 1 above; the
  400-day `PERIOD_SHIFT_DAYS` window was added with the same commit.

### Follow-ups (documented, not fixed here)

- Prefer the tag that is still being filed (ASC 606 revenue, common-stockholder
  net income) in `AUDIT_METRICS`' tag order, which would turn the largest
  `DIFFERENT_TAG` bucket into `MATCH` without losing the evidence.
- Add `dei:EntityCommonStockSharesOutstanding` to the shares metric (the
  `companyfacts` client reads only the `us-gaap` taxonomy) or mark
  `shares_outstanding` informational, since FDB does not source it from SEC.
- Treat a `0`-valued SEC annual fact for a derived/aggregate metric as "not
  usable" rather than as a value.
- `scripts/validate_data_sample.py` still polls `companyconcept` per tag; it can
  now reuse `SecFallbackFetcher` so empty-envelope issuers stop reading as
  missing SEC values.


## Balance T-view limitations (v0.19.2)

After Fix B (alias + resolution rules) and Fix C (76 demo Financials
payloads regenerated for every ticker in the offline bundle), the following
are known limitations. Each entry has cause and recommended action.

### BDX — Double-counted deferred tax
- **Observed:** The balance chip shows an unbalanced delta (≈ −$2.48B) for
  BDX despite ≥10 lines per column in the T-view.
- **Cause:** A deferred-tax note is double-counted in the aggregates that
  Financial-DataBase stores separately (the reported subtotals do not equal
  the sum of the stored components). The Fix-B mapping renders the face
  lines correctly but cannot reconcile that upstream aggregation.
- **Action:** Documented and accepted for v0.19.2. A containment rule or
  per-ticker hack was rejected; investigate if user feedback makes it
  material.

### FDB-limited (4 tickers: APA, APO, ARES, BRK-B)
- **Observed:** The balance concept map resolves the XBRL tags that exist in
  the filing, but the T-view cannot render full face lines for these
  tickers.
- **Cause:** The tags exist in the 10-K/filing but are **not stored in
  Financial-DataBase** (ingestion gap). VI cannot create facts that FDB does
  not hold.
- **Action:** Open an upstream FDB ticket to ingest the missing concepts.
  No local mapping or synthetic data added.

### AEE — Unverified
- **Observed:** The 10-K R-file for AEE could not be located during the
  investigation.
- **Cause:** Unknown; needs manual verification against the SEC filing
  source.
- **Action:** Verify against the original filing and, if the tags exist,
  file an FDB ingestion request. Documented for v0.19.2.

### AAPL — Commercial paper trade-off
- **Observed:** The T-view renders correctly and the chip is balanced, but
  an aggregate rule hides a commercial-paper sibling line.
- **Cause:** The aggregate presentation rule groups the sibling under the
  subtotal that is actually present, so the line is hidden while the subtotal
  still covers it.
- **Action:** Accepted trade-off (demo ≡ live parity maintained). No
  per-ticker override.

### Unbalanced but visible (27 tickers)
The following tickers show ≥10 lines per column in the T-format balance
view but the balance chip reports "does not balance". Causes: aggregates
Financial-DataBase stores separately, or reported subtotals not matching the
sum of stored components. The chip is **honest** (no fabricated rows).

**List (27):** ABBV, ACN, ADSK, AEE, AES, ALB, AMGN, AMT, APA, APD, APO,
APTV, ARE, ARES, AVY, AWK, AZO, BBY, BDX (−$2.48B), BEN, BG, BIIB, BLK,
BRO, JNJ (−$151.25B), PLD, XOM.

**Action:** Acceptable for v0.19.2. Investigate in a dedicated session if
user feedback shows the chip confusion is material. No balance-fabrication
rules added.
