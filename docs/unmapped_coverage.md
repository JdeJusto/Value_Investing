# Unmapped revenue coverage (2026-09-30)

Investigation of the companies that show no revenue in the platform because
no fact matches the revenue concepts the repository maps. Run as Phase D of
the v0.1.0 hardening session; no data was modified.

## Method

1. Counted companies (active listing) with no fact under any of the revenue
   concepts the repository maps, in SQL (concept union from
   `INCOME_STATEMENT_CONCEPTS` plus the bank pair `InterestIncomeExpenseNet` /
   `NoninterestIncome`).
2. Sampled 20 analyzable companies (non-OTC) at random and cross-checked 8 of
   them against the SEC `companyfacts` API (us-gaap and ifrs-full taxonomies)
   and against the facts Financial-DataBase already stores.
3. Classified each checked company as *genuine gap* (SEC has no revenue
   concept), *mapping gap* (SEC/FDB have a revenue concept the repository
   does not map) or *ingestion gap* (SEC has the tag, FDB lacks the fact).

## Totals

| Universe | Companies | Without mapped revenue | Share |
| --- | ---: | ---: | ---: |
| Active listings (all exchanges) | 7,826 | 2,028 | 25.9% |
| Analyzable (non-OTC active listings) | 6,064 | 1,061 | 17.5% |

## Root cause distribution

| Category | Evidence from the sample | Estimated share |
| --- | --- | --- |
| Closed-end funds, trusts and ETFs | Nuveen Core Equity Alpha Fund, abrdn Life Sciences Investors, Invesco Quality Municipal Income Trust, BlackRock Health Sciences Trust, Western Asset / Eaton Vance funds — SEC has **no revenue tag at all** (investment companies report net investment income, not revenue) | largest block |
| SPACs and shells | Bluerock Acquisition Corp., SPACSphere Acquisition Corp., Constellation Acquisition Corp I, West Enclave Merger Corp. — pre-merger, **no revenue tag** | large block |
| Foreign private issuers on IFRS | SOPHiA GENETICS SA (CIK 0001840706): FDB stores `RevenueFromContractsWithCustomers`, `CostOfSales` (IFRS tags); the repository mapped only US-GAAP names → **mapping gap** | 42 companies |
| Registrants with minimal XBRL facts | GEORGIA POWER CO: 18 facts in FDB and no revenue tag in SEC either (subsidiary registrant) | small |
| Foreign issuers without XBRL at all | abrdn Life Sciences Investors: SEC `companyfacts` returns 404 | small |

No ingestion gap was found: every revenue tag seen in SEC `companyfacts` for
the checked companies was also present in Financial-DataBase. The 404 case is
a filer with no XBRL facts, not missing ingestion.

## Actions taken

Repository-level mapping fix (the only fixable layer; Financial-DataBase
stores the concepts correctly):

- `RevenueFromContractsWithCustomers` (IFRS 15) → `revenue`, ranked after the
  US-GAAP `RevenueFromContractWithCustomer*` tags in the income priority list.
- `CostOfSales` (IFRS) → `cogs`, so the gross-profit identity also works for
  IFRS filers.

Three regression tests in `tests/unit/test_fdb_concept_mapping.py` cover the
IFRS revenue mapping, the IFRS COGS mapping with derived gross profit, and
the US-GAAP priority when a filer reports both taxonomies.

## Remaining after fixes

- ~1,020 analyzable companies (≈16.8%) still have no mapped revenue, almost
  all structurally revenue-less: funds/trusts/ETFs, SPACs and shells. They
  cannot be fixed with a mapping change — there is no revenue to map.
- These companies stay excluded from revenue-based screens; the platform
  degrades to INSUFFICIENT_DATA instead of fabricating a figure.

## Exclusion from screens

Companies with no revenue AND no net income in the last 3 fiscal years are
excluded from the screener by default (they are typically funds, trusts,
ETFs and SPACs). A curated name pattern (Trust / Fund / Acquisition Corp /
SPAC …) also excludes revenue-less entities that do report a bottom line,
such as funds with investment income; a company with real sales is never
excluded by name (e.g. Northern Trust). The exclusion can be disabled per
session with the "Incluir fondos y SPACs" toggle.
`backend/services/screener_filters.py::is_investable_company` implements it.
