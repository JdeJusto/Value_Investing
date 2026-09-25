# Informe de pruebas y correcciones — 2026-09-23

## 1. Resumen ejecutivo

- Los **5 bugs** solicitados han sido corregidos, más **1 bug adicional** detectado
  durante las pruebas (fecha de cierre del ejercicio fiscal en
  `get_fiscal_year_end_date`) y 1 endurecimiento (año `int` en
  `get_split_adjustment`).
- Suite unitaria: **524 passed, 1 skipped** (~19 s). El único skip es
  preexistente y de entorno: la base SQL legacy `value_investing` no existe en
  este equipo.
- Batería de integración (CLI) completa: **todos los comandos funcionan**
  (análisis individual, valoración histórica, screener, oportunidades, momentum,
  backtest, alertas, flujo diario, comparación de fuentes, SQL scripts, debug).
- La discrepancia de precio detectada (cierre "FY2025" = 168.93 en vez de
  254.52) quedó **explicada y corregida** (bug 6).
- Comparación con datos reales de internet: fundamentales FY2024 **idénticos**
  (coincidencia exacta con los 10-K), precios actuales **±0.3 %** de la cotización
  de referencia.
- Todos los cambios siguen **sin commitear** en el repo (18 ficheros modificados,
  1 nuevo).

---

## 2. Bugs corregidos

### 2.1 REIT / bancos: ingresos reconstruidos (FinancialDatabaseRepository)

`backend/repositories/financial_database_repository.py`

- El override de bancos (`InterestIncomeExpenseNet` + `NoninterestIncome`) solo
  se aplica cuando la suma es **> 0 y domina** al tag de ingresos elegido.
- El override de rentas (REIT) solo se aplica cuando las rentas son **> 0**.
- Compatibilidad con la clave `interest_income` cuando falta
  `InterestIncomeExpenseNet`.

### 2.2 `_usable()`: registros sin score (source_selection.py)

- Un registro sin nota de calidad (quality `None`) es usable **solo si lleva
  `revenue` o `net_income`**.
- Los registros con score siguen usando el umbral ≥ 0.5.

### 2.3 `health_cap`: topes graduados (ranking_engine.py)

- FCF negativo → cap 60; D/E ≥ 1.5 → cap 52; cobertura de intereses < 3x → cap 48.
- Se aplica el **mínimo de todos los topes coincidentes**.
- La cobertura de intereses negativa (empresas con pérdidas) también se topea.
- Tolerancia a la clave `free_cash_flow` ausente.

### 2.4 BUY con confianza LOW (signals.py + alert_engine.py)

- Las señales BUY con confianza LOW ahora disparan alerta solo con una barra
  más alta: **rank ≥ 80, composite ≥ 75, buffett ≥ 50**.
- Se eliminó el filtro redundante HIGH/MEDIUM en `_buy_alert` (alert_engine.py)
  y se actualizó `can_buy`.

### 2.5 Métricas de calidad / moat (quality_metrics.py, moat_analysis.py)

- `compute_quality_metrics([])` devuelve un dict todo-None (antes IndexError).
- `fcf_growth` exige **≥ 3 años** de FCF (con 2 → None, no 0.0 degenerado).
- `moat_analysis` usa `.get()` (dict parcial/vacío no lanza KeyError; historia
  vacía → moat NONE).

### 2.6 (NUEVO) Fecha de cierre del ejercicio fiscal — `get_fiscal_year_end_date`

**Síntoma:** `historical-valuation AAPL` mostraba "Precio de cierre: 168.93"
para FY2025, incoherente con `get_price_on_date("AAPL","2025-09-27") = 254.52`.

**Causa raíz:** el bucket `fiscal_year=2025` de AAPL contiene los comparativos
del 10-K (FY2023, FY2024) **mal etiquetados como 2025**. El comparativo de
FY2023 tiene un span anual mayor (370 días vs 363 del hecho real) y ganaba la
ordenación `span DESC`, devolviendo `2023-09-30` para **todos** los años
recientes. La consulta usaba el precio cercano a sep-2023 (168.93) en lugar del
cierre real del ejercicio 2025 (254.52). Verificado directamente en la BD:

```
fiscal_year | period_end | span | n
2025        | 2023-09-30 |  370 | ...  <- comparativo mal etiquetado (ganaba antes)
2025        | 2025-09-27 |  363 | ...  <- cierre real del ejercicio
2025        | 2024-09-28 |  363 | ...  <- comparativo
```

**Fix (para cualquier ticker, no solo AAPL):** la `ORDER BY` ahora prioriza los
hechos cuyo `period_end` cae en el **año calendario del bucket**
(`EXTRACT(YEAR ...) = fiscal_year`), y solo como desempate usa span y
`period_end`. Esto anula también el caso Salesforce (trimestres suplementarios
del 10-K retaggeados 'FY' en el mismo año calendario, pero con span corto) sin
perder la regla de anclaje a conceptos core (no Entity%/fee schedules).

Resultado verificado contra la BD real:

| Ticker | FY2023 | FY2024 | FY2025 |
|---|---|---|---|
| AAPL | 2023-09-30 | 2024-09-28 | 2025-09-27 |
| MSFT | 2023-06-30 | 2024-06-30 | 2025-06-30 |
| KO | 2023-12-31 | 2024-12-31 | 2025-12-31 |
| CRM | 2023-01-31 | 2024-01-31 | 2025-01-31 |
| WFC / CPT | 2023-12-31 | 2024-12-31 | 2025-12-31 |

Solo AAPL resultaba afectado (MSFT/KO/CRM/WFC/CPT ya eran correctos).

**Bonus:** `get_split_adjustment` ahora acepta también un año fiscal `int`
(resuelto a 31-dic, igual que `get_price_at_fiscal_year_end`); antes un `int`
lanzaba `TypeError`.

---

## 3. Tests automatizados

```bash
FINANCIAL_DATABASE_URL=... .venv/bin/python -m pytest tests/unit -q
# 524 passed, 1 skipped in ~19s
```

El skip: `test_financial_database_integration.py::...` — "Existing SQL repository
not available" (la BD legacy `value_investing` no existe en este equipo;
preexistente, no relacionado con los cambios).

Tests nuevos/añadidos:
- `test_fdb_normalize_revenue.py` (nuevo): 8 casos de regresión banco/REIT.
- `test_screener.py`: topes graduados de health_cap, mínimo de múltiples
  condiciones, cobertura negativa.
- `test_alerts.py`: BUY LOW dispara con la barra alta; no dispara por debajo.
- `test_repository_multi_source.py`: `_usable` con/ sin score.
- `test_intelligence.py`: historia vacía, `fcf_growth` con 2 vs 3 años, moat
  con dict vacío.
- `test_validation_comparison.py`: regla de año-calendario en el FYE
  (simulación de la polución AAPL + aserciones de SQL).
- `test_financial_database_integration.py`: regresión contra AAPL real
  (FY2023/24/25 → fechas correctas).
- `test_price_service.py`: `get_split_adjustment` con año `int`.

---

## 4. Batería de integración (CLI)

| Comando | Resultado |
|---|---|
| `analyze AAPL MSFT KO` | OK — precios obtenidos, market cap presente |
| `analyze-full AAPL` | Informe de 6 secciones completo (calidad, DCF, alertas, anomalías) |
| `buffett-analysis AAPL` | Buffett 74.7, moat STRONG (85), composite 82.9, confianza HIGH |
| `historical-valuation AAPL` | **Corregido** — FY2025 cierre 254.52 (antes 168.93); serie histórica coherente |
| `historical-valuation WFC CPT` | OK para banco y REIT (EPS/P/E correctos) |
| `data-status AAPL` | 2009–2025 frescos, sin refresco necesario |
| `screener --tickers ... --filter 'moat=STRONG'` | KO WATCHLIST, MSFT/AAPL HOLD; degradación elegante de la metadata SQL legacy |
| `momentum AAPL MSFT KO` | AAPL trigger ROIC, MSFT aceleración de ingresos, KO sin movimientos |
| `opportunities --tickers AAPL,MSFT,KO` | MSFT COMPOUNDERS + INFLECTION_POINT + QUALITY_WITH_TRIGGER |
| `backtest AAPL MSFT KO --prices ...` | 4 snapshots, CAGR 9.8 %, Sharpe 1.23, win rate 75 % |
| `alerts AAPL MSFT KO` | AAPL → TRIGGER_EVENT (mejora de ROIC) |
| `scripts/compare_sources.py AAPL MSFT KO --provider yahoo` | FDB == Yahoo (sin discrepancias > 5 %) |
| `sql-analysis company_overview --ticker AAPL` | Ejecuta el script SQL reutilizable de FDB (CIK resuelto) |
| Flujo diario (`daily_workflow --limit 5`) | Reporte + estado + alertas (ABBV BUY_SIGNAL HIGH; AAPL/ABNB trigger) |
| `debug` | Diagnóstico completo: 7/7 filtros, servicios, screener |

---

## 5. Comparación con datos de internet (2026-09-23)

### 5.1 Fundamentales FY2024 (10-K reales publicados) — coincidencia exacta

| Ticker | Revenue (FDB) | Real (10-K) | Net Income (FDB) | Real (10-K) |
|---|---|---|---|---|
| AAPL | 391.035 B | 391.035 B ✓ | 93.736 B | 93.736 B ✓ |
| MSFT | 245.122 B | 245.122 B ✓ | 88.136 B | 88.136 B ✓ |
| KO | 47.061 B | 47.061 B ✓ | 10.631 B | 10.631 B ✓ |
| WFC | 82.296 B | 82.296 B ✓ | 18.606 B | 18.606 B ✓ |
| CPT | 1.544 B | 1.544 B ✓ | 163 M | 163 M ✓ |
| JPM | 177.556 B | 177.556 B ✓ | 56.868 B | 56.868 B ✓ |

### 5.2 Precios actuales (2026-09-23) — desviación mínima

| Ticker | Cotización de referencia (web) | Nuestro precio | Δ |
|---|---|---|---|
| AAPL | $336.28 | $335.90–337.02 | ~0.3 % |
| MSFT | $500.25 | $500.59 | ~0.1 % |
| KO | $87.79 | $88.10 | ~0.4 % |

### 5.3 Nota sobre el "año simulado"

La BD Financial-DataBase ya contiene **FY2025/FY2026** (datos que en el mundo
real aún no existían para varias empresas). Ese futuro simulado **no se puede
contrastar** con internet por diseño; todas las comparaciones de fundamentales
se anclan en **FY2024** (verificadas exactas) y en **cotizaciones actuales**
para precios.

---

## 6. Observaciones no bloqueantes

1. **BD SQL legacy `value_investing` ausente** en este equipo: el screener y la
   metadata de empresa imprimen errores de conexión en stderr y degradan con
   elegancia (el análisis continúa). No afecta a los resultados.
2. **KO Total Liabilities N/A** en `compare_sources`: gap puntual de
   reconstrucción en FDB (el resto de métricas de KO coincide con Yahoo).
3. **`historical-valuation`** muestra una fila N/A para el ejercicio en curso
   (p. ej. 2026 en WFC/CPT) antes de que existan datos: cosmético, la fila del
   último ejercicio real es correcta y completa.
4. Los precios se mantienen **solo en memoria** (nunca persistidos), conforme
   al diseño; la caché (TTL 15 min) y el backoff de rate-limit de Yahoo ya
   estaban activos.

---

## 7. Estado del repo

- 18 ficheros modificados + 1 nuevo (`tests/unit/test_fdb_normalize_revenue.py`)
  y 3 informes nuevos (`docs/reporte_pruebas_2026-09-23.md`).
- **Sin commits** realizados durante esta tarea.