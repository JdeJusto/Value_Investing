# Security posture

Last full sweep: 2026-11-18 (v0.34.8). The mobile app, REST API and web
frontend were retired in v0.36.0; only the Python package remains.

## Dependabot

| Repo | Open | High | Med | Low | Notes |
|---|---:|---:|---:|---:|---|
| Value_Investing (Pipfile.lock) | 0 | 0 | 0 | 0 | `dnspython`/`opentelemetry-api` fixed; pins guarded |
| Financial-DataBase | 0 | 0 | 0 | 0 | `pip-audit`/Dependabot clean |

## Code Scanning (CodeQL)

| Repo | Open | Notes |
|---|---:|---|
| Value_Investing | 0 | path-injection in the price cache fixed in v0.32.1 (SHA-256 cache keys) |
| Financial-DataBase | 0 | — |

## Secret Scanning

| Repo | Open |
|---|---:|
| Value_Investing | 0 |
| Financial-DataBase | 0 |

The FMP and Tiingo keys are read from `.env` (gitignored) and are never
written to tracked files, tests, docs or logs. Provider exceptions are
redacted before logging (`***`). `.env.example` contains placeholders only.

## Historical fixes

- 2026-11-11: path-injection in the price cache (v0.32.1). SHA-256 cache
  keys; CodeQL 4 high → 0.
- 2026-11-13: soupsieve 4.0.0 (high, DoS); parser tests green with
  BeautifulSoup 4.15.0.
- 2026-11-18: dnspython 2.9.2 (high, GHSA-vvf4-9x63-8xvv) and
  opentelemetry-api 1.45.2 (moderate, CVE-2026-126360) from Dependabot
  #85/#84; transitive lock-only update.

## How to re-run the sweep

```bash
gh api "repos/JdeJusto/Value_Investing/dependabot/alerts?state=open" \
  --paginate --jq '[.[] | {severity: .security_advisory.severity, package: .dependency.package.name}]'
gh api "repos/JdeJusto/Value_Investing/code-scanning/alerts?state=open" --paginate
gh api "repos/JdeJusto/Value_Investing/secret-scanning/alerts?state=open" --paginate
.venv/bin/pipenv verify
```
