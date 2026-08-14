# Value Investing

Plataforma de análisis fundamental en terminal: carga de datos financieros desde
múltiples fuentes (Yahoo Finance y EDGAR/SEC), evaluación de calidad empresarial
estilo Buffett, detección de oportunidades, seguimiento de cartera, backtesting
y alertas. Todo determinista, sin ML y sin dependencias de redes sociales.

## Características

- **Datos**: pipeline multi-fuente (Yahoo + EDGAR) con fallback automático,
  calidad por año, frescura y refresco bajo demanda
- **Inteligencia**: filtro Buffett (4 pilares), análisis de moat, métricas de
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

### `screener [--tickers T1,T2] [--search TEXTO] [--top N]`
Busca empresas por criterios. Dos motores:

- **Mercado** (por defecto): `--per-max`, `--pb-min`, `--roe-min`, `--roic-min`,
  `--fcf-min`, `--debt-to-equity-max`, `--op-margin-min`, `--net-margin-min`,
  `--market-cap-min`...
- **Calidad Buffett** (con `--filter`): claves separadas por espacio
  `moat=STRONG min_score=80 min_margin_of_safety=0.15`, o comparaciones
  `--filter 'min_roic >= 0.15'`

Resultados ordenados por ranking (compuesto 55%, margen de seguridad 20%,
momentum 10%, crecimiento 5%, estabilidad 5%, confianza 5%).

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

### `debug`
Verifica que todas las piezas del sistema funcionan (BD, repositorios, CLI).

## Interfaz Web (Streamlit)

```bash
./run_ui.sh
```

Abre http://localhost:8501: screener (~150 acciones), análisis detallado y
vista rápida por ticker.

## Testing y calidad

```bash
pipenv run pytest tests/unit -q     # suite unitaria (194 tests, sin red)
pipenv run black .                  # formato
pipenv run flake8                   # lint
```

## Estructura del proyecto

```
├── main.py                       # Entry point CLI
├── backend/
│   ├── app/cli.py                # Composición de servicios (build_*)
│   ├── domain/                   # Entidades, VOs, interfaces (sin pandas)
│   ├── providers/                # Yahoo + EDGAR, normalizadores
│   ├── repositories/             # SQL (PostgreSQL) y JSON
│   ├── services/                 # Pipeline de datos, análisis
│   ├── analytics/                # Ratios, DCF, scoring, calidad
│   ├── intelligence/             # Buffett, moat, scoring, deltas, anomalías
│   ├── screener/                 # Filtros, ranking, señales, oportunidades
│   ├── portfolio/                # Modelos, repo JSON, performance, allocation
│   ├── backtesting/              # Estrategias, simulador, motor
│   └── alerts/                   # Triggers, motor de alertas, notificadores
├── cli/commands/                 # Un módulo por subcomando
├── alembic/                      # Migraciones de esquema
├── data/                         # portfolio.json, raw, cache
├── tests/unit/                   # 194 tests sin red (mocks)
├── ui/                           # Streamlit
└── docs/
```

Reglas de arquitectura: las capas de análisis nunca llaman a providers ni a la
red (consumen los outputs del pipeline); todo es determinista; el dominio no
depende de pandas.

## Licencia

Uso interno / educativo.
