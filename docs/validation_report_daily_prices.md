# Daily Workflow & Real-Time Price Validation Report

Date: 2026-09-13

Scope: screener real-time price validation (pe/per/fcf-yield/ev-ebit filters,
`--no-prices`), `analyze-full`, daily workflow, runbook. No code was committed.

## Success Criteria

### C1. Real-time prices fetched per ticker, valuation filters work
Validation (investment engine, 12 validation tickers, `--filter min_score=30`):

```
Motor: calidad Buffett (+ precios en tiempo real)  |  Filtros: {'min_score': 30.0}
6 resultados
Rank Ticker Score Ranking Moat    Rating  Precio    PER  FCF Yield  EV/EBIT  Senal
1    AAPL   45.9   61.4   MODERATE  C       $332.27  57.4  1.5%      48.4     WATCHLIST
2    HD     50.6   60.1   MODERATE  C       $308.74  38.6  2.4%      31.6     WATCHLIST
3    KO     49.0   57.5   MODERATE  C        $88.29 114.1 -1.5%     112.0     HOLD
4    UNH    46.1   55.9   WEAK      C       $379.09  35.1  3.2%      27.3     HOLD
6    JNJ    33.3   46.7   WEAK      D       $265.58  38.7  1.0%      N/A      HOLD
```

- Prices and price-derived metrics (PER, FCF Yield, EV/EBIT) appear only for
  the tickers in the query; results degrade to `N/A` when a value cannot be
  computed (e.g. JNJ EV/EBIT — no EBIT), without dropping the company.
- `--filter min_score=60` on the same 12 tickers returns 0 results because all
  analyzed companies score 33–51; the filter is working as designed.

Validation (investment engine, market mode, price-value filters):

```
python main.py screener --tickers AAPL,KO,UNH --ev-ebit-max 100 --pe-max 100 --fcf-yield-min 1
2 resultados en 8.6s
Ticker Empresa             Precio   PER  FCF Yield  EV/EBIT
AAPL   Apple Inc.            $332.27 57.4 1.5%      48.4
UNH    UnitedHealth Group I  $379.09 35.1 3.2%      27.3
```

KO is excluded because EV/EBIT 112.0 > 100 — filter applied correctly.

### C2. Prices never persisted
- `PriceService` keeps only an in-memory TTL cache (900 s default); there is no
  read/write path to any prices table.
- `--dry-run` of the daily workflow wrote nothing: `data/reports/` does not
  exist after the run.
- The 3 new price-related fields (`per`, `fcf_yield`, `ev_ebit`) and the
  historical valuation table are computed on the fly from live prices +
  fundamentals; nothing price-related is stored.

### C3. Regression tests (305 passed, 1 skipped)
```
python -m pytest tests/unit -q
305 passed, 1 skipped, 1 warning in 5.73s
```

New unit test suites:
- `tests/unit/test_screener_price_scope.py` (9): PriceService called only for
  queried tickers; `no_prices` skips price calls; pe/ev_ebit/fcf_yield filters;
  investment engine bases filters on live-price metrics; price failure keeps
  the company in the screen; price metrics not persisted.
- `tests/unit/test_analyze_full.py` (9): `analyze-full` renders sections
  1–6; per-ticker failures do not kill the batch; historical valuation table.
- `tests/unit/test_daily_report.py` (13): DailyReport/state load/save/trim,
  markdown output, alerts rendering.

### C4. Analyze-full command
```
python main.py analyze-full AAPL
```
Renders all six sections: overview, real-time price & valuation (Precio
$332.27, PER 57.4, EV/EBIT 48.4), fundamentals, quality (Buffett 58.0,
MOAT MODERATE, rating C, DCF $1,130.8B), historical valuation 2009–2026, and
risks/anomalies/triggers.

### C5. Daily workflow runs end-to-end
```
python -m scripts.daily_workflow --dry-run --top 10
```
- Universe screened: 24 companies; prices real-time.
- Report table: ranks, company names (from Financial-DataBase
  `companies.legal_name` via `FinancialDatabaseRepository.get_company_name`),
  rating, score, price, P/E, FCF yield, EV/EBIT, signal.
- 22 TRIGGER_EVENT alerts evaluated against previous-day state.
- `--dry-run` writes nothing; `--no-prices` screens with valuation set to N/A
  and notes it in the report.
- SEC update integration confirmed: `python -m financial_database.cli sec
  update-incremental --max-age-hours 24` (skipped in dry-run).

## Notes
- The legacy `value_investing` PostgreSQL DB (CompanyRepository) does not
  exist in this environment (`psycopg2.OperationalError`); `_company_enrichment`
  logs a warning and degrades gracefully, so screens and reports still run.
- Company names in the daily report and section 1 of `analyze-full` resolve
  from Financial-DataBase metadata; unknowns render as `N/A`.
- Alert severity/title text is Spanish; labels and meta match the existing
  alert system.