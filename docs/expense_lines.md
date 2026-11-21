# Expense line disaggregation (XBRL pilot, v0.35.0)

XBRL has no universal tag for "electricity" or "marketing". This feature
exposes the standardized subset that **is** filed and marks everything else
as `not disclosed` (never 0).

## Coverage in the S&P 500 master universe (500 tickers)

Measured 2026-11-21 over `config/universe.csv` (source `SP500`):

| Line item | Primary tag(s) | Tickers | Coverage |
|---|---|---|---:|
| Marketing / advertising | `MarketingExpense`, `AdvertisingExpense`, `SellingAndMarketingExpense` | 223 | **45%** |
| Research & development | `ResearchAndDevelopmentExpense` | 231 | **46%** |
| SG&A | `SellingGeneralAndAdministrativeExpense` | 293 | **59%** |
| G&A | `GeneralAndAdministrativeExpense` | 147 | **29%** |
| Occupancy | `OccupancyExpense` | 0 | **0%** |
| Utilities / electricity | `UtilitiesExpense` | 0 | **0%** |
| Depreciation & amortization | `DepreciationDepletionAndAmortization` | 365 | **73%** |
| COGS (combined variants) | `CostOfRevenue`, `CostOfGoodsAndServicesSold`, `CostOfServices` | 354 | **71%** |
| Labor | `LaborAndRelatedExpense` | 76 | **15%** |

Global FDB counts are larger (e.g. `AdvertisingExpense` 2,125 companies,
`MarketingExpense` 359, `SG&A` 2,470), but the feature is scoped to the
S&P 500 pilot. `OccupancyExpense` and `UtilitiesExpense` exist in FDB but
are absent from the S&P 500 sample, so electricity cannot be reported
separately for these companies.

## Pilot (23 tickers across sectors)

| Ticker | FY | Disclosed lines |
|---|---:|---:|
| KO | 2025 | 3 (marketing, SG&A, D&A) |
| PG | 2026 | 4 (marketing, R&D, SG&A, D&A) |
| PEP | 2025 | 4 |
| MDLZ | 2025 | 3 |
| WMT | 2026 | 2 |
| COST | 2026 | 2 |
| TGT | 2025 | 3 |
| AAPL | 2026 | 5 (marketing, R&D, SG&A, G&A, D&A) |
| MSFT | 2026 | 3 |
| GOOGL | 2025 | 3 |
| META | 2025 | 4 |
| CAT | 2025 | 3 |
| DE | 2025 | 4 |
| HON | 2025 | 3 |
| DUK | 2025 | 1 (D&A) |
| NEE | 2026 | 0 |
| SO | 2026 | 0 |
| JPM | 2026 | 0 (bank, not applicable) |
| BAC | 2025 | 0 (bank, not applicable) |
| JNJ | 2025 | 4 |
| PFE | 2025 | 3 |
| XOM | 2025 | 3 |
| CVX | 2025 | 3 |

19/23 companies have at least one disclosed line; 60/161 potential lines
(37%). Banks and the two utilities in the sample (NEE, SO) disclose no
mapped line. No override was needed for the pilot.

## What is NOT available

- **Electricity as a standalone line**: no S&P 500 filer tags
  `UtilitiesExpense`; it is inside occupancy/COGS or a note.
- **Marketing separated from advertising**: only some consumer companies
  file both; the map prefers `MarketingExpense`, then `AdvertisingExpense`,
  then `SellingAndMarketingExpense`.
- **Banks/REITs**: expense lines are not comparable (interest expense and
  FFO dominate). The report marks every line `not applicable` and the CLI
  shows the reason.
- **Text-only breakdowns**: a company may discuss advertising or electricity
  in the SG&A note without an XBRL tag. That requires a 10-K text parser
  (separate sprint); this feature never estimates the value.

## Overrides

`backend/repositories/expense_overrides.py` holds per-ticker exceptions,
verified against the filing. A tag string selects that concept; a number is
a verified USD value; `None` forces `not disclosed`. The dictionary is
empty for the pilot because the generic map covered every disclosed line.

## CLI

```bash
vi expenses KO
vi expenses AAPL --year 2026
vi expenses AAPL --json
```

Missing lines are printed as `not disclosed` with the reason (`no XBRL tag`,
`not applicable for banks`, `FX rate unavailable`). Values for non-USD
filers are converted at the fiscal-year FX rate implied by core revenue
(`revenue_usd / revenue`).

## Next steps

1. 10-K text parser for the ~55% of companies without a marketing tag and
   for electricity/occupancy.
2. Expand overrides to the top 100 S&P 500 by market cap, only after
   verifying the filing.
3. Optional `labor` line (15% coverage) once the model is settled.
