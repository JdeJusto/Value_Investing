# Contributing to Value Investing

Thanks for considering a contribution. This project is a terminal-first
fundamental-analysis platform over SEC filings.

## Getting set up

Requires Python 3.13+ and (for the data path) PostgreSQL 14+ with the
Financial-DataBase schema loaded.

```bash
git clone <your-fork-url>
cd Value_Investing
python -m pip install pipenv
pipenv install --dev
cp .env.example .env              # then edit .env — see below
```

`.env` is git-ignored and must stay that way. The only values you need for a
local run:

| Variable | Purpose |
| --- | --- |
| `FINANCIAL_DATABASE_URL` | PostgreSQL connection to the Financial-DataBase instance |
| `SEC_USER_AGENT` | Contact string the SEC requires, e.g. `YourTool/1.0 you@your-domain.com` |
| `SEC_EMAIL` | Only needed for the live EDGAR provider; without it that fallback is disabled with a warning |

Never commit `.env`, database credentials, or private/third-party contact data.
The maintainer contact in `SECURITY.md` is intentionally public. The SEC
requires a contact in `SEC_USER_AGENT`; the Yahoo preflight refuses
browser-like User-Agents (see `docs/price_recovery_2026-09-28.md`).

## Running the tests

```bash
python -m pytest tests/unit -q
```

The unit suite is hermetic and needs no database. Tests that require a live
Financial-DataBase instance are isolated under `tests/integration/`; run them
only when `FINANCIAL_DATABASE_URL` points at a test database containing the
required company data.

```bash
python -m pytest tests/integration -q
```

## Using the CLI

```bash
python main.py analyze AAPL                 # single company
python main.py screener --search "quality"  # cross-sectional screen
python -m scripts.daily_workflow --universe sp500 --limit 50
```

Module invocation is required for the scripts (`python -m scripts.…`);
running `scripts/daily_workflow.py` directly fails because `backend` is not
on `sys.path`. `docs/runbook_daily.md` is the operational guide.

## Updating dependencies

This project uses Pipenv, so `Pipfile` is the source of truth and
`Pipfile.lock` must stay in sync with it. Dependabot covers `npm`
(`frontend/`) and `github-actions` only: its Pipenv resolver rejects the
`python_version` range in `[requires]` and then fails every package, so a `pip`
ecosystem entry would only produce red weekly runs. Update Python packages
explicitly instead:

```bash
pipenv update <package> --lock-only   # rewrites only that entry in Pipfile.lock
pipenv verify                         # confirms the lock matches the Pipfile
```

`--lock-only` matters: a bare `pipenv lock` re-resolves everything and buries
your change in an unrelated diff. Adding a brand-new dependency does need
`pipenv lock`, so review the resulting diff carefully.

## Code style

- PEP 8, type hints on public signatures, docstrings on public APIs.
- No randomness or network in the domain layer; providers and repositories
  stay behind their interfaces.
- One concern per commit; messages in the imperative mood
  (`feat(analysis): …`, `fix(yahoo): …`).
- Keep prices out of every persistent store. This is a hard project rule, not
  a style preference: the Financial-DataBase `prices` table must stay
  untouched by this project.

## Pull requests

1. Fork, branch from `main`.
2. Make the change; add tests for new behaviour.
3. `python -m pytest tests/unit -q` must be green.
4. Open the PR describing what changed and why, and reference the issue.

## Releasing

Use `./scripts/release.sh <patch|minor|major> "<message>"` from a clean `main`
branch with the tests passing. The script:

1. Bumps the version (single source of truth: `backend/__init__.py`).
2. Updates `CHANGELOG.md` (Keep a Changelog) and the version badges.
3. Commits, creates the annotated tag `vX.Y.Z` and pushes.
4. Creates the GitHub release (`gh release create`).

It refuses to continue if the working tree is dirty, `main` is not in sync with
`origin/main`, the unit tests fail or `ruff` reports problems — a release is
never tagged with failing tests. Use `--dry-run` to prepare the changes without
committing, tagging or pushing.

Versioning rules:

- **patch** (`0.1.X`): bug fixes, docs, small polish.
- **minor** (`0.X.0`): new methodologies, features, non-breaking behaviour changes.
- **major** (`X.0.0`): breaking changes.

The package version must match the top `CHANGELOG.md` entry; that consistency
(plus the changelog format and the README badges) is enforced by
`tests/unit/test_release_consistency.py` in the regular suite.

## Reporting bugs

Open an issue with the `.github/ISSUE_TEMPLATE/bug_report.md` template:
command, expected vs actual, and the relevant part of
`data/logs/daily_workflow.log` (never attach a `.env`).
