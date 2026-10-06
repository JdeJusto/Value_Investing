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
- Suggested follow-up: a periodic mapping-coverage audit script that lists
  high-coverage FDB concepts missing from the curated mapping.

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
