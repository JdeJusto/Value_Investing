# Expanded Universe Test — 2026-09-23

Validación end-to-end del universo expandido (**2,528 tickers** del master
`config/universe.csv`) tras los **5 fixes de importación SEC** validados con
10 empresas del S&P 500 (`docs/validation_10_sp500_2026-09-22.md`). Tres
escenarios secuenciales (Russell 2000 → Europeo → Full universe) con refresh
SEC dirigido, precios real-time sin persistencia y verificación de integridad
de base de datos.

---

## 1. Push status (repos)

| Repo | Push | Último commit de esta sesión |
|---|---|---|
| Value Investing | **NO** (por instrucción; sin PRs) | `a263ea8` — fix `PRICE_FAILURE_*` en module scope |
| Financial-DataBase | **NO** | `c3cbd19` (sesión anterior: `fiscal_year = period_end.year`) |

Commits de esta sesión: `948ea25` (label P/B <1), `6ce5ed4` (informe validación
10 empresas), `a263ea8` (fix clasificador de fallos de precio + tests de
regresión), más los commits de datos/informe que cierran este test. `git
status` queda limpio salvo el WIP del usuario gestionado aparte (ver §10:
composite.py stasheado; `price_service.py` modificado en paralelo durante la
ejecución, fuera del alcance de este test).

## 2. Pre-flight check results

| Check | Resultado |
|---|---|
| PostgreSQL (`pg_isready`) | **PASSED** |
| Suite FDB (`tests/unit`) | **PASSED** — 149 passed |
| Suite Value Investing (`tests/unit`) | **PASSED** — 501 passed, 1 skipped (→ 503 con los 2 tests nuevos de `a263ea8`) |
| Disco (`df -h /home/caudillo`) | **PASSED** — 356 GB libres (31% usado) |
| Universo `config/universe.csv` | **PASSED** — 2,528 tickers + header (2,529 líneas) |
| `SEC_USER_AGENT` | **PASSED** — exportado en cada run |
| Snapshot DB pre-run | companies **8,023** · facts **76,067,275** · filings **1,092,021** · **prices 152** |

## 3. Russell 2000 run

Parámetros: `--universe russell2000 --max-refresh 100 --top 20`

- **Falló el 1er intento** (13:00): `NameError: PRICE_FAILURE_MAPPING` en
  `_classify_price_failures` tras completar los 100 syncs — el import de las
  constantes era local a `_run()`. **Raíz y fix: `a263ea8`** (constantes a
  module scope + tests `TestClassifyPriceFailures`). Sin este fix, los tres
  escenarios habrían abortado.
- **Rerun exitoso**: **994 s (~16.6 min)** — refresh 701 s · prices 646 s
  (solapadas) · analysis 292 s
- **Universo:** 1,957 · **passed screen:** 1,896 (coverage 97%)
- **SEC refresh:** 100 refreshed (cap) · 1,495 still stale · **10 unmapped**
  (BELFB, BATRK, CENTA, HOS, LILAK, GLIBK, ATLC, BH, AIRJ, FGBI — set
  conocido class-variant / no ingerido) · 1,395 deferred
- **Precios:** sin errores de mapping/glitch que rompieran el reporte
- **Alertas:** BUY_SIGNAL **59** · TRIGGER_EVENT **216** · SELL_WARNING **97**
  (día-vs-día contra el state del full-run 09-22; refrescos del día movieron
  scores, por eso las caídas ≥10pts)
- **Fallos de analyze:** 0

### Top 10 oportunidades (Russell)

| # | Ticker | Company | Score | Rank | P/E | FCF yield | Signal |
|---|---|---|---|---|---|---|---|
| 1 | SBH | Sally Beauty Holdings | 84.7 | 84.2 | 8.1 | 10.9% | BUY |
| 2 | ZD | Ziff Davis | 86.3 | 83.3 | 42.1 | 14.4% | BUY |
| 3 | LCII | LCI Industries | 88.0 | 83.2 | 11.4 | 13.0% | BUY |
| 4 | JBSS | Sanfilippo & Son | 89.7 | 82.7 | 12.8 | 4.5% | BUY |
| 5 | SAM | Boston Beer | 77.9 | 82.6 | 15.8 | 12.5% | BUY |
| 6 | VLGEA | Village Super Market | 89.2 | 81.9 | 12.3 | 5.1% | BUY |
| 7 | FLO | Flowers Foods | 79.3 | 81.2 | 5.0 | 22.5% | BUY |
| 8 | SIG | Signet Jewelers | 77.1 | 81.0 | 13.1 | 13.7% | BUY |
| 9 | MZTI | Marzetti Co | 89.7 | 81.0 | 14.8 | 7.3% | BUY |
| 10 | SHOE | Shoe Station | 83.7 | 80.9 | 4.9 | 19.1% | BUY |

## 4. European run

Parámetros: `--universe european --max-refresh 50 --top 20`

- **Duración:** ~5 min (refresh 22 s · 9 synced)
- **Universo:** 59 (SEC-filer subset del master) · **passed screen:** 42 (71%)
- **SEC refresh:** 9 refreshed · 9 stale · 0 unmapped
- **Precios:** limpio
- **Alertas:** TRIGGER_EVENT **3** (ASML, ABBNY, LOGI — MEDIUM) · BUY_SIGNAL **0** · SELL_WARNING **0**
- **Sin fundamentos (17, 20-F/ADR/OTC sin XBRL — esperado, screen-out limpio):**
  AKZOY, BMDPF, BZLFY, DTEGY, EONGY, ESYJY, FLIDY, HKHHY, IFNNY, LSEGY,
  PRYMF, PS, RTNTF, SCMWY, SLFPY, TGOPF, VWSYF

### Top 10 oportunidades (European)

| # | Ticker | Company | Score | Rank | P/E | FCF yield | Signal |
|---|---|---|---|---|---|---|---|
| 1 | LOGI | Logitech Intl | 78.7 | 82.5 | 21.3 | 6.4% | BUY |
| 2 | QGEN | Qiagen N.V. | 78.5 | 80.9 | 21.2 | 5.0% | BUY |
| 3 | ABBNY | ABB Ltd | 84.3 | 78.2 | 49.1 | 1.9% | BUY |
| 4 | ASML | ASML Holding | 82.3 | 75.6 | 69.9 | 1.7% | BUY |
| 5 | FMS | Fresenius Medical Care | 65.9 | 72.9 | 10.1 | N/A | WATCHLIST |
| 6 | AMRZ | Amrize Ltd | 40.9 | 70.4 | 18.0 | 6.7% | AVOID |
| 7 | ALC | Alcon | 53.5 | 66.2 | 32.4 | N/A | AVOID |
| 8 | RELX | RELX PLC | 37.3 | 63.3 | 27.6 | N/A | AVOID |
| 9 | STM | STMicroelectronics | 62.6 | 63.2 | 285.3 | N/A | WATCHLIST |
| 10 | DEO | Diageo | 38.2 | 62.1 | 19.1 | N/A | AVOID |

## 5. Full universe run

Parámetros: `--universe all --max-refresh 200 --top 20`

- **Duración:** 3,022 s (~50.4 min) — refresh **2,258 s** · prices 1,262 s
  (solapadas bajo el refresh) · analysis 763 s
- **Universo:** 2,528 · **passed screen:** 2,448 (97%) · 80 sin datos suficientes
- **SEC refresh:** 200 refreshed (cap) · 1,405 still stale · **10 unmapped**
  (mismo set conocido) · 1,205 deferred
- **Precios:** 7 `mapping gap` (AIRJ, ATLC, BH, FGBI, GLIBK, HOS, LILAK —
  clase no ingerida) · 11 `quote glitch` (Yahoo 401 "Invalid Crumb" /
  rate-limit transitorio — p. ej. SBMT); SBH/LCII/ZD/MZTI aparecen en el
  top-20 con precio N/A pero fundamentals intactos
- **Alertas:** BUY_SIGNAL **78** (SP500 47 · Russell2000 31) · TRIGGER_EVENT **281**
  (SP500 33 · Russell2000 244 · Nasdaq100 3 · European 1; **8 HIGH**: AMCR,
  CAH, GPN, HII, MCK, AGX, AZZ, NGVT) · SELL_WARNING **0** — artefacto: el
  state previo era el del run europeo (59 tickers), no el día anterior
- **Fallos de analyze:** 0
- Hallazgo: el `NameError` del escenario 3 se arregló ANTES del full; el fix
  se validó en vivo (clasificador funcionando sin excepción).

### Top 20 oportunidades (full universe)

| # | Ticker | Company | Score | Rank | P/E | FCF yield | Signal |
|---|---|---|---|---|---|---|---|
| 1 | BF-B | Brown-Forman | 95.5 | 86.6 | 16.7 | 7.5% | BUY |
| 2 | PAYX | Paychex | 88.9 | 85.1 | 21.5 | 6.1% | BUY |
| 3 | HII | Huntington Ingalls | 90.1 | 84.4 | 17.7 | 7.4% | BUY |
| 4 | ACN | Accenture | 92.2 | 84.3 | 14.8 | 9.6% | BUY |
| 5 | DGX | Quest Diagnostics | 88.8 | 84.3 | 26.0 | 5.3% | BUY |
| 6 | ABBV | AbbVie | 88.1 | 83.8 | 112.0 | 3.8% | BUY |
| 7 | SBH | Sally Beauty | 84.7 | 83.3 | N/A* | N/A* | BUY |
| 8 | CBOE | Cboe Global Markets | 83.9 | 83.1 | 26.0 | 5.9% | BUY |
| 9 | LCII | LCI Industries | 88.0 | 82.7 | N/A* | N/A* | BUY |
| 10 | ZD | Ziff Davis | 86.3 | 82.6 | N/A* | N/A* | BUY |
| 11 | BR | Broadridge | 84.7 | 82.5 | 16.7 | 6.8% | BUY |
| 12 | MKC | McCormick | 92.7 | 82.5 | 16.6 | 5.6% | BUY |
| 13 | DRI | Darden Restaurants | 85.8 | 82.4 | 20.3 | 4.6% | BUY |
| 14 | DG | Dollar General | 87.0 | 82.3 | 23.7 | 6.3% | BUY |
| 15 | INTU | Intuit | 84.5 | 82.0 | 16.9 | 11.2% | BUY |
| 16 | BDX | Becton Dickinson | 83.8 | 81.3 | 29.6 | 5.4% | BUY |
| 17 | APTV | Aptiv | 91.7 | 81.1 | 56.9 | 16.3% | BUY |
| 18 | CF | CF Industries | 79.1 | 81.0 | 12.6 | 9.8% | BUY |
| 19 | LOW | Lowe's | 85.5 | 80.9 | 15.6 | 7.1% | BUY |
| 20 | MZTI | Marzetti Co | 89.7 | 80.9 | N/A* | N/A* | BUY |

\* Precio N/A por glitch Yahoo (crumb 401) en el snapshot; score por fundamentals.

### Top TRIGGER_EVENT (full universe, HIGH)

8 HIGH: **AMCR** (aceleración ingresos, rank 85.9 BUY), **CAH** (ROIC),
**GPN** (margen bruto), **HII** (FCF), **MCK** (ROIC), **AGX** (ROIC),
**AZZ** (FCF), **NGVT** (FCF). MEDIUM representativos: ABNB (ROIC), ADM
(FCF), ALNY (FCF), APP (ROIC), ARM (FCF), BALL (FCF), BNY (FCF). Todos
positivos según la calibración (floors + percentil 0.92; mejoras persistentes
dos periodos).

## 6. Post-run verification

| Check | Pre-run | Post-run | Veredicto |
|---|---|---|---|
| `prices` | 152 | **152** | ✅ **sin precios persistidos** |
| `companies` | 8,023 | 8,023 | ✅ estable |
| `financial_facts` | 76,067,275 | **76,073,925** | ✅ +6,650 (refrescos del día) |
| `filings` | 1,092,021 | **1,092,196** | ✅ +175 (refrescos del día) |
| `import_runs` (6 h) | — | 200 × success (full: 20:13→20:50) | ✅ ledger registrado (Russell 100 + Europeo 9 quedaron fuera de la ventana 6h por el restart del server) |

Reportes en `data/reports/`: `daily_2026-09-23.md` (final = full universe),
`report_european_2026-09-23.md` (archivo intermedio), `workflow_all_2026-09-23.log`.
Nota operativa: un restart del server vació `/tmp/opencode/` a mitad de sesión
(se perdieron los logs de Russell/Europeo y el archivo del reporte Russell);
las métricas de esos dos escenarios se recuperaron de capturas en-sesión y se
archivaron los artefactos del Europeo dentro del repo.

## 7. Score distribution y comparación cross-universe

Distribución de `total_score` (0–100) de todos los analizados (state del full
run, 2,448 compañías; **no** solo top-20):

| Universo | n | min | p10 | med | p90 | max | mean |
|---|---|---|---|---|---|---|---|
| **Full 2,528** | 2,448 | 2.5 | 26.1 | 49.9 | 79.3 | 95.5 | 51.0 |
| SP500 (en full run) | 499 | 21.0 | 39.1 | 67.5 | 87.0 | 95.5 | 65.2 |
| Nasdaq-100 (en full run) | 98 | 4.0 | 39.3 | 72.3 | 86.3 | 93.2 | 66.6 |
| Russell 2,000 (en full run) | 1,896 | 2.5 | 24.7 | 47.1 | 72.0 | 93.8 | 47.6 |
| European (en full run) | 42 | 20.5 | 24.7 | 29.7 | 65.9 | 84.3 | 36.8 |

Frente al run 09-22 (full med 47.8, mean 49.2): mediana/mean ligeramente
superiores (49.9 / 51.0) — los refrescos del día trajeron datos más frescos a
Russell. **Bien dispersos (p10 26.1 → p90 79.3), no agrupados en 40–60** —
decisión válida para discriminación cross-seccional.

## 8. Tickers con fallas recurrentes

| Categoría | Tickers | Naturaleza |
|---|---|---|
| Mapping (unmapped) | BELFB, BATRK, CENTA, HOS, LILAK, GLIBK, ATLC, BH, AIRJ, FGBI | Russell class-variant / no ingerido — esperado, documentado |
| Glitch Yahoo | SBMT, SBH, LCII, ZD, MZTI (11 eventos) | Crumb 401 / rate-limit transitorio; retry auto — glitch, no defecto |
| Sin XBRL (informacional) | VGNT, PFBC, GENB, HMH, SWMR + 9 europeos ADR | `EdgarProvider returned no data` pre-XBRL; sin impacto de datos |
| Analyze failures | **0** en los 3 escenarios | — |

Sin fallos recurrentes nuevos: los 14 "no data" ya existían en 09-22.

## 9. Nuevos nombres de calidad (Russell 2000 / European)

- **Russell 2000 con score > 70: 222 empresas.** Top: **CRI 93.8**,
  **EAT 92.7**, **HCKT 92.5**, **SXI 92.2**, **UTMD 91.8**, **WDFC 91.3**,
  MZTI 89.7, JBSS 89.7, JJSF 89.4, VLGEA 89.2, TPB 88.9, FELE 88.4,
  LCII 88.0, SHOO 88.0, HBB 87.7 — small-caps con ROIC alto y FCF positivo
  que antes del universo expandido no se puntuaban.
- **Europeos en el top-50 del full run: ninguno.** Europa aporta amplitud
  (LOGI/QGEN/ABBNY/ASML en BUY), no alfa — coherente con 09-22.

## 10. Sanity-check top-5 (analyze-full --no-refresh)

| Ticker | Score | Buffett | Moat | ROE | ROIC | Op.marg | D/E | FCF | Notas |
|---|---|---|---|---|---|---|---|---|---|
| BF-B | 95.5 | 93.6 | STRONG | 17.8% | 12.7% | 25.5% | 0.62 | $893M | revenue −1.2% (flag suave: marca premium estable); Altman 1.80; anóm. FCF up (z 3.05) |
| PAYX | 88.9 | 85.4 | STRONG | 47.1% | 27.5% | 38.6% | 1.22 | $2.3B | crecimiento 16.9%; D/E algo elevado (negocio de servicios) |
| HII | 90.1 | 88.5 | STRONG | 11.9% | 5.4% | 5.3% | 1.06 | $794M | ROIC modesto (defensa capital-intensiva) — coherente |
| ACN | 92.2 | 93.0 | STRONG | 24.6% | 32.5% | 14.7% | 0.17 | $10.9B | calidad de libro; D/E mínimo; CROIC 43.7% |
| DGX | 88.8 | 81.7 | STRONG | 13.8% | 10.3% | 14.1% | 0.72 | $1.4B | crecimiento 11.8%; fines marcadores coherentes |

Los scores se sostienen: alta confianza (HIGH), moat STRONG, sin pérdidas,
FCF positivo; el único flag genuino es la tope de crecimiento de BF-B. (Los
precios de la sección 2 salieron N/A en esta corrida por el mismo 429 de
Yahoo al arrancar — artefacto de red, no de datos.)

## 11. Observaciones y recomendaciones

1. **Bug encontrado y arreglado en el propio test**: `NameError` de
   `PRICE_FAILURE_*` en `_classify_price_failures` (`a263ea8`) — detalle de
   alcance: las constantes vivían en un import local a `_run()`. Clase nueva
   `TestClassifyPriceFailures` (2 tests). Suite: **503 passed / 1 skipped**.
2. **Reducción real de duración vs 09-22**: full universe 3,148 s → **3,022 s**
   (~4% menos) pese a refrescar 200 igual; refresh 1,652 s → 2,258 s (el
   volumen de sincronización del día fue mayor); prices ahora solapadas en
   su mayoría (1262 s vs 1,168 s reales pero críticos ≈ 0). Con menos stale
   (drenando el backlog + `--resume` multi-día), el objetivo ~25-30 min sigue
   viable.
3. **Yahoo flaky durante el full run (401 crumb / 429)**: 11 glitches; el
   retry único + clasificación funcionaron (sin drop masivo). Los N/A de
   precio en top-20 (SBH/LCII/ZD/MZTI) se explican — re-snapshots con
   `--no-refresh` recuperan el precio sin tocar fundamentals.
4. **SELL_WARNING 0 en el full run es artefacto de secuencia** (state previo =
   europeo). Alerta honesta: cuando un run repite universo, los SELL_WARNING
   day-over-day vuelven a ser significativos (Russell de hoy: 97).
5. **WIP del usuario**: `backend/analytics/scoring/composite.py` **stasheado**
   (`WIP interpretation/scoring`) por estar incompleto — añade `per` al
   composite sin cablearlo en `backend/analytics/service.py:290` (reescalaría
   todos los scores sin intención). `backend/analytics/interpretation.py`
   (P/B <1 → "Muy barato") committeado (`948ea25`) e incluido en el run.
6. **WIP del usuario aparecido durante la ejecución (NO tocado)**: se detectó
   `backend/services/price_service.py` modificado en la working tree a las
   20:44 (mitad del full run): bump de pacing anti-rate-limit (delays
   0.2→0.5 s, pausa de 60 s tras ~60 requests, 3 retries con backoff
   exponencial en `.info`) y métodos nuevos `get_market_cap` /
   `get_enterprise_value` / `get_beta`. Es trabajo externo a esta sesión — se
   deja **sin commitear ni validar** para revisión del usuario. Los N/A de
   precio del top-20 se produjeron en la fase previa a ese cambio (401/429 de
   Yahoo); no están relacionados.
7. **Gateway**: sin rendijas — precios nunca persistidos (152→152), DB
   íntegra, sin DELETEs, sin push, `refresh_workers` sin tocar (2).