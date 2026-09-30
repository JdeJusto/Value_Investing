# QA session — screener semantics (2026-09-30)

AppTest with programmatic widget values; real Financial-DataBase.

## D1/D2 — SP500, cap 50, sector Technology, verdict BUY

- Result: **no exception**, run **91.8 s** (50 tickers; ~1.8 s/ticker
  including the batched Yahoo snapshot prefetch + methodology enrichment).
- **Warning fired correctly**:
  `El filtro de verdict/categoría se aplica solo a los primeros 50 tickers
  tras los filtros SQL (85 candidatos). Aumenta 'Max tickers' para cubrir más.`
  (85 Technology candidates > cap 50 — honest partial-coverage notice).
- Results: **12 rows**, columns `Ticker, Name, Sector, Price, P/E, FCF
  Yield, ROE, Verdict, Score, Category`; **1 CSV download button** present.
- Caption: `Candidatos tras filtros SQL: 85 · screened: 50 · metodología:
  buffett_classic · filas: 12`.

## D3 — Edge cases

| Case | Behavior | Flag |
| --- | --- | --- |
| Market cap min 500B > max 10B | No exception; renders "Ningún resultado con los filtros actuales." | IMPROVEMENT: should show a validation error for an impossible range |
| Sector multiselect with values | Applied in the SQL pre-filter (one bulk query) | OK |
| Verdict filter with cap < candidates | Warning shown, no silent partial results | OK |
| CSV export | Download button rendered with the results | OK |

## Findings

1. **Estimate caption understates the cost** (`~0 min para 50 tickers`;
   real ≈ 1.8 s/ticker). → fixed in Phase G (text + per-ticker constant).
2. **Invalid market-cap range is not validated** (min > max silently
   yields zero rows). → fixed in Phase G (explicit error).
3. Verdict/category enrichment covers every screened row (cap-bounded),
   and the warning covers the capped-candidates case. Semantics verified.
