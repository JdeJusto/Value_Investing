# Value Investing

[English](README.md) · [Español](README.es.md)

[![Version](https://img.shields.io/badge/version-0.4.1-blue)](CHANGELOG.md)
[![Tests](https://img.shields.io/badge/tests-1324%20passed-green)]()

A deterministic, explainable toolkit for fundamental stock analysis. It combines financial statements, transparent valuation and quality measures, screening, portfolio tracking, and backtesting through a command-line interface and web applications.

> **Design principle:** “Fools admire complexity; geniuses admire simplicity.” Prefer clear rules, small components, and traceable data over complexity that does not add value.

## What's in 0.1.0

First public release: seven book-derived methodologies (Graham, Graham & Dodd, Buffett/Clark, Buffett Classic, Fisher, Lynch GARP and Greenblatt Magic Formula), DCF valuation with four variants, SEC-derived fundamentals through the companion Financial-DataBase, a five-page Streamlit UI, screener, portfolio tracking, daily workflow and alerts. Prices are fetched on demand and never persisted. See [CHANGELOG.md](CHANGELOG.md) for the full list and the known limitations.

## Why this project

Most fundamental-analysis tools give you **one** answer: a single score, a
single rating, a single recommendation. This project does the opposite: it
runs **8 book methodologies in parallel** and shows you where they agree and
where they disagree — because disagreement is information, not a bug.

- **8 book methodologies, side by side.** Graham, Graham & Dodd, Buffett
  (×2), Fisher (quantitative subset), Lynch, Greenblatt and Marks. Each one
  evaluates the same company independently.
- **DCF as an explicit outsider.** Valuations that come from a
  discounted-cash-flow model are labeled `not-from-canon` and never merged
  into the book methodology scores.
- **Disagreement summary.** When Graham says AVOID and Buffett says BUY, the
  system tells you *why* — different frameworks, not different data.
- **Financial guards.** Banks and insurers are excluded from methodologies
  that do not apply to them, instead of producing misleading numbers.
- **Data engine built in.** Financial-DataBase ingests 76M+ SEC facts across
  8,000 companies with full provenance and idempotency.
- **Prices are never persisted.** Every price is fetched in real time and
  cached in memory, so the numbers you see are the numbers the market has
  right now.

### How it compares

| Feature | This project | Simply Wall St | Finviz | Morningstar |
|---|:---:|:---:|:---:|:---:|
| Multiple methodologies, side by side | ✅ 8 | ❌ | ❌ | ❌ |
| Explicit disagreement summary | ✅ | ❌ | ❌ | ❌ |
| Financial guards by methodology | ✅ | ❌ | ❌ | ❌ |
| Book-derived rules (documented) | ✅ | ⚠️ | ❌ | ⚠️ |
| Open source | ✅ | ❌ | ❌ | ❌ |
| Self-hostable, no accounts | ✅ | ❌ | ❌ | ❌ |
| Prices never persisted | ✅ | — | — | — |
| DCF explicitly labeled not-from-canon | ✅ | ❌ | ❌ | ❌ |

*Honest footnote:* the table is about the workflow this project optimises
for. Commercial tools beat it in other dimensions (universe breadth, news,
broker integration, mobile apps) — and Fisher here is a **quantitative
subset** (4 of 15 points), because scuttlebutt cannot be automated.

## Try it in 30 seconds (no database required)

![analyze-full](assets/analyze-full.gif)

![compare-methodologies](assets/compare-methodologies.gif)

```bash
git clone https://github.com/JdeJusto/Value_Investing.git
cd Value_Investing
uv sync            # or: pipenv install --dev

python main.py analyze-full AAPL --demo
python main.py compare-methodologies AAPL --demo

VI_DEMO=1 ./run_ui.sh   # http://localhost:8501
```

Demo mode uses a **pinned offline bundle** for 8 tickers (AAPL, MSFT, KO, JNJ,
JPM, XOM, PLD, TSLA): no PostgreSQL, no SEC, no Yahoo. Every command accepts
`--demo`, `screener --universe demo` screens the bundle, and the UI shows a
demo banner with the price refresh disabled. The fixtures are real-ish 10-K
figures pinned to a date — regenerate them with
`python -m scripts.build_demo_data`. To use the real system, see
[Installation](#installation).

## UI

| Home | Analysis |
|------|----------|
| ![Home](assets/ui_home.png) | ![Analysis](assets/ui_analysis.png) |

| Screener | Portfolio |
|----------|-----------|
| ![Screener](assets/ui_screener.png) | ![Portfolio](assets/ui_portfolio.png) |

| Reports |
|---------|
| ![Reports](assets/ui_reports.png) |

Captured from the five-page Streamlit app running in demo mode
(`VI_DEMO=1 ./run_ui.sh`).

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

## Data conventions

- **Net income**: when a company reports both a consolidated net income and
  a net income available to common stockholders (usually because it has
  preferred stock), the platform uses the **available to common** figure —
  it is the right basis for per-share metrics (EPS, P/E, DDM) and keeps
  preferred dividends from inflating returns. The CLI marks the figure as
  "available to common" so it is not mistaken for the consolidated number
  found on EDGAR (JPM FY2025: 55.7B available to common vs 57.0B
  consolidated — see `docs/coherence_audit_2026-09-30.md`).

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
| `FINANCIAL_DATABASE_URL` | Financial-DataBase PostgreSQL URL (default `postgresql://financial:test@localhost:5432/financial_database` — a **local development default**, not a secret; change it for anything beyond localhost). Optional: without a reachable FDB the app falls back to the local JSON repository and live providers. |
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

## Releasing

Releases follow [Semantic Versioning](https://semver.org/). See [CONTRIBUTING.md](CONTRIBUTING.md#releasing) for the process.

## License

[MIT](LICENSE). The license applies to this project's code, not to data supplied by external providers.
