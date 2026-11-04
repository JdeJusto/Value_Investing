# Value Investing

<p align="center">
  <a href="https://github.com/JdeJusto/Value_Investing/releases"><img src="https://img.shields.io/github/v/release/JdeJusto/Value_Investing?style=for-the-badge&color=0B1B3A" alt="Última versión"></a>
  <a href="https://github.com/JdeJusto/Value_Investing/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/JdeJusto/Value_Investing/ci.yml?branch=main&style=for-the-badge&label=CI&color=10A77A" alt="Estado de CI"></a>
  <a href="tests/unit"><img src="https://img.shields.io/badge/tests-2522%20passed-10A77A?style=for-the-badge" alt="2.522 tests passed"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/JdeJusto/Value_Investing?style=for-the-badge&color=0B1B3A" alt="Licencia MIT"></a>
  <img src="https://img.shields.io/badge/python-3.13%2B-0B1B3A?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.13 o superior">
  <img src="https://img.shields.io/badge/streamlit-1.66.0-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" alt="Streamlit 1.66.0">
  <img src="https://img.shields.io/badge/database-PostgreSQL-336791?style=for-the-badge&logo=postgresql&logoColor=white" alt="Fuente de datos PostgreSQL">
  <img src="https://img.shields.io/badge/code%20style-Ruff-261230?style=for-the-badge" alt="Comprobación y formato con Ruff">
</p>

<p align="center"><a href="README.md">English</a> · <a href="README.es.md">Español</a></p>

Análisis fundamental en la terminal para empresas cotizadas. Scorecards, un
screener, ocho metodologías de inversión independientes (Graham, Graham & Dodd,
Lynch, Buffett-Classic, Buffett-Clark, Fisher, Greenblatt, Marks), consenso y
DCF — tanto en CLI como en Streamlit. Los fundamentales se normalizan desde SEC
EDGAR en una base PostgreSQL local (Financial-DataBase).

## Instalación

Requiere Python 3.13 y una base PostgreSQL poblada por
[Financial-DataBase](https://github.com/JdeJusto/Financial-DataBase).

```bash
git clone https://github.com/JdeJusto/Value_Investing
cd Value_Investing
python -m pip install pipenv
PIPENV_VENV_IN_PROJECT=1 pipenv install --dev
pipenv shell
```

Los comandos siguientes se ejecutan desde la raíz del repositorio; `./vi` usa
el virtualenv del proyecto.

## CLI

```bash
./vi scorecard AAPL                           # Scorecard completa con veredictos
./vi financials AAPL                          # Balance (activos | pasivo+patrimonio)
./vi financials AAPL --json                   # Salida JSON estructurada
./vi rank --by graham --top 20                # Mejores tickers por metodología
./vi rank --combine graham,lynch --strategy and  # Intersección
./vi compare-methodologies AAPL                # Ocho metodologías de un vistazo
./vi dcf AAPL                                 # Resumen del DCF
./vi consensus AAPL --universe all             # Consenso canónico (las 8)
./vi portfolio view                           # Cartera actual
./vi screener --tickers AAPL,MSFT --no-prices --no-refresh  # Screener
```

`./vi --help` lista los 42 comandos. Todos admiten `--no-color`;
`vi financials` y `vi rank` también admiten `--json`.

## Streamlit

![Interfaz Streamlit — scorecard](assets/ui_v2_analysis_scorecard.png)

```bash
./run_ui.sh

# O con datos de demo (sin FDB):
VI_DEMO=1 ./run_ui.sh
```

Abre en <http://localhost:8501>. Páginas registradas: Inicio, Análisis (resumen,
estados financieros, metodologías, DCF, filings), Screener, Cartera, Informes y
Consenso. El ranking por metodología está disponible en CLI con `vi rank`.

## Flujo diario

```bash
python scripts/daily_workflow.py
```

Sincroniza filings de la SEC y precios de Yahoo en FDB, evalúa alertas y genera
el informe diario. Admite `--resume` y health checks antes de cada etapa.
Códigos de salida: `0` éxito, `1` parcial, `2` no se pudo ejecutar. Véase
[`docs/runbook_daily.md`](docs/runbook_daily.md) para fallos y recuperación.

## Datos (FDB)

Requiere [Financial-DataBase](https://github.com/JdeJusto/Financial-DataBase)
en `~/Financial-DataBase` y una base PostgreSQL local con facts financieros,
precios y metadatos de compañías.

## Contribuir

Issues y PRs son bienvenidos.

```bash
pytest tests/unit tests/api             # tests
ruff check . && ruff format --check .   # lint
```

Véase [`docs/`](docs/) para notas de diseño y
[`docs/backlog.md`](docs/backlog.md) para problemas conocidos.

## Licencia

MIT — véase [`LICENSE`](LICENSE).
