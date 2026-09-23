# Expanded Universe Test — 2026-09-22

End-to-end validation of the expanded daily universe (S&P 500 + Nasdaq-100 +
Russell 2000 + European SEC-filers, master `config/universe.csv` = **2,528
tickers**) across three workflow scenarios, plus database integrity checks and
a performance/optimization review.

---

## 1. Push status (per repo)

| Repo | Unpushed commits | Latest commit |
|---|---|---|
| Value Investing | 0 (auto-pushed) | `fdd63e3` — docs: final report for the daily-universe expansion (then `216a7cc` this session, see §10) |
| Financial-DataBase | 0 (auto-pushed) | `f86cc1d` — docs: .env.example SEC_USER_AGENT/DATABASE_URL |

Both working trees clean, both `main` synced with `origin/main` (the
environment's auto-push mechanism propagated the previous session's commits
without manual `git push` — none was run this session).

## 2. Pre-flight check results

| Check | Result |
|---|---|
| PostgreSQL reachable (`pg_isready`) | **PASSED** |
| FDB unit suite | **PASSED** — 148 passed |
| Value Investing unit suite | **PASSED** — 474 passed, 1 skipped (→ 476 after this session's fix) |
| Disk free (`df -h /home/caudillo`) | **PASSED** — 357 GB free (≥ 20 GB) |
| Universe files | **PASSED** — `config/universe.csv` present, 2,528 tickers + header (2,529 lines) |
| `SEC_USER_AGENT` export | **PASSED** — set for every run |
| Pre-run DB snapshot | captured: companies 8,023 · facts 76,064,087 · filings 1,091,848 · prices 152 |

## 3. Russell 2000 run

Parameters: `--universe russell2000 --max-refresh 100 --top 20`

- **Duration:** 2,529 s (~42 min) — refresh 696 s · prices 948 s · analysis 885 s · alerts 0 s · report 0 s
- **Universe:** 1,957 tickers · **passed screen:** 1,895 (coverage 97%)
- **SEC refresh:** 100 refreshed (cap hit) · 1,890 still stale · **10 unmapped**
  (BELFB, BATRK, CENTA, HOS, LILAK, GLIBK, ATLC, BH, AIRJ, FGBI — the known
  class-variant / not-yet-ingested set) · 1,790 deferred (`--max-refresh`)
- **Prices:** no glitch/mapping failures surfaced in the report (delisted /
  unknown classes silently skipped); market fields real-time
- **Alerts:** BUY_SIGNAL **43** · TRIGGER_EVENT **208** (205 MEDIUM, 3 HIGH) · SELL_WARNING **0**
- **Analyze failures:** 1 — `HBNC` (complex-CAGR bug, **root-caused and fixed this session**, see §10)

### Top 10 opportunities (Russell-only run)

| # | Ticker | Company | Score | Rank | P/E | FCF yield | Signal |
|---|---|---|---|---|---|---|---|
| 1 | SAM | Boston Beer Co | 78.1 | 81.2 | 15.8 | 12.5% | BUY |
| 2 | LCII | LCI Industries | 83.9 | 81.0 | 11.4 | 12.9% | BUY |
| 3 | ZD | Ziff Davis | 82.4 | 80.7 | 41.6 | 14.6% | BUY |
| 4 | MMS | Maximus | 81.5 | 79.7 | 9.1 | 12.5% | BUY |
| 5 | SIG | Signet Jewelers | 78.1 | 79.7 | 13.4 | 13.3% | BUY |
| 6 | NATR | Nature's Sunshine | 75.3 | 79.5 | 11.9 | 12.4% | BUY |
| 7 | GPI | Group 1 Automotive | 79.3 | 78.7 | 9.4 | 14.0% | BUY |
| 8 | PGNY | Progyny | 73.9 | 78.6 | 34.9 | 9.4% | BUY |
| 9 | DFIN | Donnelley Financial | 76.5 | 78.5 | 36.9 | 9.0% | BUY |
| 10 | PRGS | Progress Software | 77.4 | 78.2 | 22.5 | 13.9% | BUY |

## 4. European run

Parameters: `--universe european --max-refresh 50 --top 20`

- **Duration:** 300 s (5 min) — refresh 221 s · prices 36 s · analysis 43 s
- **Universe:** 59 tickers (SEC-filer subset matched in the master) ·
  **passed screen:** 42 (coverage 71%)
- **SEC refresh:** 50 refreshed (cap) · 59 initially stale · 9 deferred
- **Prices:** clean (no surfacing failures)
- **Alerts:** TRIGGER_EVENT **3** (ASML, ABBNY, LOGI — all MEDIUM) · BUY_SIGNAL **0** · SELL_WARNING **0**
- **Missing data (17):** AKZOY, BMDPF, BZLFY, DTEGY, EONGY, ESYJY, FLIDY,
  HKHHY, IFNNY, LSEGY, PRYMF, PS, RTNTF, SCMWY, SLFPY, TGOPF, VWSYF — 20-F /
  ADR/OTC names without FDB fundamentals (expected for the SEC-filer-only
  policy; they screen out gracefully, no crash).

### Top 10 opportunities (European)

| # | Ticker | Company | Score | Rank | P/E | FCF yield | Signal |
|---|---|---|---|---|---|---|---|
| 1 | LOGI | Logitech Intl | 78.1 | 82.2 | 21.1 | 6.5% | BUY |
| 2 | QGEN | Qiagen N.V. | 64.4 | 79.8 | 21.3 | 5.0% | BUY |
| 3 | ABBNY | ABB Ltd | 83.1 | 78.3 | 49.1 | 1.9% | BUY |
| 4 | ASML | ASML Holding | 82.0 | 75.7 | 69.6 | 1.7% | BUY |
| 5 | FMS | Fresenius Medical Care | 67.9 | 74.1 | 10.1 | N/A | WATCHLIST |
| 6 | AMRZ | Amrize | 40.9 | 70.4 | 17.9 | 6.7% | AVOID |
| 7 | ALC | Alcon | 53.5 | 66.2 | 32.3 | N/A | AVOID |
| 8 | RELX | RELX PLC | 37.3 | 63.3 | 27.6 | N/A | AVOID |
| 9 | STM | STMicroelectronics | 60.6 | 63.2 | 285.3 | N/A | WATCHLIST |
| 10 | DEO | Diageo | 38.2 | 62.1 | 19.1 | N/A | AVOID |

## 5. Full universe run

Parameters: `--universe all --max-refresh 200 --top 20`

- **Duration:** 3,148 s (~52 min) — refresh **1,652 s** · prices 1,168 s · analysis 327 s · alerts 0 s · report 0 s
- **Universe:** 2,528 tickers · **passed screen:** 2,447 (coverage 97%) · 81 missing data
- **SEC refresh:** 200 refreshed (cap) · 1,814 still stale · **10 unmapped**
  (same class-variant set: BELFB, BATRK, CENTA, HOS, LILAK, GLIBK, ATLC, BH, AIRJ, FGBI) · 1,614 deferred
- **Prices:** clean (no glitch/mapping errors surfaced); delisted e.g. the
  14 EdgarProvider "no data" resyncs (VGNT, PFBC, GENB, HMH, SWMR + 9 European
  20-F names) are informational pre-XBRL warnings, not workflow failures
- **Alerts:** BUY_SIGNAL **68** (SP500 24 · Russell2000 44) · TRIGGER_EVENT **267**
  (262 MEDIUM, 5 HIGH) · SELL_WARNING **0**
- **Analyze failures:** 1 — `HBNC` again (the run started before the fix landed; fixed thereafter)

### Top 20 opportunities (full universe)

| # | Ticker | Company | Rating | Score | Rank | P/E | FCF yield | Signal |
|---|---|---|---|---|---|---|---|---|
| 1 | BF-B | Brown-Forman | A | 90.1 | 80.7 | 17.0 | 7.3% | BUY |
| 2 | LCII | LCI Industries | A | 83.9 | 80.5 | 11.3 | 13.1% | BUY |
| 3 | ZD | Ziff Davis | A | 82.4 | 79.9 | 41.4 | 14.7% | BUY |
| 4 | SAM | Boston Beer Co | A | 78.1 | 79.6 | 15.8 | 12.5% | BUY |
| 5 | ACN | Accenture | A | 90.2 | 79.2 | 14.7 | 9.6% | BUY |
| 6 | ADBE | Adobe | A | 78.2 | 79.1 | 13.3 | 10.4% | BUY |
| 7 | PAYX | Paychex | A | 84.6 | 79.0 | 23.1 | 5.7% | BUY |
| 8 | HII | Huntington Ingalls | A | 85.8 | 79.0 | 17.7 | 7.4% | BUY |
| 9 | MMS | Maximus | A | 81.5 | 78.9 | 9.1 | 12.6% | BUY |
| 10 | INTU | Intuit | A | 79.5 | 78.8 | 17.0 | 11.2% | BUY |
| 11 | CF | CF Industries | A | 75.7 | 78.6 | 12.7 | 9.8% | BUY |
| 12 | APTV | Aptiv | A | 88.0 | 78.6 | 56.2 | 16.5% | BUY |
| 13 | LDOS | Leidos | A | 78.2 | 78.4 | 10.8 | 10.4% | BUY |
| 14 | SIG | Signet Jewelers | A | 78.1 | 78.1 | 13.3 | 13.5% | BUY |
| 15 | MKC | McCormick | A | 88.4 | 77.9 | 16.8 | 5.6% | BUY |
| 16 | DGX | Quest Diagnostics | A | 85.7 | 77.7 | 26.3 | 5.2% | BUY |
| 17 | VLGEA | Village Super Market | A | 89.2 | 77.6 | 12.3 | 5.1% | BUY |
| 18 | LZB | La-Z-Boy | A | 83.8 | 77.6 | 12.0 | 10.4% | BUY |
| 19 | NATR | Nature's Sunshine | A | 75.3 | 77.5 | 11.9 | 12.4% | BUY |
| 20 | VRSK | Verisk Analytics | A | 83.8 | 77.3 | 24.7 | 5.3% | BUY |

### Top TRIGGER_EVENT alerts (full universe)

HIGH severity (5): **HII, HON, ENS, NGVT, PII** — e.g. HII "salto de free cash
flow" + rank 82.2 BUY, HON "mejora de ROIC" + rank 79.7 BUY, ENS/NGVT/PII FCF
surge. MEDIUM (representative): ABBV (ROIC), ALNY (FCF), APH (ROIC), APP
(margin), ARM (FCF), CARR (FCF), MU (FCF), SWKS (BUY 81.5), MRVL (revenue
accel), RDDT (FCF). All triggers are *positive* fundamental improvements per
the calibration (floors + cross-sectional percentile).

## 6. Post-run verification

| Check | Pre-run | Post-run | Verdict |
|---|---|---|---|
| `prices` row count | 152 | **152** | ✅ **no prices persisted** |
| `companies` | 8,023 | 8,023 | ✅ stable |
| `financial_facts` | 76,064,087 | 76,067,275 | ✅ +3,188 (refreshes) |
| `filings` | 1,091,848 | 1,092,021 | ✅ +173 (refreshes) |
| `import_runs` (last 6 h) | — | 407 × success, 17:32→20:59 | ✅ refresh ledger recorded |

Reports generated in `data/reports/`: `daily_2026-09-22.md` (final = full
universe; each scenario archived to `/tmp/report_{russell2000,european,all}_2026-09-22.md`
since the dated file is overwritten per run) plus `daily_state.json`.

## 7. Score distribution and analysis

All analyses (not just top-20), from the archived run states:

| Universe | n | min | p10 | median | p90 | max | mean |
|---|---|---|---|---|---|---|---|
| **Full 2,528** | 2,447 | 2.5 | 24.8 | 47.8 | 75.9 | 94.2 | 49.2 |
| SP500 (same-day, in full run) | 499 | 8.5 | 39.5 | 63.7 | 82.8 | 94.2 | 62.0 |
| Nasdaq-100 (same-day) | 95 | 4.0 | 42.4 | 64.3 | 81.4 | 91.1 | 63.3 |
| Russell 2,000 (Russell-only run) | 1,895 | 2.5 | 23.1 | 45.8 | 70.0 | 90.7 | 46.1 |
| European (European-only run) | 42 | 20.5 | 24.7 | 29.7 | 64.4 | 83.1 | 36.3 |

Scores are **well spread (p10 24.8 → p90 75.9)**, not clustered in 40–60 —
the expansion adds a long tail of small-caps and early-stage names while the
large-caps keep the top band. Russell small-caps do score higher than the
S&P average at the tail: e.g. HCKT rank 84.4, LCII 84.0/80.5, ZD 83.0/79.9,
SAM 82.3/79.6, and top-20 now includes 8 Russell names (LCII, ZD, SAM, MMS,
SIG, VLGEA, LZB, NATR) alongside the S&P quality names.

## 8. Recurrently failing tickers

Across all three logs the only true analyze failure is **HBNC** (complex
`revenue_cagr`, fixed in `216a7cc`). The 14 `EdgarProvider returned no data`
lines (VGNT, PFBC, GENB, HMH, SWMR + 9 European ADRs) are informational
edgartools `FutureWarning`s for pre-XBRL filings during `sec sync` — no data
or workflow impact. The 10 unmapped Russell names (BELFB, BATRK, CENTA, HOS,
LILAK, GLIBK, ATLC, BH, AIRJ, FGBI) recur across all runs as expected —
class-variant / not-yet-ingested, documented in the validator report. **No
recurrent price failures** (delisted/unknown are skipped silently per design).

## 9. Comparison vs previous 500-only run

Baseline `data/reports/daily_2026-09-21.md`: universe 500, screened 499,
runtime 1,387 s, 1 refreshed, 24 BUY_SIGNAL, 475 TRIGGER_EVENT. Note the
09-21 report used the **pre-calibration** alert engine (a trigger fired for
~every company, 475/499); 09-22 uses the calibrated engine (absolute floor +
cross-sectional percentile), so alert **counts are not directly comparable**.
Score/rank comparisons are valid.

- **Relative ranking kept:** the S&P names that led on 09-21 still lead the
  full-universe top-20 (BF-B #1, ACN #5, PAYX #7, HII #8, MKC #15, VRSK #20).
  None dropped unexpectedly; the same-day SP500 subset shows 24 BUY — identical
  to the baseline's 24.
- **Percentile squeeze is visible but modest:** BF-B rank 83.0 → 80.7, ACN
  81.2 → 79.2, MKC 80.8 → 77.9 — a few points lower because 2,528 (not 500)
  names now compete for the same 10–90 band. Expected, not a regression.
- **New quality names emerging from Russell 2000:** LCII (rank 80.5), ZD
  (79.9), SAM (79.6), MMS (78.9), SIG (78.1), HCKT (alert rank 84.4),
  NATR — small-caps with ROIC 21–30% and positive FCF that simply weren't
  scored before.
- **Europe adds breadth, not alpha:** median 29.7 — many ADRs lack FCF
  fundamentals (N/A columns); only LOGI/QGEN/ABBNY/ASML reach BUY territory.

## 10. Bug found & fixed (this session)

`revenue_cagr()` (`backend/intelligence/quality_metrics.py`) and backtesting
`simulator.cagr()` raised a fractional power on a **negative base** when the
latest year's revenue (HBNC: −26.9 M in FY2025) or the final equity value is
≤ 0, yielding a Python `complex` and crashing downstream comparisons
(`'>=' not supported between instances of 'complex' and 'float'`). Both now
return `None` for a non-positive endpoint. Commit `216a7cc` (+ 2 regression
tests). Verified: HBNC now analyzes normally (total 42.53, `revenue_cagr: None`).
Full suite: **476 passed, 1 skipped**.

---

## 11. Optimization report (optimización y rendimiento)

*Resumen en español* — más abajo el detalle en inglés.

**¿Cómo ha ido?** El pipeline es correcto y determinista, pero el cuello de
botella es claramente la **refresco SEC (`sec sync`)**: 52 % del tiempo total
del run completo (1 652 s de 3 148 s por 200 empresas ≈ 8,3 s/empresa,
secuencial). La precarga de precios (46 %–38 %) y el análisis son
paralelizables y escalan casi linealmente. El run completo tardó **52 min**
(estimación inicial ~16 min fue demasiado optimista; 3 148 s vs 1 387 s del
baseline de 500 con datos mayoritariamente frescos).

**¿Se puede optimizar más? Sí, ordenado por impacto:**
1. **Paralelizar `sec sync` con 2–3 workers** (respetando rate limits de SEC)
   → el mayor ahorro: ~−25 % del wall-clock total.
2. **Subir workers del snapshot de precios de 4 a 6** (probes previas: 0
   fallos a 6) → −15–20 % de la fase de precios.
3. **`--resume` multi-día** para drenar los ~1 614 Russell diferidos en vez de
   re-hacer los mismos 200 más stale.
4. **Excluir del path diario los 17 europeos sin fundamentos** (ahorrar
   lookups muertos). Opción: flag `has_fundamentals`.
5. **Solapar precios del batch N+1 con análisis del batch N** (cambio
   arquitectónico, mayor esfuerzo).
6. La anomalía analysis 327 s (full) vs 885 s (Russell-only) merece un
   benchmark; sugiere variabilidad por carga, no un bug.

**Estado de implementación (2026-09-23):** las palancas 1 y 2 ya están
implementadas en el código y la configuración por defecto:

- **Refresh SEC paralelo**: `RefreshService` ejecuta los `sec sync <CIK>`
  de las empresas vencidas con hasta `refresh_workers` subprocesos
  concurrentes (por defecto **2**, `config/refresh.yaml` y env `REFRESH_WORKERS`;
  flag `--refresh-workers N` en `daily_workflow`). Los resultados se agrupan
  preservando el orden de entrada. Como `sec sync` es un subproceso (libera el
  GIL), 2 workers recortan ~a la mitad la fase de refresh manteniendo modesto
  el burst a SEC. Tests: `tests/unit/test_refresh_service.py`.
- **Snapshot de precios 4 → 6 workers**: nuevo cap `SNAPSHOT_WORKERS_CAP = 6`
  en `daily_workflow.py` y **workers por defecto 1 → 4** (env `WORKFLOW_WORKERS`
  sigue sobreescribiendo). La precarga de cotizaciones sigue en lotes con
  reintento único; el análisis gana con threads porque es I/O-bound a
  PostgreSQL.

Estimación actualizada del objetivo: con refresh paralelo (2 workers) + workers
4 en precios/análisis, el run completo de ~2 500 tickers debería bajar de
**~52 min a ~30–35 min**; es la referencia a validar en la próxima corrida.

---

### 11.1 Stage-level timings

| Run | Universe | refresh | prices | analysis | total | cost per ticker¹ |
|---|---|---|---|---|---|---|
| Baseline 09-21 (500, mostly fresh) | 500 | 66 s | — | — | 1,387 s | 2.8 s |
| Russell-only | 1,957 | 696 s | 948 s | 885 s | 2,529 s | 1.3 s |
| European | 59 | 221 s | 36 s | 43 s | 300 s | 5.1 s |
| **Full universe** | 2,528 | **1,652 s** | 1,168 s | 327 s | **3,148 s** | 1.2 s |

¹ total / analyzed tickers (raw, includes refresh).

### 11.2 Where the time goes (full run, 3,148 s)

- **Refresh 1,652 s (52 %)**: 200 `sec sync` subprocesses, sequential
  (~8.3 s/company). Pure wall-clock loss — bounded by `--max-refresh`, not by
  CPU. **Biggest lever.**
- **Prices 1,168 s (37 %)**: Yahoo snapshot prefetch, workers capped at
  `min(workers,4)` per the throttling guardrails (quote-summary bursts are far
  more tolerant than `history()`); ~0.46 s/ticker.
- **Analysis 327 s (10 %)**: parallel analyzers over the warm snapshot cache.
- Alerts/report ≈ 0 s.

### 11.3 What is already optimized (done this week)

- Snapshot price prefetch eliminated all per-ticker network I/O during
  analysis (parallel workers, retry-once, batched pacing).
- `staleness_ranked()` feeds `--max-refresh` the most-recent-synced stale
  companies first, deferring the rest — refresh deadlines are prioritized.
- Coverage-gated validator, 10-unresolved cap, `--resume` reuse of
  `daily_state.json`.
- Analysis/price parallelism cap at 2 workers only where Yahoo history is
  dense; snapshot path already safe at higher concurrency.

### 11.4 Remaining optimization opportunities (ranked)

| # | Lever | Est. saving (full run) | Effort | Risk |
|---|---|---|---|---|
| 1 | Parallelize `sec sync` (2–3 workers, SEC-friendly pacing) | −600–800 s (refresh 1,652 → ~900 s; total −20–25 %) | Low | SEC rate-limit (mitigate: 2 workers, backoff) |
| 2 | Snapshot workers 4 → 6 (quote probes showed 0 failures at 6) | −150–200 s (prices) | Low | Yahoo throttling (retry-once absorbs) |
| 3 | Multi-day `--resume` to drain deferred Russell backlog | −unneeded re-syncs over the week | Low | None |
| 4 | Skip European non-filers (flag `has_fundamentals`) | ~17 dead-end lookups/run | Low | None |
| 5 | Pipeline overlap: prefetch next batch while analyzing current | −parallel gain on prices+analysis | Medium/High | Complexity |
| 6 | Cache analyzed results across days (recompute only deltas) | long-term largest | High | Staleness semantics |

### 11.5 Verdict

The expanded-universe workflow is **production-correct** (deterministic,
no price persistence, DB integrity preserved) and currently runs the full
2,528-ticker universe in **~52 min**. With levers 1–3 applied (refresh
parallelism + snapshot workers + `--resume`), a realistic target is
**~30–35 min** for the daily full-universe run, scaling sub-linearly with
ticker count. Further gains are architectural (overlap, result caching) and
not needed for daily cadence unless universe size grows materially.

---

## 12. Gates summary

| Gate | Result |
|---|---|
| All three runs completed end-to-end | ✅ Russell 2,529 s · European 300 s · Full 3,148 s |
| No prices persisted (152 before and after) | ✅ |
| No DB corruption (companies stable; facts +3,188; filings +173) | ✅ |
| Reports generated in `data/reports/` | ✅ |
| Comprehensive report written and committed | ✅ |
| All tests pass | ✅ 479 passed, 1 skipped |