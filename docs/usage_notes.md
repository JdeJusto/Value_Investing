# Usage notes — auditoría y notas de uso

Este fichero tiene dos partes:

- **Parte A**: auditoría funcional automatizada (rellenada por el agente).
- **Parte B**: notas de uso real (plantilla vacía, para que el humano la
  rellene durante 1-2 semanas).

La auditoría es de solo lectura sobre el producto. Los outputs completos
quedaron en `/tmp/opencode/audit_usage/` y no se versionan.

---

## Parte A — Auditoría funcional (2026-11-04)

### Tickers auditados

30 tickers, con diversidad de sectores, geografías y casos conocidos:

| Grupo | Tickers |
|---|---|
| Large caps US | AAPL, MSFT, JNJ, CAT, T, VZ, CSX, ADM, PG |
| Bancos | SAN, TD, JPM, BAC, BNS |
| IFRS / ADR | SNY, TTE, BTI, RACE, AZN |
| REITs / utilities | AMT, PLD, DUK, NEE |
| Derivados / problemáticos | PCAR, MRX, AAMI, BRUN, SKT |
| PoC / mid-small | BJRI, APA |

### Comandos ejecutados

- `vi scorecard <ticker> --no-color` para los 30.
- `vi financials <ticker> --no-color` para los 30.
- `vi financials <ticker> --json` para los 30.
- `vi dcf <ticker> --no-color` para los 30.
- `vi compare-methodologies <ticker> --no-color` para los 30
  (`methodologies show` espera un nombre de metodología, no un ticker).
- `vi rank --by graham`, `--by lynch`, `--combine graham,lynch` con
  `and` y `or` sobre los 30 tickers.
- `vi consensus AAPL --universe all` y
  `vi consensus-ranking --universe all`.
- `vi screener --tickers ... --no-prices --top 10`.
- Streamlit live (`VI_DEMO=0`) en las páginas registradas + flujo
  Analysis → Scorecard/Financials.

### Resultados por comando

| Comando | Tickers OK | Tickers con error/vacío | Exit codes != 0 |
|---|---|---|---|
| `vi scorecard` | 30 | 0 | — |
| `vi financials` | 30 | 13 con salida corta (<25 líneas): SAN, TD, BNS, SNY, TTE, BTI, RACE, AZN, PCAR, MRX, AAMI, BRUN, SKT | — |
| `vi financials --json` | 30 | 7 con `derived.equity` falso positivo (JNJ, CAT, T, VZ, CSX, ADM, PG); 5 sin `assets.current` (SAN, TD, BNS, PCAR, BRUN) | — |
| `vi dcf` | 30 | 14 con `INSUFFICIENT_DATA` (VZ, TD, SNY, TTE, BTI, RACE, AZN, DUK, NEE, MRX, AAMI, BRUN, SKT, APA) | — |
| `vi compare-methodologies` | 30 | Muchos N/A/INSUFFICIENT en bancos e IFRS (esperado por el guard financiero y por falta de split corriente/no corriente) | — |
| `vi rank` | OK | — | — |
| `vi consensus --universe all` | OK (2.450 empresas) | — | — |
| `vi screener` | OK (10 resultados, 9 s) | — | — |

### Bugs encontrados

#### AUDIT-001 — NCI equity no se reconoce como equity total (Alta)

- **Tickers**: JNJ, CAT, T, VZ, CSX, ADM, PG.
- **Comando**: `vi financials <ticker> --json` y la T-view de Streamlit.
- **Esperado**: `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`
  cuenta como equity total; JNJ: assets 199.210 B, liabilities 117.666 B,
  equity 81.544 B, delta 0.
- **Real**:
  - CLI JNJ: `total_equity=168.978 B` (RetainedEarnings), `delta=-87.434 B`,
    `derived.equity=true`.
  - Streamlit JNJ: `TOTAL LIABILITIES + EQUITY = 350.458 B` y
    `Δ = -151.248 B`.
  - El tag NCI no está en `MASS_SUBTOTAL_CONCEPTS` (UI) ni en
    `_EQUITY_TOTAL_CONCEPTS` (CLI).
- **Reproducción**:
  ```bash
  ./vi financials JNJ --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['derived'], d['liabilities_equity']['total_equity'], d['delta'])"
  ```
- **Severidad**: alta.
- **¿Bloquea uso real?**: sí para análisis de balance de esos 7 large caps;
  el scorecard usa otra ruta y no está afectado.

#### AUDIT-002 — La página Methodologies no está registrada en Streamlit (Alta)

- **Comando**: navegar a `/methodologies` en la app live.
- **Esperado**: página de ranking por metodología (UI 07).
- **Real**: renderiza Home; `ui/pages/07_methodologies.py` no está en
  `st.navigation` (`ui/app.py` registra 6 páginas, no 7/8).
- **Reproducción**: `streamlit run ui/app.py` y abrir `/methodologies`.
- **Severidad**: alta (feature completa inaccesible desde la UI).
- **¿Bloquea uso real?**: no bloquea la CLI (`vi rank` sí funciona), pero
  la UI no ofrece la funcionalidad.

#### AUDIT-003 — T-view/JSON vacío o escaso para bancos, IFRS y PCAR (Media)

- **Tickers**: SAN, TD, BNS, SNY, TTE, BTI, RACE, AZN, PCAR.
- **Comando**: `vi financials <ticker> --json` y `--no-color`.
- **Esperado**: line items de balance en `assets.current` / `liabilities_equity`.
- **Real**:
  - SAN/TD/BNS: `assets.current=[]` (no hay split corriente/no corriente;
    estructura bancaria).
  - SNY/TTE/BTI/RACE: `assets.current` con 1 item; `equity` vacío o casi.
  - PCAR: `assets.current=[]`; FDB solo expone el tag de cash restringido
    (`CashCashEquivalentsRestrictedCash...`) y no entra en el mapa actual.
- **Severidad**: media (bancos/IFRS es estructural; PCAR es recuperable).
- **¿Bloquea uso real?**: parcialmente para analizar el balance de esos tickers.

#### AUDIT-004 — MRX partial equity marcado como “Balanced” (Media)

- **Ticker**: MRX.
- **Comando**: `vi financials MRX --json` / T-view.
- **Esperado**: si el equity es parcial (`RetainedEarnings` only), no debería
  declararse balanceado.
- **Real**: `delta=281.6 M` (0.81 % de assets) y `balanced=true`; la UI
  muestra `✓ Balanced (Δ = +$281,600,000)` junto al caption de partial equity.
- **Causa**: tolerancia de balance del 1 % en `build_balance_model` y en
  `_totals`; el equity parcial no se excluye del chip.
- **Severidad**: media.
- **¿Bloquea uso real?**: no, pero es engañoso.

#### AUDIT-005 — `vi screener` refresca SEC por defecto (Media)

- **Comando**: `vi screener --tickers ... --no-prices --top 10`.
- **Esperado** (para una auditoría de solo lectura): no escribir.
- **Real**: el output mostró `4 synced with SEC · 6 untouched`; el comando
  hace refresh por defecto. En una auditoría de solo lectura hay que pasar
  `--no-refresh`.
- **Severidad**: media (efecto lateral operacional, no corrupción).
- **¿Bloquea uso real?**: no; documentar y usar `--no-refresh` cuando se
  quiera solo lectura.

#### AUDIT-006 — DCF sin motivo explícito para `INSUFFICIENT_DATA` (Baja)

- **Tickers**: VZ, TD, SNY, TTE, BTI, RACE, AZN, DUK, NEE, MRX, AAMI, BRUN,
  SKT, APA.
- **Comando**: `vi dcf <ticker> --no-color`.
- **Esperado**: un motivo (FCF negativo, falta de datos, banco, etc.).
- **Real**: solo `Verdict : INSUFFICIENT_DATA`; no se explica el campo que
  falta.
- **Severidad**: baja.
- **¿Bloquea uso real?**: no; es una mejora de explicabilidad.

#### AUDIT-007 — `vi consensus` sin ticker / `--universe demo` (Baja)

- **Comando**: `vi consensus --no-color` y `vi consensus --universe demo`.
- **Esperado**: un comando de consenso con un ticker o un universo válido.
- **Real**: sin ticker falla por argparse (correcto); `--universe demo` no
  encuentra el fichero (el demo vive en `data/demo/consensus`, con
  `universe=sp500`). `--demo` y `--universe all` funcionan.
- **Severidad**: baja (UX/documentación).
- **¿Bloquea uso real?**: no.

#### AUDIT-008 — JSON de financials sin `currency` (Baja)

- **Ticker**: SAN (EUR); aplica a cualquier emisor no USD.
- **Comando**: `vi financials SAN --json`.
- **Esperado**: moneda para interpretar los totales.
- **Real**: el contrato no incluye `currency`; la UI sí muestra `EUR`.
- **Severidad**: baja.
- **¿Bloquea uso real?**: no para un humano, sí para un consumidor
  multi-divisa.

### Gaps de datos

| Ticker | Campo | Situación | Causa conocida | ¿Recuperable? |
|---|---|---|---|---|
| MRX | equity | partial (RetainedEarnings only) | filing sin equity total | no |
| AAMI | equity | sin tag de equity en último FY | filing; equity derivable pero no se deriva | no (decisión) |
| BRUN | assets | sin `total_assets` | filing; assets derivable pero no se deriva | no (decisión) |
| SKT | balance | sin facts de balance FY2024/2025 | hueco de ingestión | sí (re-sync) |
| SAN, TD, BNS | current/non-current | sin split corriente/no corriente | estructura bancaria | no aplica |
| SNY, TTE, BTI, RACE | equity/current | line items incompletos | IFRS/20-F + clasificación actual | parcial |
| PCAR | assets.current | vacío | cash restringido no mapeado | sí (mapping) |
| AMT | balance | Δ 6.703 B (10.6 %) | componentes de liabilities/equity incompletos | por investigar |
| PLD | balance | Δ 4.561 B (4.6 %) | componentes incompletos | por investigar |
| NEE | balance | Δ 11.871 B (5.6 %) | componentes incompletos | por investigar |
| VZ, TD, SNY, TTE, BTI, RACE, AZN, DUK, NEE, MRX, AAMI, BRUN, SKT, APA | DCF | INSUFFICIENT_DATA | FCF/datos insuficientes o banco | depende del caso |

### Incoherencias CLI ↔ Streamlit

| Ticker | Campo | CLI | Streamlit | Delta | Causa |
|---|---|---|---|---|---|
| AAPL | total assets / L+E | 359.241 B / 359.241 B | 359.241 B / 359.241 B | 0 | OK |
| PCAR | liabilities / L+E | 25.0722 B* / 44.3362 B | 25.0722 B* / 44.3362 B | 0 | OK |
| MRX | L+E | 34.3935 B | 34.3935 B | 0 | Ambos “balanced” con equity parcial |
| SAN | assets / L+E | 1.867.515 B / 1.867.515 B | 1.867.515 B / 1.867.515 B | 0 | OK; CLI no expone EUR |
| AMT | assets / L+E | 63.1904 B / 56.4876 B | 63.1904 B / 56.4876 B | 0 | Ambos no balancean |
| JNJ | L+E / delta | 199.210 B / -87.434 B | 350.458 B / -151.248 B | **151.248 B** | AUDIT-001 |

No se detectaron diferencias de cifras entre CLI y UI para AAPL, PCAR, MRX,
SAN o AMT; la discrepancia real es JNJ (y los otros NCI large caps) por
AUDIT-001.

### Ranking

- `graham`: 15 resultados, orden descendente, sin N/A; top `T` 42.86.
- `lynch`: 19 resultados, orden descendente, sin N/A; top `CAT` 60.00.
- `combine AND`: 0 resultados.
- `combine OR`: 8 resultados, orden descendente; top `MSFT` 34.285.
- AND ≤ OR, sin N/A incluidos por defecto.

### Consensus

- Fichero `data/consensus/consensus_2026-11-04.json`: 2.450 empresas.
- Distribución de veredictos: BUY 486, WATCH 1.188, HOLD 2.126,
  AVOID 6.795, INSUFFICIENT_DATA 5.565, N/A 3.440.
- 377 empresas con BUY y AVOID a la vez (disagreement real).
- 430 empresas con todas las metodologías N/A/INSUFFICIENT_DATA.
- `vi consensus AAPL --universe all` y `consensus-ranking --universe all`
  funcionan. `--universe demo` no encuentra el fichero demo (AUDIT-007).

### Screener

- 10 tickers, `--no-prices`, 10 resultados en 9 s.
- Cifras plausibles (AAPL ROE 151.9 %, ROIC 82.3 %, D/E 1.34; MSFT ROE
  30.2 %, etc.). P/E y FCF yield N/A por `--no-prices`.
- El comando hizo `4 synced with SEC · 6 untouched` (AUDIT-005).

### Verificación visual (Streamlit)

| Página | Estado |
|---|---|
| Home | OK; portfolio vacío, top opportunities vacío, latest report 2026-11-04 |
| Analysis → AAPL | OK; scorecard y financials sin excepción |
| Screener | OK; página carga filtros (no se ejecutó el screener desde la UI) |
| Portfolio | OK; estado vacío correcto |
| Reports | OK; report 2026-11-04 disponible |
| Consensus | OK; página carga |
| Methodologies | **ERROR**: `/methodologies` renderiza Home (AUDIT-002) |

No se evaluó el aspecto visual (colores/layout), solo que no hubiera
excepciones y que las páginas cargaran.

### Resumen

- **Total bugs**: 8 (2 alta, 3 media, 3 baja).
- **Total gaps de datos**: 11 filas de la tabla (varios tickers por fila).
- **Total incoherencias CLI ↔ Streamlit**: 1 real (JNJ/large caps NCI),
  más diferencias de formato (currency, total equity row).
- **Comandos que fallan sistemáticamente**: ninguno (todos los exit codes
  auditados fueron 0; los “fallos” son datos vacíos/N/A o semántica).
- **Tickers que fallan en algún comando**: JNJ, CAT, T, VZ, CSX, ADM, PG
  (AUDIT-001); MRX (AUDIT-004); PCAR/SAN/TD/BNS/SNY/TTE/BTI/RACE (AUDIT-003);
  BRUN/SKT/AAMI (gaps conocidos).

---

## Parte B — Notas de uso real (para rellenar por el humano)

> **Instrucciones**: durante las próximas 1-2 semanas, cada vez que uses el
> sistema (CLI o app), añade una entrada abajo. No hace falta ser exhaustivo.
> Solo lo que te frustre o te sorprenda. Al cabo de 1-2 semanas, revisa qué
> se repite.

### Tickers analizados (uso real)

- TODO: [ticker] · [qué buscaba] · [qué encontré] · [qué faltó]

### Fricciones (por orden de frecuencia)

- TODO: [fricción] · [cuántas veces] · [impacto: bloqueante/molesta/poco]

### Bugs encontrados (nuevos, no en Parte A)

- TODO: [ticker] · [campo] · [esperado] · [real] · [contexto]

### Features que usaría si existieran

- TODO: [feature] · [por qué] · [alternativa actual]

### Comandos que más uso

- TODO: [comando] · [frecuencia] · [por qué]

### Comandos que nunca uso

- TODO: [comando] · [por qué] · [¿eliminar? sí/no]

---

## Próxima decisión

Tras 1-2 semanas de uso real, revisar:

1. ¿Cuántas fricciones se repiten 5+ veces? → Candidatas a feature.
2. ¿Cuántos bugs nuevos aparecen? → Prioridad.
3. ¿Qué comandos no se usan? → Candidatos a deprecar/mejorar.
4. ¿Qué parte del plan original (T-view side-by-side, `--json` en 40
   comandos, FDB-3, etc.) resuelve una fricción real? → Priorizar.
5. ¿Qué parte NO resuelve nada real? → Descartar.
