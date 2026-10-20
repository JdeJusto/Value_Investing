# Backlog (updated 2026-09-30, after v0.1.0)

All P0/P1, the QA-session P2 items and the v0.1.0 hardening items are
closed. This file now tracks what remains.

## Quality debt

Measured 2026-10-14 (stability/precision sprint):

- **Unit coverage: 73.3%** — `python -m pytest tests/unit --cov`, threshold
  `fail_under = 70` in `pyproject.toml` (the API suite is measured separately
  and `backend/api/*` is omitted from the unit coverage config). Files at 0%:
  `backend/analytics/ratios/revenue_growth.py`, `backend/core/database.py`,
  `backend/core/security.py`, `backend/domain/interfaces/cache.py`,
  `backend/domain/interfaces/repository.py`, `backend/logging_config/setup.py`,
  `backend/providers/cache/memory.py`, `backend/repositories/financials.py`,
  `backend/tasks/screener.py` and the `scripts/build_demo_*.py` generators.
- **Pyright (basic): 73 errors / 12 warnings** on the narrowed scope
  (`backend/services` + `backend/methodologies`, see `pyrightconfig.json`).
  The full `backend` + `cli` + `scripts` scope reports 195 errors, so the
  check is wired into CI as informational (`continue-on-error: true`) until
  the debt is paid down. Hot spots: `backend/services/ui_adapter.py`,
  `backend/services/yahoo_health.py`, `backend/services/price_service.py`.

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

6. **Wire ROIC / interest coverage / current ratio into
   `FinancialInsightsService`.** The scorecard's Financial Health dimension
   marks `current_ratio` `INSUFFICIENT` because no calculator exposes it. ROIC
   and interest coverage are already wired through `backend/analytics/ratios`
   (the scorecard calls `RoicCalculator` / `InterestCoverageCalculator`
   directly on the latest row). Promoting all three to first-class insights
   would remove the scorecard's only direct calculator calls. *Effort*: S.

### P3 — deferred / future

5. ~~**Marks cycle positioning**~~ — shipped in v0.3.0 as the 8th
   methodology (measurable subset: cycle position, resilience, margin of
   safety, quality persistence).
6. ~~**`analyze-graham`/`lynch-garp` first-call warm-up**~~ — v0.3.0 runs
   the analysis price batch with 3 bounded workers (the remaining latency is
   Yahoo's own response time, not sequencing).

## Deferred

- **Primary-document URLs in the filings list (99.7% fall back to the EDGAR
  index)**: FDB's `filings` table does not persist the SEC
  `primaryDocument` name (only 0.3% of rows have `filing_url`, so
  `sec_document_url` is mostly `None`). Consumers already prefer the
  document via `sec_url` (audited 2026-10-02; pinned by tests). Real fix:
  persist `primaryDocument` at FDB ingest time, or resolve the document name
  from SEC at listing time (would make `FilingService` fetch — currently
  "never fetches"). Priority: low (the index page is one click away).
- **Auto-follow incorporation-by-reference**: when a section points to another
  document, fetch and extract that document as well. Requires exhibit index
  parsing and additional SEC fetches. Priority: low (rare case, and the user
  can manually navigate to the referenced filing via the EDGAR link).
- **Ubuntu 26 migration (2026-10-19)**: GitHub Actions `ubuntu-latest`
  migrates to Ubuntu 26. Workflows are pinned to `ubuntu-24.04` (done);
  review and test on `ubuntu-26.04` when available.
- ~~**Hand-written `Pipfile.lock` entry for `plotly` (v0.17.0)**~~ — closed
  2026-10-20: the full `pipenv lock` ran on `chore/pipenv-lock-cleanup`
  (branched from v0.19.0, `3d873ea`). `plotly` resolved to 7.1.0 unchanged,
  so pipenv's own resolution now backs the entry and `_meta.hash.sha256` is
  pipenv's again. See "2026-10-20 — Pipenv lock exceptions" below for the
  three majors that were reverted.

## 2026-10-20 — Pipenv lock exceptions

`Pipfile.lock` was regenerated from scratch on a clean branch
(`rm Pipfile.lock && pipenv lock`, pipenv 2026.8.0). `_meta.hash.sha256`
stayed `9c5fd439…62eb3` because the `Pipfile` was not touched. 39 lock
entries moved: 33 runtime version changes, `toml` dropped (no longer pulled
by any runtime dependency) and 6 dev-package entries. `plotly` resolved to
7.1.0 (unchanged) and `streamlit` only moved 1.64.0 → 1.66.0 (minor).

The three major bumps below were reverted **individually**, back to the
exact previous lock entry (version + hashes + markers copied verbatim). The
`Pipfile` and `_meta` were left untouched, so `pipenv install --deploy`
still validates the hash. Each was constraint-checked against the *new*
parent versions before being pinned:

- `pyarrow` pinned to `25.0.1` (major `26.0.0` deferred): a C++ binary
  extension pulled by `edgartools` and `streamlit`; a major here moves the
  Arrow ABI under pandas/Polars with no functional gain for this project.
  `edgartools 5.62.0` requires `pyarrow>=23.0.1` and `streamlit 1.66.0`
  requires `pyarrow!=25.0.0,<27,>=10.0.1` (only 25.0.0 is excluded) — 25.0.1
  satisfies both.
- `websockets` pinned to `16.1.1` (major `17.3` deferred): the protocol layer
  behind `streamlit` sessions and `uvicorn[standard]`; protocol majors are a
  common source of silent stream/UI breakage. `streamlit 1.66.0` requires
  `>=12,<18`, and both `yfinance 1.7.0` and `uvicorn 0.54.0[standard]` require
  `>=13` — 16.1.1 satisfies all three.
- `soupsieve` pinned to `2.10` (major `3.0.3` deferred): the CSS-selector
  engine behind `beautifulsoup4`, i.e. the parsing path the EDGAR filing
  reader uses. `beautifulsoup4 4.15.0` requires `soupsieve>=1.6.1` — 2.10
  satisfies it.

To lift a pin, delete that one entry from the lock and re-run `pipenv lock`
once the major has a release or two of soak time. Nothing here is a
`Pipfile` constraint: these are transitive dependencies, so the next
regeneration will propose the majors again.

## 2026-10-20 — ruff pinning

`ruff` is now a pinned dev dependency (`ruff = "==0.16.4"` in
`Pipfile[dev-packages]`) and its configuration moved out of the standalone
`ruff.toml` into `pyproject.toml [tool.ruff]`, so lint and coverage config
live in the same file. `required-version = "==0.16.4"` makes the binary
refuse to run at all if it is ever swapped: with 0.17.1 on the PATH the run
aborts with "Required version `==0.16.4` does not match the running version
`0.17.1`".

**Why 0.16.4 and not the current 0.17.x.** ruff's *stable defaults* are not a
fixed contract. Measured 2026-10-20 on this tree, comparing the two binaries
with `--isolated` (defaults only, no project config): 0.16.4 reports 40
findings, 0.17.1 reports 47. The entire delta is `RUF100` (4 → 11): the `DTZ`
rules left the default set in 0.17, so seven existing `# noqa: DTZ001` /
`DTZ005` comments in *tracked* files — `scripts/daily_workflow.py:570`,
`scripts/validate_sp500.py:67` and five lines in
`tests/unit/test_price_service.py` — stop being "used" directives and become
violations instead. Same tree, same config, different verdict. Under the
project config the pre-fix totals were 12 (0.16.4) vs 19 (0.17.1).

0.16.4 is the version the whole cleanup sprint was measured with, so it is
the version that is pinned. Moving to 0.17 is a separate task: drop the seven
`DTZ` noqa directives (the rules are off), re-measure the baseline, then bump
`required-version`, the Pipfile and this note together.

**Why there is no explicit `select`.** An explicit rule list is the obvious
way to make linting version-independent, but ruff 0.16.4 enables **413 rules
by default** and they are *not* aligned to rule groups — only 3 of the 58 `S` rules, 2 of
the 18 `E` rules, 29 of the 39 `B` rules, and so on. Three measurements on
this tree:

- `select` set to the group prefixes present in the defaults → **12,007
  errors** (11,977 in tracked code), because every prefix pulls in the rules
  the defaults deliberately leave off;
- `select = ["ALL"]` → 810 rules, requiring a ~397-entry `ignore` list to
  get back to the current baseline;
- an exact prefix cover of the 413 defaults does not exist (only 5 prefixes
  are admissible, covering 30 rules), so the faithful alternative is a list
  of ~380 individual codes.

The codebase already passes all 413 default rules, so freezing the *version*
freezes the rule set exactly — no ignore list, no coverage loss, no
unmaintainable config. A curated `select` remains possible, but it is a
lint-policy conversation: it would trade currently-passing rules for a
hand-picked subset, and it belongs in its own change with its own review.

**`scripts_dev/` is excluded, not linted** (`extend-exclude`, together with
`.venv` and `node_modules`). It is tracked in git — three dev helpers: the
screenshot harness, the fixture surgery script and the theme verifier — so a
clean clone *does* see it; excluding it is what takes `ruff check .` from 6
findings to 0. Those files still carry stale `# noqa: E402` comments that
would become `RUF100` noise if the exclusion were ever lifted.

**CI has no lint job.** `.github/workflows/ci.yml` installs everything from
the lock (`pipenv install --system --deploy --dev`), so CI now gets
`ruff==0.16.4` exactly like a local clone, with no workflow edit needed.
`scripts/release.sh` is the only place that invokes ruff directly and it
picks up the pinned binary from `.venv`.

**Lock note.** `ruff` has zero runtime dependencies, so its entry was carried
into the lock and `_meta.hash.sha256` is pipenv's own value for the edited
`Pipfile` — the result is "previous lock + ruff", nothing else moved, and
`pipenv install --deploy --dev` accepts it. A plain `pipenv lock` re-resolves
everything and re-proposes the three majors reverted above (`pyarrow 26`,
`soupsieve 3`, `websockets 17`) plus unrelated minors (`fastapi 0.151`), so
the next regeneration needs the same review-and-revert pass documented in the
section above.

Baseline after this change: `ruff check .` 0, `ruff format --check .` 0 (564
files), unit 2363 passed / 2 skipped, api 125 passed. The six tracked findings
that were fixed are 2 × `I001` (`ui/pages/02_analysis.py`,
`ui/pages/04_portfolio.py`) and 4 × `C408` (`ui/theme/plotly_template.py`,
`dict(...)` → literals); three further files were reformatted to reach a
clean `ruff format --check .` (`tests/unit/test_ui_theme.py`, `ui/_shared.py`,
`ui/pages/06_consensus.py`) — cosmetic only.

## Shipped: real-time financial alerts (v0.10.1)

Ten deterministic rules over the FDB facts (see `docs/financial_alerts.md`):
low cash runway (CRITICAL); margin collapse, debt spike, inventory buildup,
negative FCF streak, dividend cut (WARNING); revenue decline, earnings
quality, EPS dilution, strong FCF conversion (INFO). UI sidebar panel +
`financial-alerts` CLI (exit 1 on CRITICAL).

Remaining follow-ups:

- **User-configurable thresholds** (a config file overriding the constants
  in `alert_service.py`).
- **External notifications** (email/Telegram/desktop) for CRITICAL alerts.

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
> - FDB: required checks = Unit tests (no database), PostgreSQL integration tests, Compile check
>
> Fresh-clone onboarding verified on 2026-09-30 (clean clone, no .env, no
> database, no network): `pipenv install --dev` (with
> `PIPENV_VENV_IN_PROJECT=1`) took 1m15s, `analyze-full AAPL --demo` 5s and
> `VI_DEMO=1 ./run_ui.sh` answered HTTP 200. The README quick start was
> fixed (33837ae): `uv sync` cannot work without a pyproject.toml and a
> plain `pipenv install` puts the virtualenv outside the project.
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
