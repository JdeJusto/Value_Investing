# FDB upstream tickets

These tags exist in SEC filings but are not stored in FDB, which limits
the balance T-view for the affected tickers.

## APA — Apache Corporation

- CIK: 0000006769
- Missing concepts: `Goodwill`, `OtherAssets` (verify exact tags)
- SEC example:
  `https://data.sec.gov/api/xbrl/companyconcept/CIK0000006769/us-gaap/Goodwill.json`
- Impact: balance T-view shows fewer asset lines than the 10-K face.

## APO — Apollo Global Management

- CIK: 0001858681
- Missing: insurance/alternative asset face lines (`SeparateAccountsAsset`,
  `MarketRiskBenefitAsset`, etc.)
- Impact: insurance-specific lines missing.

## ARES — Ares Management

- CIK: 0001176948
- Missing: insurance/alternative asset face lines (same as APO)
- Impact: insurance-specific lines missing.

## BRK-B — Berkshire Hathaway

- CIK: 0001067983
- Missing: `AccountsPayableCurrent` (face: "Accounts payable, accruals and
  other liabilities"), `NotesPayableCurrent` (face: "Notes payable")
- Impact: current liabilities column is sparse.

## AEE — Ameren

- CIK: 0001002910
- Status: 10-K R-file not located; unverified. Not a ticket, just a note.

## How to verify

For each concept:
```bash
curl -s -H "User-Agent: $SEC_USER_AGENT" \
  "https://data.sec.gov/api/xbrl/companyconcept/CIK0000006769/us-gaap/<Concept>.json" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['units']['USD'][-1])"
```

If the concept returns 200 and a value but
`SELECT count(*) FROM financial_facts WHERE company_id=... AND concept='<Concept>'`
returns 0, the gap is confirmed.

## PCAR — PACCAR (unclassified balance sheet)

- CIK: 0000075362
- FDB lacks `AssetsCurrent` / `LiabilitiesCurrent` for the latest years: the
  10-K face is unclassified (industrial + financial-services segments), so
  this may be structural rather than a missing fact.
- Cash is only stored as
  `CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsIncludingDisposalGroupAndDiscontinuedOperations`
  (FY2025: 6.31B); the plain `CashAndCashEquivalentsAtCarryingValue` tag is
  absent. Canonical debt tags are absent too.
- Impact: Greenblatt EY/ROC cannot be computed; `vi financials` shows a
  partial balance view. Requires a product decision (segment-level treatment)
  before mapping a restricted-inclusive cash figure to `cash`.

## BRUN — Boost Run

- Only 1-2 fiscal years with usable fundamentals; latest total assets and
  equity are missing.
- Impact: scorecard and methodology history are mostly `INSUFFICIENT_DATA`.
  Not an FDB ingestion ticket: the company has not filed enough history.
