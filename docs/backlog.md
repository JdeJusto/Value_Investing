# Backlog (updated 2026-09-30, after v0.1.0)

All P0/P1, the QA-session P2 items and the v0.1.0 hardening items are
closed. This file now tracks what remains.

## Closed in the v0.1.0 session (2026-09-30)

| Item | Commit |
| --- | --- |
| Unknown-ticker preflight only in `analyze-full` | shared `require_known_tickers` in all seven `analyze-*` commands (`4569b78`, 14 tests) |
| No test pinning the price fetch without a window | `26d22ec` (3 tests) |
| Greenblatt Magic Formula (P3) | 7th methodology with weekly rankings (`a7ebf3f`, 19 tests) |
| Screener enrichment sequential | bounded parallel `enrich_rows` (`57c2829`, 5 tests); cost is GIL-bound DB reconstruction, 1.14x measured |
| Unmapped revenue coverage (P3) | IFRS tags mapped (`5f4cd54`); classification in `docs/unmapped_coverage.md` |
| Leftover DEBUG prints in the CLI entry points | removed (`570847a`) |
| Repo-wide `ruff format` drift (77 files) | clean (`85efd90`) |
| First release | v0.1.0 tagged, CHANGELOG + README badges |

## Closed in the refinement sprint (2026-09-30)

| Item | Commit |
| --- | --- |
| `--no-refresh` was a parsed no-op in the six `analyze-*` commands | `54c24b1` (wired through `refresh_analysis_inputs`, regression tests) |
| Unknown ticker in `analyze-full` had no clear message | `1994ce2` (preflight resolver, exit 2, 5 tests) |
| Screener estimate hardcoded / "~0 min" | adaptive per-run measurement (screener commit) |
| Disagreement summary boilerplate on non-value/quality splits | conditional narrative + consensus (`disagreement_narrative`) |
| `buffett_classic` exempt from the financial guard | guard added; JPM/WFC abstain like the other five |
| Ford typed as financial by the leverage fingerprint | known non-financial sector now wins; Ford gets real verdicts |
| `historical-valuation` 37 s (one fetch per fiscal year) | one cached full-history fetch; measured 16 s |

## Remaining

### P2 — nice to have

1. ~~**Screener enrichment is GIL-bound.**~~ Done in v0.3.0: the screener
   reads the newest 10 fiscal years (SQL cap, 178 -> 146 ms/ticker) on top
   of the parallel enrichment. Deeper gains (bulk multi-ticker query) remain
   if needed.
2. **Greenblatt rankings need a schedule.** The methodology reads
   `data/rankings/greenblatt_*.json` and abstains when older than 30 days;
   add a weekly cron / `daily_workflow` hook so the file never goes stale.
   *Effort*: S.
3. **~1,020 analyzable companies still show no revenue** — structurally
   revenue-less funds, trusts, SPACs and shells
   (`docs/unmapped_coverage.md`). No mapping fix exists; the next lever is
   excluding them from revenue-based screens explicitly. *Effort*: S.
4. **JPM net income uses the common-stockholders tag** (55,681 M vs the
   57,048 M consolidated); documented in `docs/coherence_audit_2026-09-30.md`
   but worth a one-line note in the analysis output. *Effort*: XS.

5. **Frontend lint warnings in CI** (not failures): `setState`
   synchronously inside effects and fast-refresh-only-exports warnings in
   `src/store/AuthContext.tsx`, `src/pages/PortfoliosPage.tsx`,
   `src/pages/AlertsPage.tsx` and `src/pages/CompanyDetailPage.tsx`. The
   fixes touch React state flow, so they were deferred ahead of v0.1.1.
   *Effort*: S-M.

### P3 — deferred / future

5. ~~**Marks cycle positioning**~~ — shipped in v0.3.0 as the 8th
   methodology (measurable subset: cycle position, resilience, margin of
   safety, quality persistence).
6. ~~**`analyze-graham`/`lynch-garp` first-call warm-up**~~ — v0.3.0 runs
   the analysis price batch with 3 bounded workers (the remaining latency is
   Yahoo's own response time, not sequencing).

## Deferred

- **Ubuntu 26 migration (2026-10-19)**: GitHub Actions `ubuntu-latest`
  migrates to Ubuntu 26. Workflows are pinned to `ubuntu-24.04` (done);
  review and test on `ubuntu-26.04` when available.

## Pre-publish checklist

Before making the repository public:

- [ ] `git status` clean in both repos
- [ ] `main` in sync with `origin/main`
- [ ] Latest tag matches `__version__` and the top CHANGELOG entry
- [ ] CI green on `main` and on the latest tag
- [ ] No personal email in the tree beyond the intentional contacts
      (`SECURITY.md`, `CODE_OF_CONDUCT.md`)
- [ ] `.env` gitignored in both repos (and never tracked)
- [ ] LICENSE, CONTRIBUTING, SECURITY present (Value Investing also
      CODE_OF_CONDUCT)
- [x] Topics set on GitHub (both repos)
- [x] Roadmap issue pinned (Value Investing #18)

### Branch protection — applied 2026-09-30

> Branch protection applied on 2026-09-30:
> - VI: required checks = Unit tests (no database), Compile check, Frontend (audit, lint, build)
> - FDB: required checks = Unit tests (no database), PostgreSQL integration tests
>
> `strict: true`, force-push and branch deletion disabled, admins exempt
> (the release script pushes directly to `main`).

The commands below are kept as a reference for re-applying or adjusting
the protection (branch protection and rulesets require GitHub Pro or a
public repository — free private repos return HTTP 403).

```bash
# Value Investing
gh api repos/JdeJusto/Value_Investing/branches/main/protection -X PUT \
  -H "Accept: application/vnd.github+json" \
  -f "required_status_checks[strict]=true" \
  -f "required_status_checks[contexts][]=Unit tests (no database)" \
  -f "required_status_checks[contexts][]=Compile check" \
  -f "required_status_checks[contexts][]=Frontend (audit, lint, build)" \
  -f "enforce_admins=false" \
  -f "required_pull_request_reviews=null" \
  -f "restrictions=null" \
  -F "allow_force_pushes=false" -F "allow_deletions=false"

# Financial-DataBase
gh api repos/JdeJusto/Financial-DataBase/branches/main/protection -X PUT \
  -H "Accept: application/vnd.github+json" \
  -f "required_status_checks[strict]=true" \
  -f "required_status_checks[contexts][]=Unit tests (no database)" \
  -f "required_status_checks[contexts][]=PostgreSQL integration tests" \
  -f "enforce_admins=false" \
  -f "required_pull_request_reviews=null" \
  -f "restrictions=null" \
  -F "allow_force_pushes=false" -F "allow_deletions=false"
```

Applied on 2026-09-30 (both repos public); see the note above.
