# Value Investing

Plataforma de análisis fundamental en terminal: carga de datos financieros desde
múltiples fuentes (Yahoo Finance y EDGAR/SEC), evaluación de calidad empresarial
estilo Buffett, detección de oportunidades, seguimiento de cartera, backtesting
y alertas. Todo determinista, sin ML y sin dependencias de redes sociales.

## Características

- **Datos**: pipeline multi-fuente (Yahoo + EDGAR) con fallback automático,
  calidad por año, frescura y refresco bajo demanda
- **Inteligencia**: filtro**: filtro Buffett (4 pilares), análisis de moat, métricas de
  calidad (ROIC, owner earnings, CV, CAGR...), scoring compuesto con rating y
  confianza, deltas interanuales y detección de anomalías (z-score)
- **Screener**: filtros por valor/calidad, ranking con momentum fundamental,
  señales BUY/WATCHLIST/HOLD/AVOID y 7 tipos de oportunidad
- **Portfolio**: posiciones con tesis y señal de entrada, PnL realizado/no
  realizado, concentración de riesgo (HHI), exposición por sector
- **Backtesting**: simulación determinista sobre snapshots anuales (CAGR,
  max drawdown, Sharpe, win rate)
- **Alertas**: BUY_SIGNAL, SELL_WARNING y TRIGGER_EVENT con notificadores
  extensibles
- Interfaz web Streamlit para screener y análisis detallado

## Requisitos

- Python >= 3.11
- Pipenv
- PostgreSQL (opcional; sin él se usa el repositorio JSON)

## Instalación

```bash
git clone <repo-url>
cd Value_Investing
pipenv install --dev
```

El entorno virtual se crea automáticamente en `.venv/`.

## Configuración

Copia `.env.example` a `.env`:

| Variable | Descripción | Por defecto |
|---|---|---|
| `SEC_EMAIL` | Email de identificación en EDGAR | tu-email@ejemplo.com |
| `SEC_NAME` | Nombre para EDGAR | Tu Nombre |
| `DATABASE_URL` | PostgreSQL (activar con `docker-compose up -d db`) | postgresql://postgres:postgres@localhost:5432/value_investing |
| `PORTFOLIO_PATH` | Ruta del archivo JSON de cartera | data/portfolio.json |
| `FINANCIAL_DATABASE_URL` | Conexión a Financial-DataBase (fundamentales; los precios NO se almacenan, se consultan en tiempo real) | postgresql://financial:test@localhost:5432/financial_database |
| `PRICE_CACHE_TTL` | TTL (segundos) de la caché en memoria de precios reales | 900 (15 min) |

```bash
docker-compose up -d db        # base de datos opcional
pipenv run python main.py debug   # verifica que todo funciona
```

## Empezar en 2 minutos

```bash
# 1. Carga datos de un ticker (10 años fiscales, multi-fuente)
pipenv run python main.py load-data AAPL

# 2. Calidad empresarial estilo Buffett + moat + insights
pipenv run python main.py buffett-analysis AAPL

# 3. Busca oportunidades en todo lo cargado
pipenv run python main.py screener --tickers AAPL,KO --filter moat=STRONG min_score=80
pipenv run python main.py opportunities

# 4. Sigue tu cartera
pipenv run python main.py portfolio add AAPL 10 180 --thesis "moat fuerte" --signal BUY
pipenv run python main.py portfolio view
pipenv run python main.py portfolio performance

# 5. Backtest y alertas
pipenv run python main.py backtest --strategy momentum --top 3
pipenv run python main.py alerts

# 6. Análisis histórico de valoración (P/E y FCF yield)
pipenv run python main.py historical-valuation AAPL MSFT

# 7. Comparar datos entre fuentes
pipenv run python scripts/compare_sources.py AAPL MSFT KO

# 8. Ejecutar scripts SQL reutilizables de Financial-DataBase
pipenv run python main.py sql-analysis --script company_overview --cik 0000320193
pipenv run python main.py sql-analysis --script financial_series --cik 0000320193
pipenv run python main.py sql-analysis compare --ciks 0000320193,0000789019
```

## Referencia de comandos

Todos los comandos se ejecutan con `pipenv run python main.py <comando>`.

### `load-data TICKERS... [--years N] [--force]`
Pipeline completo (fetch → normalizar → almacenar). Multi-fuente con
fallback: Yahoo primero, EDGAR si falla; por defecto 10 años fiscales.
`--force` re-descarga aunque existan datos.

### `data-status TICKERS...`
Por ticker y año fiscal: fuente usada, cobertura, calidad, fecha de carga y
si requiere refresco.

### `company TICKER`
Nombre, precio y métricas principales de un ticker.

### `analyze TICKERS...`
Análisis completo (ratios, scoring, DCF) de uno o varios tickers.

### `buffett-analysis TICKERS... [--full]`
Evaluación estilo Buffett/Munger: filtro de 4 pilares (rentabilidad,
fortaleza financiera, generación de caja, estabilidad), moat (STRONG/
MODERATE/WEAK/NONE), score compuesto con rating (A–D), confianza de datos,
insights interpretables. `--full` muestra el desglose de cada métrica.

### `screener [--tickers T1,T2] [--search TEXTO] [--top N] [--no-prices]`
Busca empresas por criterios. Dos motores:

- **Mercado** (por defecto): `--per-max`, `--pb-min`, `--roe-min`, `--roic-min`,
  `--fcf-min`, `--debt-to-equity-max`, `--op-margin-min`, `--net-margin-min`,
  `--market-cap-min`...
- **Calidad Buffett** (con `--filter`): claves separadas por espacio
  `moat=STRONG min_score=80 min_margin_of_safety=0.15`, o comparaciones
  `--filter 'min_roic >= 0.15'`

Con `--no-prices` no se consultan precios: la columna de precio y las métricas
derivadas del precio (PER, P/B, EV/EBIT, FCF yield, market cap) se muestran
como N/A y los filtros basados en esas métricas no producen resultados.
Los filtros de valoración emitirán un aviso en ese modo. Los precios nunca se
persisten; se consultan en tiempo real vía PriceService (Yahoo Finance).

Resultados ordenados por el ranking calibrado: percentil intra-ticker de cada
componente (compuesto 55%, margen de seguridad 20%, momentum 10%, crecimiento
5%, estabilidad 5%, confianza 5%), mapeado a la banda 10-90, con tope de 60
para empresas con FCF negativo, deuda/equity ≥ 1.5 o cobertura de intereses
< 3×. Señales: BUY ≥ 75, WATCHLIST ≥ 60, AVOID si buffett < 40. Detalle en
`docs/scoring_methodology.md` y `docs/scoring_validation.md`.

### `opportunities [--tickers T1,T2] [--type TIPO]`
Detecta situaciones accionables sobre el universo cargado: 7 tipos
(UNDERVALUED_QUALITY, COMPOUNDERS, FUNDAMENTAL_ACCELERATION, INFLECTION_POINT,
QUALITY_WITH_TRIGGER, TURNAROUNDS, SPECIAL_SITUATIONS) con confianza y razones.

### `momentum [TICKERS...]`
Ranking por momentum fundamental (aceleración de ingresos, márgenes, ROIC y
FCF) con su trigger dominante.

### `anomalies [TICKERS...]`
Anomalías del último ejercicio vs el histórico: z-score (severidad
STRONG con |z| ≥ 3) y saltos interanuales (≥ 50%) en ingresos, beneficio y FCF.

### `portfolio <add|exit|remove|view|performance>`
Cartera persistente en `data/portfolio.json`.

```bash
# add: añade o promedia (misma cantidad → precio medio, mismo ticker)
main.py portfolio add AAPL 10 180 --thesis "moat fuerte" --signal BUY --date 2026-08-01
# exit: cierra vendiendo (registra PnL realizado)
main.py portfolio exit AAPL
# remove: borra sin registrar venta
main.py portfolio remove KO
# view: valor, retorno, score Buffett, moat, señal y oportunidad de cada posición
main.py portfolio view
# performance: PnL, retorno total, sobreconcentración, riesgo (HHI), sector
main.py portfolio performance
```

### `backtest [--strategy buffett|momentum] [--years N] [--top N] [--rebalance N] [--prices FILE] [TICKERS...]`
Reconstruye análisis históricos desde el repositorio y simula una cartera
igual-ponderada con rebalanceo cada N años. Métricas: CAGR, max drawdown,
Sharpe, win rate.

El momentum fundamental pesa `0.4*Δingresos + 0.3*Δmargen + 0.2*ΔROIC +
0.1*Δcrecimiento FCF`, normalizado cross-seccionalmente por snapshot.
Sin `--prices` los retornos son planos (mide solo la calidad de selección);
para retornos reales pasa un archivo con `TICKER,AÑO,PRECIO` por línea:

```
AAPL,2023,180
AAPL,2024,220
KO,2023,60
```

### `alerts [--state JSON] [TICKERS...]`
Motor de alertas sobre el universo:
- `BUY_SIGNAL` — la señal del screener es BUY con datos HIGH/MEDIUM
- `SELL_WARNING` — caída del score total ≥ 10 puntos (≥ 15 → HIGH) respecto a
  un estado anterior (`--state` con `{ticker: analysis}` en JSON)
- `TRIGGER_EVENT` — trigger dominante (expansión de margen, aceleración de
  ingresos, mejora de ROIC, salto de FCF...)

Salida `{ticker, alert_type, reason[], confidence}`, extensible a notificadores
reales (email/telegram/webhooks) implementando `backend/alerts/notifier.py`.

> **Nota:** `anomalies`, `momentum` y `alerts` reciben los tickers como
> argumentos posicionales (`anomalies AAPL MSFT KO`), **no** con la opción
> `--tickers` (que solo existe en `screener` y `opportunities`).

### `historical-valuation TICKERS...`
Muestra ratios históricos de valoración (P/E y FCF yield) para los tickers
indicados. Los **fundamentales** salen de Financial-DataBase (repositorio
principal); los **precios son en tiempo real** vía `PriceService` (yfinance) y
**nunca se persisten** en ninguna base de datos.

El cálculo se basa en:
- **Precio**: cierre del día de negociación más cercano al cierre del año fiscal
  (la fecha exacta del fin de año fiscal se obtiene de los fundamentales; si no
  está disponible se usa el 31 de diciembre del año)
- **EPS**: Beneficio neto / acciones en circulación
- **P/E ratio**: Precio / EPS
- **FCF yield**: Flujo de caja libre / Capitalización de mercado (el FCF se
  deriva de OCF − capex cuando el dato directo no existe)
- **Ajuste por splits**: los precios de Yahoo están ajustados por splits y las
  acciones reportadas no; `PriceService.get_split_adjustment` las alinea para
  que las métricas por acción sean consistentes a través del tiempo

Los precios se cachean en memoria (máx. 15 minutos, configurable con
`PRICE_CACHE_TTL`); cada ejecución nueva vuelve a Yahoo en tiempo real.

Si no hay datos de precios disponibles para un año, ese año se muestra con
"N/A" en lugar de fallar.

Ejemplo de salida para AAPL:

```
fiscal_year |    price |      eps |   pe_ratio |  fcf_yield
-----------------------------------------------------------
      2025 |   254.52 |     5.23 |      48.70 |      2.21%
      2024 |   225.90 |     4.76 |      47.44 |      2.28%
      2023 |   168.93 |     4.96 |      34.06 |      3.36%
```

### Refresco de datos SEC bajo demanda (`--refresh` / `--no-refresh` / `--freshness-hours`)

Los comandos de análisis (`analyze`, `analyze-full`, `buffett-analysis`,
`screener`, `momentum`, `opportunities`, `anomalies`, `alerts`,
`historical-valuation`) comprueban antes de analizar si los fundamentales de
**los tickers solicitados** están frescos en Financial-DataBase y, si no lo
están, lanzan una **sincronización SEC acotada por CIK** (`sec sync <CIK>`
por empresa) — nunca un sync masivo del universo completo.

- `--refresh`: fuerza la sincronización de todos los tickers analizados, sin
  importar la antigüedad.
- `--no-refresh`: desactiva el paso de sincronización (usa los datos que ya
  existen); los precios se siguen consultando.
- `--freshness-hours N`: antigüedad máxima para considerar los datos frescos
  (por defecto 168 h = 7 días, configurable en `config/refresh.yaml`).

Cuando el comando corre sobre el universo amplio sin tickers explícitos
(p. ej. `screener` o `momentum` sin argumentos), el refresh se omite por
defecto para no sincronizar cientos de empresas de golpe; se indica en la
salida y `--refresh` lo fuerza si se desea.

Degradación: si Financial-DataBase no está disponible, `SEC_USER_AGENT` no está
configurado, SEC no responde o el ticker no tiene CIK, el paso se reporta como
fallo/saltado con un mensaje claro y el análisis continúa con los datos
existentes. Los precios siempre se consultan en tiempo real vía `PriceService`
y **nunca se persisten**.

### `sql-analysis SCRIPT [--script SCRIPT] [--cik CIK] [--ciks CIKs] [--params JSON] [--limit N] [--list] [--output FORMAT]`
Ejecuta scripts SQL reutilizables desde el directorio `scripts/analysis` de
Financial-DataBase. Permite consultas predefinidas para overview de compañías,
ratios avanzados y otros análisis financieros.

- `SCRIPT` o `--script`: Nombre del script SQL (sin extensión .sql)
- `--cik`: CIK directo para usar como parámetro
- `--ciks`: Lista de CIKs separados por comas (para scripts multi-empresa
  como `compare`/`compare_companies`)
- `--params`: Parámetros adicionales en formato JSON
- `--limit`: Limita el número de filas devueltas (útil para scripts como financial_series)
- `--list`: Lista los scripts SQL disponibles
- `--output`: Formato de salida (table, json, csv; default: table)

Alias: `compare` → `compare_companies`.

Ejemplos:

```bash
# Overview de Apple vía CIK directo
pipenv run python main.py sql-analysis --script company_overview --cik 0000320193

# Series financieras de los últimos 5 años para Apple
pipenv run python main.py sql-analysis --script financial_series --cik 0000320193 --limit 5

# Ratios avanzados para Apple
pipenv run python main.py sql-analysis --script ratios_advanced --cik 0000320193

# Comparar múltiples empresas (Apple y Microsoft) con el alias shorthand
pipenv run python main.py sql-analysis compare --ciks 0000320193,0000789019
```

### `debug`
Verifica que todas las piezas del sistema funcionan (BD, repositorios, CLI).

## Interfaz Web (Streamlit)

```bash
./run_ui.sh
```

Abre http://localhost:8501: screener (~150 acciones), análisis detallado y
vista rápida por ticker.

## Comparación de fuentes de datos

El script `scripts/compare_sources.py` compara los **fundamentales** de
Financial-DataBase con los obtenidos directamente de Yahoo Finance y EDGAR para
validar calidad y consistencia. **Los precios nunca se comparan ni se piden**;
la comparación es exclusivamente de estados financieros.

- Comparación anclada en el **último año fiscal completo** de Financial-DataBase
  (aquel con datos anuales `period='FY'`), no en el año en curso a medio cerrar.
- Campos comparados (6): ingresos, beneficio neto, activos totales, pasivos
  totales, flujo de caja operativo y gastos de capital.
- Se destacan discrepancias **> 5%** entre fuentes.

Ejemplo de uso:

```bash
pipenv run python scripts/compare_sources.py AAPL MSFT KO
```

## Limitaciones conocidas

- **Precios en tiempo real (no persistidos)**: `historical-valuation`, el
  screener y cualquier métrica que requiera precio consultan Yahoo Finance en
  vivo (caché en memoria ≤ 15 min). Esto es intencional: los precios no se
  almacenan en Financial-DataBase. Depende por tanto de la disponibilidad y los
  límites de tasa de Yahoo/yfinance; si la red falla, las métricas dependientes
  de precio se muestran como "N/A" en lugar de fallar.
- **Ajuste por splits**: los precios ajustados de Yahoo se alinean con las
  acciones reportadas históricamente mediante `PriceService.get_split_adjustment`.
  Si Yahoo no devuelve el historial de splits, se usan las cifras tal como se
  reportaron (posible métricas por acción inexactas para años anteriores a un
  split).
- **Dependencia de Yahoo Finance y EDGAR**: El script de comparación depende de
  las bibliotecas `yfinance` y `edgar`, que pueden estar sujetas a límites de
  tasa o cambios en sus APIs. Si fallan, el script continuará con las fuentes
  disponibles.
- **Discrepancias entre fuentes**: Los datos de Financial-DataBase (SEC EDGAR
  procesado) pueden diferir de Yahoo/EDGAR vivo por ventanas temporales o
  conceptos (p. ej. total liabilities ausentes para ciertos tickers). El script
  las detecta y las reporta, pero no las corrige.
- **Scripts SQL**: Los scripts SQL reutilizables provienen de Financial-DataBase
  y pueden requerir ajustes futuros si el esquema de la base de datos cambia.
- **Precisión de los cálculos**: Se usa el cierre del día de negociación más
  cercano al cierre del año fiscal (ventana de ±15 días naturales) si no hay
  datos para ese día exacto.

## Universo de análisis

El universo maestro para el screener y el flujo diario es
`config/universe.csv`, generado por un pipeline de cuatro pasos que también
produce archivos por índice (`config/universe_sp500_nasdaq.csv`,
`config/universe_russell2000.csv`, `config/universe_european.csv`):

```bash
python scripts/fetch_universe.py            # 1) S&P 500 + Nasdaq-100 (Wikipedia)
python scripts/fetch_russell2000.py         # 2) Russell 2000 (holdings oficiales de IWM)
python scripts/fetch_european_indices.py    # 3) FTSE 100, DAX 40, CAC 40, IBEX 35,
                                            #    FTSE MIB, AEX, SMI, OMXS30, OMXC20/25
python scripts/build_universe.py            # 4) Merge + dedup -> config/universe.csv
python scripts/validate_universe_against_fdb.py   # 5) Gate de cobertura (>= 80%)
```

Solo se mantienen en el maestro las empresas con **CIK de SEC EDGAR**: los
fundamentales se derivan exclusivamente de los filings SEC, de modo que las
empresas europeas que no presentan ante la SEC (sin ADR/20-F/40-F) y las
acciones Russell sin CIK quedan fuera del maestro (pero visibles, marcadas, en
su archivo por índice). El flujo diario (`scripts/daily_workflow.py`) acepta
subconjuntos con `--universe sp500|nasdaq100|sp500,nasdaq100|russell2000|
european|all` o una ruta a un archivo, y limita el sync SEC acotado por CIK con
`--max-refresh N` (por defecto 200). Ver `docs/runbook_daily.md`.

## Testing y calidad

```bash
pipenv run pytest tests/unit -q     # suite unitaria (274 tests, sin red)
pipenv run black .
pipenv run flake8
```

## Estructura del proyecto

```
├── main.py                       # Entry point CLI
├── backend/
│   ├── app/cli.py                # Composición de servicios (build_*)
│   ├── domain/                   # Entidades, VOs, interfaces (sin pandas)
│   ├── providers/                # Yahoo + EDGAR, normalizadores
│   ├── repositories/             # SQL (PostgreSQL) y JSON
│   ├── services/                 # Pipeline de datos, análisis, precios en tiempo real
│   ├── analytics/                # Ratios, DCF, scoring, calidad
│   ├── intelligence/             # Buffett, moat, scoring, deltas, anomalías
│   ├── screener/                 # Filtros, ranking, señales, oportunidades
│   ├── portfolio/                # Modelos, repo JSON, performance, allocation
│   ├── backtesting/              # Estrategias, simulador, motor
│   └── alerts/                   # Triggers, motor de alertas, notificadores
├── cli/commands/                 # Un módulo por subcomando
├── alembic/                      # Migraciones de esquema
├── data/                         # portfolio.json, raw, cache
├── tests/unit/                   # 274 tests sin red (mocks)
├── ui/                           # Streamlit
└── docs/
```

Reglas de arquitectura: las capas de análisis nunca llaman a providers ni a la
red (consumen los outputs del pipeline); todo es determinista; el dominio no
depende de pandas.

## Licencia

Uso interno / educativo.