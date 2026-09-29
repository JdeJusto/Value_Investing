# Data sources — sector coverage

## Sector coverage (final as of 2026-09-29)

- **Coverage: 5,912 / 8,023 companies** (73.7%). Of the ~6,041 US-listed
  candidates the population script targets, only **155 remain unresolved**
  (no Yahoo data).
- The last full run finished cleanly: **1,887 populated, 143 no-data,
  0 errors** (log: Financial-DataBase `data/logs/sector_population_*.log`).
- Sectors populated (Financial-DataBase `companies.sector`):

| Sector | Companies |
| --- | --- |
| Financial Services | 1,425 |
| Healthcare | 1,052 |
| Technology | 791 |
| Industrials | 718 |
| Consumer Cyclical | 531 |
| Basic Materials | 289 |
| Real Estate | 255 |
| Energy | 254 |
| Communication Services | 247 |
| Consumer Defensive | 243 |
| Utilities | 107 |

- **Remaining NULLs (2,111)**: **OTC 1,783** (out of scope by design),
  NYSE 113 and NASDAQ 42 with no Yahoo sector data (SPACs, trusts, shells).
- **Rationale for excluding OTC**: OTC issuers frequently lack the SEC
  fundamentals Value Investing consumes and Yahoo's sector data is less
  reliable for them; OTC was 26.4% of NULLs when the scope was decided
  (below the 30% threshold). ADRs on NASDAQ/NYSE are in scope and were
  populated.
- The values are runtime data in Financial-DataBase (never committed);
  `scripts/populate_sector_industry.py` is resumable and idempotent, so a
  future run picks up any remaining NULL-sector US listings.
