# QA session — portfolio and workflow end-to-end (2026-09-30)

## E1 — Portfolio CLI cycle (real file, cleaned up afterwards)

| Step | Result |
| --- | --- |
| `portfolio add AAPL 1 100.00` | "Posicion AAPL registrada (1.0 acciones a 100.00)" |
| `portfolio view` | AAPL shown with the live price ($329.40), PnL 229.4%, signal columns |
| `portfolio exit AAPL 150.00` | "Posicion AAPL cerrada — PnL realizado +50.00" |
| `portfolio performance` | PnL realizado $50.00 · PnL total $50.00 · Retorno 50.0% |
| `portfolio remove AAPL` | removed |
| `data/portfolio.json` after | `{"name": "default", "positions": []}` — **no test data left** |

## E1b — UI refresh / save (on a copy, never the real file)

- `Fetch current prices` → no exception, delta table rendered, `Save
  prices to portfolio` enabled.
- `Save` → no exception; the **copy** JSON was updated (current_price
  changed). The real `data/portfolio.json` was untouched.
- One transient Yahoo warning (`$AAPL: possibly delisted`, DNS flake);
  the other positions refreshed fine.

## E2 — Daily workflow (real run)

`python -m scripts.daily_workflow --limit 20 --top 5`:

- **exit 0, 35 s**.
- Report generated: `data/reports/daily_2026-09-30.md` (same-day file is
  replaced, so the report count stayed at 8).
- Sections present: header, SEC refresh (0 refreshed / 20 fresh / 2 s),
  Network, Price stage, Screened (20 companies, 100% coverage,
  real-time prices), Alerts, **DCF Valuation (supplementary,
  not-from-canon)**.
- **`prices` table: 152 before and after** — nothing persisted.

## Assessment

The portfolio cycle, the UI price flow (in-memory + explicit save) and
the full daily workflow behave as designed end-to-end.
