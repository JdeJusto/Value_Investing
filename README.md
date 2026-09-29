# Value Investing

[English](README.md) · [Español](README.es.md)

A deterministic, explainable toolkit for fundamental stock analysis. It combines financial statements, transparent valuation and quality measures, screening, portfolio tracking, and backtesting through a command-line interface and web applications.

> **Design principle:** “Fools admire complexity; geniuses admire simplicity.” Prefer clear rules, small components, and traceable data over complexity that does not add value.

## What it does

- Loads and normalizes company fundamentals from SEC filings, Yahoo Finance, or the companion Financial-DataBase.
- Calculates financial ratios, DCF valuations, company-quality and moat assessments, and explainable scores.
- Screens companies, ranks opportunities, and generates fundamental alerts.
- Tracks portfolios and runs deterministic, historical backtests.
- Provides a CLI, a Streamlit analysis UI, and a FastAPI + React web application.

This is an analysis tool, **not investment advice**. Results depend on the quality and availability of upstream data.

## Data sources and external services

| Source | How it is used |
| --- | --- |
| [SEC EDGAR](https://www.sec.gov/edgar) | Filings, XBRL company facts, and company/CIK identifiers. The direct provider uses `edgartools`; the companion Financial-DataBase can also refresh SEC data. SEC requests require a descriptive `SEC_USER_AGENT` with valid contact details. |
| [Yahoo Finance](https://finance.yahoo.com/) via [`yfinance`](https://github.com/ranaroussi/yfinance) | Market data, on-demand prices, and an alternate source for financial statements. Prices are cached in memory and **are not persisted** by this project. Availability and rate limits are controlled by Yahoo. |
| [Wikipedia](https://www.wikipedia.org/) | Constituent lists used when rebuilding the S&P 500, Nasdaq-100, and selected European index universes. |
| [iShares](https://www.ishares.com/) | Russell 2000 constituents from the official IWM ETF holdings file. |
| [Financial-DataBase](https://github.com/JdeJusto/Financial-DataBase) | Optional companion PostgreSQL database for SEC-derived fundamentals and targeted SEC refreshes; configured with `FINANCIAL_DATABASE_URL`. It is a separate project. |

Provider data and trademarks are not covered by this repository's MIT license. Follow each provider's terms, access policies, and attribution requirements. Data may be delayed, incomplete, or unavailable.

The Python integrations use `edgartools`, `yfinance`, and SQLAlchemy. The
interfaces include Streamlit and FastAPI + React; the optional Compose stack
also uses Redis and Celery. `Pipfile` and `Pipfile.lock` are the authoritative
Python dependency list.

## Quick start

Requirements: Python 3.13+ (the CI-tested version) and Pipenv. PostgreSQL and Docker Compose are optional for the CLI; Node.js 22+ is needed only to develop the React frontend.

```bash
git clone https://github.com/JdeJusto/Value_Investing.git
cd Value_Investing
python -m pip install pipenv
pipenv install --dev
cp .env.example .env
```

Edit `.env` before making SEC requests. Replace the example `SEC_USER_AGENT` with a descriptive application name and a real contact address. Set `SEC_EMAIL` and `SEC_NAME` for the direct `edgartools` provider. Never commit `.env` or real credentials.

```bash
# With pipenv (creates .venv automatically)
pipenv install --dev
pipenv shell                # or prefix every command with: pipenv run
# Without pipenv: use the checked-in venv wrapper
source .venv/bin/activate   # python3.13+ venv
```

```bash
./vi debug
./vi load-data AAPL
./vi analyze AAPL
./vi screener --tickers AAPL,MSFT
./run_ui.sh                 # Streamlit UI (5 pages) at http://localhost:8501
```

`./vi` runs the project's virtual environment without requiring `pipenv run` (equivalent to `.venv/bin/python main.py ...`). The complete environment-variable list is in [`.env.example`](.env.example). The variables that matter day to day:

| Variable | Purpose |
| --- | --- |
| `SEC_USER_AGENT` | Required for SEC requests (app name + real contact, e.g. `MyApp/1.0 me@example.com`). |
| `SEC_EMAIL` / `SEC_NAME` | Contact for the direct `edgartools` provider. |
| `FINANCIAL_DATABASE_URL` | Financial-DataBase PostgreSQL URL (default `postgresql://financial:test@localhost:5432/financial_database`). Optional: without a reachable FDB the app falls back to the local JSON repository and live providers. |
| `DATA_RAW_DIR` | Raw SEC download directory used by the FDB sync subprocess. |
| `PORTFOLIO_PATH` | Portfolio JSON (default `data/portfolio.json`). |

### Analysis commands

```bash
./vi analyze-graham AAPL
./vi analyze-buffett-classic AAPL
./vi analyze-buffett-clark AAPL
./vi analyze-graham-dodd AAPL
./vi analyze-fisher-quant AAPL
./vi analyze-lynch-garp AAPL
./vi compare-methodologies AAPL     # all methodologies side by side
./vi dcf AAPL                       # not-from-canon DCF (REIT/DDM/hyper-growth variants)
./vi analyze-full AAPL              # consolidated 6-section report
```

### Streamlit UI (5 pages)

```bash
./run_ui.sh                 # Home · Analysis · Screener · Portfolio · Reports
```

Do **not** run `python -m ui.app`: the app is launched with Streamlit (`streamlit run ui/app.py`, which `run_ui.sh` wraps). Pages are `ui/pages/01_home.py` … `05_reports.py`; data loading is cached in memory and prices are never persisted (the only price write is the explicit "Save prices to portfolio" button).

### Portfolio

```bash
./vi portfolio view
./vi portfolio performance
./vi portfolio add AAPL 10 180.00 --thesis "moat"
./vi portfolio exit AAPL 340.00
./vi portfolio remove AAPL
```

### Daily workflow

```bash
source .venv/bin/activate
python -m scripts.daily_workflow                    # full run (writes data/reports/daily_*.md)
python -m scripts.daily_workflow --dry-run --limit 5 --top 3   # safe smoke run
```

The daily report feeds the Home page (top opportunities + alerts).

The optional Docker Compose stack includes PostgreSQL, Redis, the FastAPI service, Celery workers, and the React frontend. It is for local development, not a production deployment; configure secrets, database migrations, and network access before exposing any service.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `ModuleNotFoundError: No module named 'dotenv'` | You are running with the system Python. Activate the venv (`source .venv/bin/activate`) or use `./vi` / `pipenv run`. `python-dotenv` is already installed and declared in `Pipfile`/`Pipfile.lock`; the daily workflow also degrades gracefully without it. |
| `Connection refused` to PostgreSQL | Check the service and the URL in `.env` (`FINANCIAL_DATABASE_URL` for Financial-DataBase, `DATABASE_URL` for the local store). The CLI falls back to JSON storage when the database is unreachable. |
| `pyarrow.lib.ArrowInvalid` in the UI | Fixed by the dataframe normalizer (`ui/_shared.normalize_rows`); update `main` and reload the page. |
| Yahoo throttling (HTTP 429, prices N/A) | Wait and retry. Prices are cached in memory only (15 min) and degrade to "—"; nothing is fabricated or persisted. |
| Streamlit on a busy port | `./run_ui.sh` uses 8501; run `streamlit run ui/app.py --server.port N` for another port. |

## Tests

```bash
pipenv run python -m pytest tests/unit -q
```

The unit suite does not require live market data or a database. Tests that need Financial-DataBase skip when it is not configured.

## Project layout

```text
backend/      domain, providers, repositories, analytics, services, and API
cli/          command-line commands
ui/           Streamlit analysis interface
frontend/     React + TypeScript client for the FastAPI service
scripts/      daily workflow, universe builders, validation, and dev utilities
config/       universe and runtime configuration
tests/        automated tests
data/         local repository data, cache, and reports
```

## Documentation

- [Daily workflow](docs/runbook_daily.md)
- [Scoring methodology](docs/scoring_methodology.md) and [validation](docs/scoring_validation.md)
- [Cross-source validation methodology](docs/validation_methodology.md)
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Code of Conduct](CODE_OF_CONDUCT.md)

## License

[MIT](LICENSE). The license applies to this project's code, not to data supplied by external providers.
