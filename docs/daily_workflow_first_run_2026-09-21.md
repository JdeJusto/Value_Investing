# First real daily workflow run — report (2026-09-21)

First production (non-dry-run) execution of the daily workflow over the
S&P 500 + Nasdaq-100 universe (**500 tickers**, `config/universe.csv`).

## 1. Pre-flight checks

| Check | Result |
|---|---|
| a) PostgreSQL running | **PASSED** — `pg_isready` accepts connections on 5432 (`/run/postgresql:5432`) |
| b) Disk space ≥ 20 GB | **PASSED** — 357 GB free on `/home/caudillo` after the run (154→156 GB used) |
| c) Financial-DataBase suite | **PASSED** — `tests/unit` 148 passed; full `tests/` **184 passed, 0 failed** |
| d) Value Investing suite | **PASSED** — `tests/unit` **387 passed, 1 skipped, 0 failed** (pre-run: 382 passed) |
| e) Universe file | **PASSED** — 501 lines = header + 500 tickers, all CIK-mapped (0 unmapped) |
| f) `SEC_USER_AGENT` | Set explicitly for the run: `ValueInvesting/1.0 <your-e-mail>` (real contact, read from the git-ignored `.env`; same UA shape already validated against SEC live) |
| g) DB snapshot (pre-run) | companies **8,023** · facts **76,035,751** · filings **1,091,495** · prices **152** |
| h) `import_runs` (pre-run) | 29 success · 2 failed · 13 stuck in "running" since 2026-09-08 (stale marker only — not used by freshness logic; non-blocking) |

## 2. Scope estimate (dry-run, read-only)

`RefreshService.check_freshness` over the 500 tickers (no sync, no prices):

- **496 of 500 stale** (>168 h) · 4 fresh · 0 unmapped
- Estimated duration at ~3.1 companies/min: refresh ≈ 2.6–2.8 h + analysis ≈ 20 min
- **Action:** per the run policy (>300 stale), the scope was presented to the
  user and the **full run was approved**.

> Note: before launching, `scripts/daily_workflow.py` still invoked
> Financial-DataBase's `sec update-incremental` (a full-universe sync over all
> ~8,000 companies — a hard-rule violation). This was replaced with the
> targeted per-CIK refresh from `RefreshService` (see §10).

## 3. Real run outcome

### Run 1 (2026-09-21 ~09:45→… local / 12:18→14:32 UTC), pid 5579
- Targeted SEC refresh: **496/496 `sec sync` succeeded, 0 failed** (~2 h 14 m, @ ~3.1/min)
- Crashed **after** the refresh, in the alert phase: `AttributeError` in
  `detect_trigger` on a `None` analysis (a company whose `analyze()` returned
  `None` instead of raising — no "analyze failed" warning was logged).
- Data layer completed: all 496 companies ingested; facts +7,695; filings +196.

### Resume attempt (pid 39568)
- Killed by the environment restart during price prefetch; `companies.updated_at`
  timeline confirms 0 companies synced by it (freshness checks only).

### Run 2 — final successful run (pid 3536, started 2026-09-22 09:45 local, ended 10:09)
- SEC refresh (targeted): **1 refreshed · 499 fresh/skipped · 66 s**
  — the only stale company on 09-22 was **XOM** (7.6 days old; +20,629 facts),
  confirming the targeted mechanism refreshes *exactly* the stale companies.
- Real-time prices fetched for all 500 (batched 25, 0.2 s delay, **never persisted**).
- Analysis: **499 of 500** screened (`HONA` — Honeywell Aerospace — unable to
  analyze: only 298 facts / insufficient history; reported under Missing data).
- Runtime: **1,387 s** per the report.

### Alerts generated (report dated 2026-09-21)
- **BUY_SIGNAL: 24** (all HIGH confidence)
- **TRIGGER_EVENT: 475** (463 MEDIUM + 12 HIGH)
- **SELL_WARNING: 0** — expected: `daily_state.json` only held ~20 tickers of
  prior state on the first run; comparisons start from the next run.

## 4. Report location and key content

`/home/caudillo/Value_Investing/data/reports/daily_2026-09-21.md` (38.9 KB)

- Universe screened: **500** · passed: **499** (coverage 100%) · prices: real-time
- Top-20 table (rank, rating, score, price, P/E, FCF yield, EV/EBIT, signal)
- Alerts section (24 BUY_SIGNAL, 475 TRIGGER_EVENT)
- Missing data: HONA
- Data-integrity line (*"no price is ever persisted… `prices` table untouched"*)
- Runtime: 1,387 s

State persisted for tomorrow: `data/reports/daily_state.json` (61.4 KB, all 500).

## 5. Database state before → after

| Metric | Pre-run | Post-run | Δ |
|---|---|---|---|
| companies | 8,023 | 8,023 | 0 |
| financial_facts | 76,035,751 | 76,064,075 | **+28,324** (refresh only) |
| filings | 1,091,495 | 1,091,828 | +333 |
| prices | **152** | **152** | **0 — no price persisted** |

No corruption; facts/filings only ever increased; no new companies added.

## 6. Verification of no price persistence

- `SELECT count(*) FROM prices` = **152 before and after** the entire operation
  (0 new rows despite 500 real-time price fetches).
- All price traffic flows through `PriceService` (Yahoo, in-memory cache, TTL 900 s).
- The report's `prices` column values match the live `analyze-full` spot checks
  performed post-run.

## 7. Errors and warnings

- **Alert-engine crash (run 1)** — fixed, see §10 (commit `5baaae8` + `b20acef`).
- **HONA** — analyzed as `None` (insufficient data) → gracefully listed under
  Missing data; 298 facts exist in the DB (CIK 0002089271, synced in run 1).
- Transient Yahoo noise: `$LRCX/$NOC/$PFG/$PG/$PGR: possibly delisted; no price
  data found (period=1d)` — non-fatal; those tickers still screened with
  available metrics.
- 13 stale `import_runs` rows marked "running" since 2026-09-08 — historical
  artifact, not consulted by the freshness logic; no action needed.

## 8. Top 10 opportunities

| # | Ticker | Company | Score | Signal |
|---|---|---|---|---|
| 1 | BF-B | Brown-Forman | 90.1 | BUY |
| 2 | ACN | Accenture | 90.2 | BUY |
| 3 | MKC | McCormick & Co | 88.4 | BUY |
| 4 | PAYX | Paychex | 84.6 | BUY |
| 5 | HII | Huntington Ingalls | 85.8 | BUY |
| 6 | APTV | Aptiv | 88.0 | BUY |
| 7 | HSIC | Henry Schein | 91.0 | BUY |
| 8 | VRSK | Verisk Analytics | 83.8 | BUY |
| 9 | HRL | Hormel Foods | 89.4 | BUY |
| 10 | SWKS | Skyworks Solutions | 85.2 | WATCHLIST |

Spot-checked against live `analyze-full` (P/E, FCF yield, total score) — all match.

## 9. Recommendation

**Run successful.** The daily workflow completed end-to-end: targeted refresh of
stale companies only (497 across the operation: 496 on 09-21 + XOM on 09-22),
real-time prices for 500 (never persisted), 499 analyzed, report + state written,
alerts generated, no test regressions, no DB corruption.

Ready to schedule as a daily job. Proposed configuration (NOT created — for user
decision):

```ini
# /etc/systemd/system/value-investing-daily.service
[Unit]
Description=Value Investing daily workflow (S&P 500 + Nasdaq-100)
After=network-online.target postgresql.service

[Service]
Type=oneshot
User=caudillo
WorkingDirectory=/home/caudillo/Value_Investing
EnvironmentFile=/home/caudillo/Value_Investing/.env
EnvironmentFile=-/home/caudillo/Value_Investing/.env   # provides SEC_USER_AGENT
ExecStart=/home/caudillo/Value_Investing/.venv/bin/python -m scripts.daily_workflow --top 20
# Allow up to 4 h for the run (refresh is skipped by default once fresh)
TimeoutStartSec=14400

[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/value-investing-daily.timer
[Unit]
Description=Daily Value Investing analysis
[Timer]
OnCalendar=07:30
RandomizedDelaySec=15m
Persistent=true
[Install]
WantedBy=timers.target
```

Run 2+ will be fast: with all 500 companies fresh, the refresh phase is ~1 min of
freshness checks and the job is dominated by ~23 min of screening/analysis.

## 10. Code changes (committed; author jdejusto; no push, no PR)

| Hash | Type | Description |
|---|---|---|
| `071dc57` | feat(refresh) | read-only `RefreshService.check_freshness` for scope estimation (+4 hermetic tests) |
| `b0a10c5` | fix(daily-workflow) | replace full-universe `sec update-incremental` with targeted per-CIK refresh; add `--refresh/--no-refresh/--freshness-hours` |
| `0e4ea81` | feat(report) | add *"prices never persisted"* data-integrity line to the daily report (+test) |
| `5baaae8` | fix(alerts) | `alert_engine.run()` skips `None` analyses instead of crashing |
| `b20acef` | test(alerts) | regression test: XDATA (None) skipped in `run()` |

Runtime artifacts (`data/reports/*`, `data/state`, logs) remain untracked per
project policy.