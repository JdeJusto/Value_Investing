# Pull request

<!-- One-line summary of the change. -->

## What changed

<!--
What the PR does, and why. If it changes a score, a signal, an alert
threshold or a report, say so explicitly: that affects every user of the
daily report.
-->

## Checklist

- [ ] `python -m pytest tests/unit -q` is green (or FDB: `python -m pytest tests/unit -q`)
- [ ] Tests added or updated for the new behaviour
- [ ] **No secrets**: no `.env`, no connection string with a password, no API
      key, no personal e-mail (use `<your-e-mail>` in docs)
- [ ] No personal absolute paths (`/home/<user>/…`) in code, docs or unit files
- [ ] Docs updated (`docs/`, README, runbook) where behaviour or setup changed
- [ ] Commit messages in the imperative mood, one concern per commit

## Project invariants

- [ ] **Prices are never persisted.** No code path writes quotes to any
      database. (Value Investing)
- [ ] SEC requests keep a compliant `User-Agent` and stay bounded — no
      database-wide sweep by default. (Financial-DataBase)
- [ ] Ingestion stays idempotent (`ON CONFLICT DO NOTHING`, per-company
      `import_runs`). (Financial-DataBase)
- [ ] Schema changes ship as a numbered migration in `db/migrations/` **and**
      the manifest assertions in `tests/unit/test_migrations.py` are updated.
      (Financial-DataBase)

## Verification

<!--
How you checked it beyond the test suite: a command and its output, a
before/after benchmark. For behaviour changes, numbers beat adjectives.
-->

```
```

## Screenshots / report excerpt

<!--
For report changes, paste the relevant section of
data/reports/daily_<date>.md (it is git-ignored, so paste the text).
-->
