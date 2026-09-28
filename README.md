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
./vi debug
./vi load-data AAPL
./vi analyze AAPL
./vi screener --tickers AAPL,MSFT
./run_ui.sh                 # Streamlit UI at http://localhost:8501
```

`./vi` runs the project's virtual environment without requiring `pipenv run`. The complete environment-variable list is in [`.env.example`](.env.example). `FINANCIAL_DATABASE_URL` is optional; without a reachable Financial-DataBase instance, the application can use its local JSON repository and configured live providers.

The optional Docker Compose stack includes PostgreSQL, Redis, the FastAPI service, Celery workers, and the React frontend. It is for local development, not a production deployment; configure secrets, database migrations, and network access before exposing any service.

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
