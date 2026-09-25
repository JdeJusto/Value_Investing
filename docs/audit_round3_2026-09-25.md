# Auditoría ronda 3 — 2026-09-25 (condensada)

Validación de cierre tras la ronda 2: WIP commiteado en incrementos atómicos,
estrategia anti-403 de SEC implementada, y re-ejecución del top de comandos
para confirmar que nada se rompió.

**Metodología:** barrido determinista con `REFRESH_SKIP_FLAG=1` y sin
`SEC_USER_AGENT` → ningún tráfico SEC durante el smoke (el refresh se omite
con aviso, como está diseñado). Los tiempos son wall-clock con el venv activo
y `FINANCIAL_DATABASE_URL` apuntando a la base principal.

## 1. WIP y commits de la ronda

El WIP (17 modificados + 2 untracked) era el lote de correcciones documentado
en `docs/reporte_pruebas_2026-09-23.md` más los restos de la ronda 2
(P0 norm + yfinance lazy). Se commitéó en 10 incrementos atómicos (autor
`jdejusto`, sin push):

| Commit | Contenido |
|---|---|
| `9b6b67a` | perf: optimización de `_normalize_financial_facts` (150×) |
| `4c2dfad` | fix(repository): dominancia de ingresos REIT/banco + FY-end por año calendario |
| `7fd4148` | perf: import perezoso de yfinance en price_service |
| `6b949e7` | fix(price): año fiscal `int`, reintentos .info y rate pacing |
| `218e9d8` | fix(scoring): health caps graduados + barra BUY para confianza LOW |
| `24e484d` | fix(intelligence): historia vacía/parcial robusta + FCF a 3 años |
| `6c810f2` | fix(repository): envoltorios sin score no cuentan como cobertura |
| `b0b4284` | test(repository): regresiones FY-end y normalización de ingresos |
| `40c3b36` | docs: informe del lote 2026-09-23 + notas AGENTS.md |
| `844e0f1` | feat(refresh): preflight de disponibilidad de SEC |

Financial-DataBase: `2cefeda` (docs: investigación del 403 de SEC) — local.

## 2. Smoke tests (21 comandos, todos exit=0)

| Comando | Exit | Duración | Notas |
|---|---|---|---|
| `debug` | 0 | 2.64s | 7/7 filtros y servicios OK |
| `company AAPL` | 0 | 2.70s | |
| `analyze AAPL` | 0 | 7.08s | Yahoo-bound (ver §3) |
| `analyze-full AAPL` | 0 | 12.17s | Yahoo-bound |
| `buffett-analysis AAPL` | 0 | 12.39s | |
| `historical-valuation AAPL` | 0 | 6.73s | serie 2009-2025 coherente |
| `screener --tickers AAPL,MSFT,KO,JNJ,PG --filter min_score=40` | 0 | 16.55s | filtros Buffett |
| `screener` universo (10 SP500) `--top 10` | 0 | 10.68s | ⚠ `--universe` no existe en screener |
| `opportunities --tickers AAPL,MSFT,KO` | 0 | 10.63s | |
| `anomalies AAPL MSFT KO` | 0 | 9.63s | |
| `momentum AAPL MSFT KO` | 0 | 3.85s | |
| `alerts AAPL MSFT KO` | 0 | 5.99s | |
| `portfolio view` | 0 | 1.15s | |
| `backtest AAPL MSFT KO JNJ PG --strategy momentum --years 3 --top 5` | 0 | 1.99s | ⚠ sin tickers usaría las 2,528 del universo |
| `sql-analysis company_overview` | 0 | 17.17s | |
| `sql-analysis financial_series --limit 5` | 0 | 1.13s | |
| `sql-analysis ratios_advanced` | 0 | 1.24s | |
| `sql-analysis compare` | 0 | 1.26s | |
| `daily_workflow --dry-run --universe sp500 --top 10` | 0 | 161.05s | análisis completo del universo; el refresh SEC sí se omite |
| `screener --search "Apple"` | 0 | 2.28s | |
| `import backend.app.cli` (frío) | 0 | 0.154s | |

Sin un solo Traceback/ERROR/WARNING en los 21 logs. Degradaciones elegantes
observadas: `HONA` sin datos (missing data) y glitch de cotización de Yahoo
en `BAC`/`FANG` (analizados con campos de mercado N/A).

## 3. Rendimiento vs ronda 2

| Métrica | Ronda 2 | Ronda 3 | Δ |
|---|---|---|---|
| Cold CLI import | 0.18s | **0.154s** | ~igual |
| `screener --search "Apple"` | 6.4s | **2.28s** | −64% |
| Normalización P0 (`_normalize_financial_facts`) | 0.148s cum | **0.065s cum** (11 calls) | mejor |
| `analyze AAPL` (core determinista) | — | **2.29s** | — |
| `analyze AAPL` (wall, 3 runs) | 4.11s | 7.84 / 12.15 / 13.57s | varianza Yahoo |
| `analyze-full AAPL` | 8.07s | 12.17s | varianza Yahoo |

**Atribución de `analyze AAPL`** (instrumentado): import 0.12s + construir
servicio 0.31s + refresh/mercado 1.15s + análisis 0.72s = **2.29s**. El resto
hasta 7-13s es latencia de `.info` de Yahoo (1-12s según el momento, más
reintentos 1s/2s si hay glitch). No hay regresión de código: la varianza
aparece también en `historical-valuation` (14.05s → 6.73s entre pasadas).

## 4. Integridad de datos (base principal)

```
companies=8023  facts=76117485  filings=1093944  prices=152
import_runs=1372  running=9 (todos prices_update)
```

- **Sync en vivo de TALK** (CIK `0001803901`, stale desde el 1-Sep, UA
  compliant): `status=success`, 41s, **0 inserted / 5,149 skipped**
  (89 filings + 5,060 facts), 0 errores de validación → idempotencia del
  bulk insert verificada contra SEC real; `last_synced_at` estampado
  (antes NULL).
- Dangling `running`: **24 → 9**; los 9 restantes son `prices_update` (fuera de
  `SEC_PIPELINES`), los de pipelines SEC se cerraron durante el sync en vivo.
- `prices` intacta en 152 filas: los precios nunca se persisten.

## 5. SEC (403: diagnóstico y preflight)

- Diagnóstico reproducible: SEC bloquea UAs con **dominio github.com**
  (incluido `users.noreply.github.com`) y UAs genéricos (`curl`, `python-requests`);
  las ráfagas >10 req/s también devuelven 403. **No era un bloqueo del entorno.**
  Detalle y evidencias: FDB `docs/sec_403_investigation.md`.
- Con UA compliant: `company_tickers` 10,413 empresas en 0.7s (2ª llamada
  0.000s, memoización validada en vivo).
- Preflight `backend/services/sec_health.py` integrado en `RefreshService`:
  con trabajo stale sondea (HEAD, 1 reintento, caché 120s); si no hay SEC,
  omite con `sec_skipped_reason` y sigue con los fundamentales almacenados.
  Verificado en CLI: `analyze TALK` sin `SEC_USER_AGENT` →
  `SEC no disponible — refresh SEC omitido` y el análisis continúa.
- **Criterio para reanudar el refresh**: exportar un `SEC_USER_AGENT`
  compliant (¡sin dirección github.com!) y dejar el preflight activo; los
  periodos con 403 se saltan solos.

## 6. Suites de tests

| Proyecto | Resultado |
|---|---|
| Value Investing (`tests/unit`) | **537 passed, 1 skipped** (+13 del preflight vs 524) |
| Financial-DataBase (`pytest` completo) | **189 passed** (`tests/unit`: 153) |

## 7. Regresiones y observaciones

- **Ninguna regresión funcional ni de rendimiento atribuible al código.**
- `screener` no soporta `--universe` (se usó la lista explícita de 10 SP500).
- `daily_workflow --dry-run` ejecuta el análisis completo del universo; solo
  omite el refresh SEC (por eso sus 161s).
- No usar direcciones `github.com` en `SEC_USER_AGENT` (403 determinista).
- 9 `import_runs` de `prices_update` siguen en `running` (fuera del ámbito
  SEC; el cierre de colgados solo cubre `SEC_PIPELINES`).

## 8. Referencias

- `docs/reporte_pruebas_2026-09-23.md` (lote de bugs de la ronda).
- `docs/scoring_methodology.md` (health caps + barra LOW).
- FDB `docs/sec_403_investigation.md` (403 de SEC).
- `backend/services/sec_health.py` y `backend/services/refresh_service.py`
  (preflight y degradación).
