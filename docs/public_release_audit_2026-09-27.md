# Public release readiness audit — 2026-09-27

Audit of **Value_Investing** before making the repository public. Read-only:
nothing was modified while producing it. Tooling note: `gitleaks` and
`trufflehog` are not installed on this machine, so the scan is pattern-based
(§1 lists the exact patterns).

## 1. Secrets

### 1.1 History (`git log -p --all`)

| Pattern | Hits | Verdict |
| --- | ---: | --- |
| `<SEC_CONTACT_EMAIL>` (the personal address) | 71 | **Real exposure if published** |
| `@gmail\.com` | 71 | same occurrences (the address is referenced here as `<SEC_CONTACT_EMAIL>`, never literally) |
| private-key headers (RSA / OpenSSH / PGP) | 0 | clean |
| `api[_-]?key` | 0 | clean |
| `password` | 47 | **all false positives**: `password_hash` column, `bcrypt.gensalt()`, `type="password"` inputs, `plain_password.encode()` — no credential |

Introduced in `3b4ec1e` (2026-04-26) as a `os.getenv` default in
`backend/config/settings.py`, `backend/app/cli.py`, `backend/core/config.py`,
a literal in `scripts/compare_sources.py`, an `export` in
`scripts/run_daily_background.sh` and two documentation lines. Removed from
HEAD by `bbb2801` and `5137135`.

### 1.2 HEAD

| Finding | Verdict |
| --- | --- |
| `.env.example:22 SECRET_KEY="change-me-in-production-use-a-strong-random-key"` | placeholder, safe |
| `.env.example:23-24 ACCESS_TOKEN_EXPIRE_MINUTES / REFRESH_TOKEN_EXPIRE_DAYS` | config, safe |
| `backend/api/deps.py` OAuth2 bearer + `decode_token` | code, safe |
| `Pipfile.lock` `pytokens` | dependency, safe |

**No live secret in HEAD.** No `.env` file was ever tracked (only
`.env.example`).

## 2. Personal information

**HEAD — 12 files contain the absolute path `~`:**

| File | Lines |
| --- | --- |
| `AGENTS.md` | 81, 347, 404, 405, 406 |
| `backend/services/refresh_service.py` | 55, 56 (comments) |
| `deploy/systemd/value-investing-daily.service` | 23, plus `WorkingDirectory`/`ExecStart` |
| `docs/scheduled_run_verification_2026-09-28.md` | (verification log) |
| `docs/price_recovery_2026-09-28.md` | (verification log) |
| `docs/runbook_daily.md`, `docs/catch_up_stale*` etc. | operational examples |

Reveals the local username, the sibling checkout path and the home
directory layout. Not a secret, but it is machine-specific noise for a public
audience.

**Personal e-mail addresses in HEAD: 0** (this document refers to the address
only as `<SEC_CONTACT_EMAIL>`). No macOS or Windows user paths either.
**No internal hostnames or IPs.**

**History:** the e-mail above (71 lines) plus `name="Jaime"` in the old
`EdgarProvider` default and a `SEC_NAME` default.

## 3. Commit authors

```
jdejusto@users.noreply.github.com   <- preferred (recent commits)
<SEC_CONTACT_EMAIL>                <- personal; public the moment the repo is
jdejusto@example.com                <- placeholder, harmless
jdejusto@localhost                  <- local placeholder, harmless
```

**Recommendation:** for a public repository, prefer
`jdejusto@users.noreply.github.com` and set it as the account-wide default
(`git config --global user.email`). Note that the personal Gmail address is
**already the account identity on GitHub**, so publishing the history adds
little marginal exposure — the decisive input for the rewrite decision in
`docs/history_rewrite_recommendation.md`.

## 4. .gitignore

Tracked files that arguably should be ignored:

| Path | Assessment |
| --- | --- |
| `data/cache/.gitkeep`, `data/raw/.gitkeep`, `data/logs/.gitkeep` | intentional (directory placeholders) — keep |
| `data/reports/report_european_2026-09-23.md` | one-off report committed on purpose before the daily-artifact rule existed; harmless, but a reader may wonder why one report is tracked. Consider untracking. |

Effective rules verified with `git check-ignore`: `.env`, `data/raw/*`,
`data/cache/analysis/`, `data/cache/alerts/`, `data/reports/daily_*.md`,
`data/reports/daily_state.json`, `data/reports/daily_run_state*.json`,
`data/state/`, `data/alerts/`, `data/logs/*`, `__pycache__/`, `.venv/`.

**No gaps that can leak runtime data.** The one inconsistency is the single
tracked report above.

## 5. Dependencies

- `Pipfile` / `Pipfile.lock` / `setup.cfg`: no `git+`, no `file://`, no
  personal index. Clean.
- No hardcoded connection string with a real password. The database URL
  default is `postgresql://financial:test@localhost:5432/financial_database`
  — a local development default, overridable by `FINANCIAL_DATABASE_URL`.
  The `test` password is a placeholder.
- Tests: 2 of the unit-test files reference `FINANCIAL_DATABASE_URL` and skip
  when it is absent, so the suite is runnable without a database.
- Python version is **not declared** in a `pyproject.toml` (the project uses
  `Pipfile` + `setup.cfg`). Publishing without a declared floor is a
  documentation gap (§6).

## 6. Documentation

| Item | Status |
| --- | --- |
| `README.md` | present, **no absolute paths** (0 matches) |
| `.env.example` | present, placeholder values only |
| `LICENSE` | **MISSING** |
| `CONTRIBUTING.md` | **MISSING** |
| `CODE_OF_CONDUCT.md` | **MISSING** |
| `SECURITY.md` | **MISSING** |
| `CHANGELOG.md` | missing (optional) |
| `AGENTS.md` | present (agent guidance; unusual in a public repo but harmless) |
| `docs/` | 30+ documents: runbooks, methodology, audits, investigations. Strong. |

## 7. GitHub configuration

| Item | Status |
| --- | --- |
| `.github/workflows/` | **MISSING** — no CI at all |
| `.github/dependabot.yml` | **MISSING** |
| `.github/ISSUE_TEMPLATE/` | **MISSING** |
| `.github/pull_request_template.md` | **MISSING** |
| `.github/` | does not exist |

(Financial-DataBase already has `dependabot.yml` and a PR template; Value
Investing has none.)

## 8. Recommendations, by priority

**Must do before publishing**

1. **Decide the history question** — the personal e-mail is in 71 lines of
   history. See `docs/history_rewrite_recommendation.md`; my recommendation
   is Option B (accept), because the address is already the GitHub account
   identity and the rewrite would rewrite five months of hashes.
2. **Add a LICENSE** (MIT) — without it the default is "all rights
   reserved", which contradicts a public repository.
3. **Add `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`** — expected
   by contributors and by `github.com`'s community standards.
4. **Add a minimal CI workflow** so a public fork has a green/red signal.

**Should do**

5. **Reduce the absolute paths in `AGENTS.md`** (5 lines) and the comments in
   `backend/services/refresh_service.py` (2) to `$HOME`-style or relative
   forms. Low value individually, but they are the only machine-identifying
   content in HEAD.
6. **Declare the Python version floor** (the interpreter used is 3.13+; FDB
   declares `>=3.13`).
7. **Untrack `data/reports/report_european_2026-09-23.md`** or document why
   it is tracked.
8. **Add issue and PR templates.**

**Optional**

9. Topics and a description on the repository page.
10. A short architecture diagram in the README (the project has `docs/`
    with the material already).
11. A `CHANGELOG.md` once releases start being tagged.
