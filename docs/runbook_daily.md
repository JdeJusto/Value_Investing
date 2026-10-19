# Daily runbook — screening with real-time prices & daily report

This runbook describes the daily workflow for fundamental screening with
real-time prices. Prices are always fetched live from Yahoo Finance
(`PriceService`) **only for the tickers in the current query** and are
**never persisted**.

## Prerequisites

- **Financial-DataBase** repository at `../Financial-DataBase` with its own
  virtualenv (`.venv`) and a running PostgreSQL:
  `postgresql://financial:test@localhost:5432/financial_database`.
- **SEC_USER_AGENT** set (required by the SEC EDGAR incremental update),
  e.g. `export SEC_USER_AGENT='your-email@example.com'`. Put it in the repo
  `.env` (git-ignored) or let the systemd unit export it. **Never use a
  github.com address in the User-Agent** — SEC answers HTTP 403 for the
  github.com address family (see the companion
  [Financial-DataBase SEC investigation](https://github.com/JdeJusto/Financial-DataBase/blob/main/docs/sec_403_investigation.md));
  a descriptive UA with a normal email domain is required.
- Universe file `config/universe.csv` (default) — the **master universe**
  produced by `scripts/build_universe.py` from per-index source files:
  - `config/universe_sp500_nasdaq.csv` — S&P 500 + Nasdaq-100
    (`scripts/fetch_universe.py`);
  - `config/universe_russell2000.csv` — Russell 2000 constituents, from the
    official iShares IWM holdings snapshot (`scripts/fetch_russell2000.py`);
  - `config/universe_european.csv` — FTSE 100, DAX 40, CAC 40, IBEX 35,
    FTSE MIB, AEX, SMI, OMXS30, OMXC20/25 with `has_sec_filings`
    (`scripts/fetch_european_indices.py`).
  Columns: `ticker,cik,company_name,source_index` (comma-joined when a
  company belongs to several indices). Only companies with an SEC EDGAR CIK
  are kept — the project derives fundamentals exclusively from SEC filings,
  so European companies that do not file with the SEC (no ADR/20-F/40-F) and
  Russell names without a CIK are excluded from the master (they stay in
  their per-index file, flagged, for auditability).
- The daily workflow selects a universe with `--universe <named-subset|file>`:
  `sp500` (default), `nasdaq100`, `sp500,nasdaq100`, `russell2000`,
  `european`, `all`, or a path to a CSV/plain-text universe file. Run
  `python -m scripts.validate_universe_against_fdb --universe config/universe.csv`
  after regenerating to confirm FDB coverage stays ≥ 80% (gate used before
  pointing the daily job at a changed universe).

## 1. Update SEC fundamentals (Financial-DataBase)

The daily workflow runs this automatically unless you pass `--no-update` or
`--dry-run`. You can also run it by hand:

```bash
cd ~/Financial-DataBase
SEC_USER_AGENT="you@example.com" DATA_RAW_DIR=./data/raw \
  .venv/bin/python -m financial_database.cli sec update-incremental
```

This pulls the latest filings statement-by-statement. It is idempotent and
rate-limited; in a fresh environment run the full seed first:

```bash
# one-time bulk ingest (only if the database is empty)
.venv/bin/python -m financial_database.cli sec bulk-ingest
```

> **On-demand targeted refresh (analysis commands):** even without the bulk
> update above, every analysis command (`analyze`, `analyze-full`, `screener`,
> `momentum`, `opportunities`, `anomalies`, `alerts`, `buffett-analysis`,
> `historical-valuation`) checks the analyzed tickers' freshness and runs a
> targeted `sec sync <CIK>` for each stale company — never a full-universe
> sync. Use `--no-refresh` to skip it, `--refresh` to force it, or
> `--freshness-hours N` to change the threshold (default 168 h). The SEC sync
> needs `SEC_USER_AGENT`; without it the refresh step degrades with a clear
> message and analysis continues.
>
> Universe-wide runs (e.g. `screener` or `momentum` without explicit tickers)
> intentionally skip the sync to avoid syncing hundreds of companies at once;
> pass `--refresh` to force it on those too.

## 2. Daily workflow

```bash
cd ~/Value_Investing
source .venv/bin/activate

# Full run: SEC update + screen + alerts + report
# (module invocation is required — running scripts/daily_workflow.py directly
#  fails because `backend` is not on sys.path)
python -m scripts.daily_workflow

# Skip the SEC update but still screen and write the report/state
python -m scripts.daily_workflow --no-update

# Validate without touching anything (no SEC update, no files written)
python -m scripts.daily_workflow --dry-run

# Analyze only the first 200 tickers of the universe (staging / fast loop)
python -m scripts.daily_workflow --limit 200

# Pace price fetching to stay under Yahoo's rate limits
python -m scripts.daily_workflow --batch-size 25 --batch-delay 0.2

# Parallel fetch + analysis (8 workers): much faster on large universes, still
# paces price requests per batch; uses one PostgreSQL connection per thread
python -m scripts.daily_workflow --workers 8

# Use a named universe subset (sp500 | nasdaq100 | sp500,nasdaq100 |
# russell2000 | european | all) instead of the default S&P 500, or point at a
# CSV/plain-text universe file directly
python -m scripts.daily_workflow --universe russell2000 --limit 200
python -m scripts.daily_workflow --universe config/universe.txt \
  --out data/reports --no-prices

# Cap the on-demand targeted SEC refresh so a stale universe never triggers an
# unbounded sync: only the N most recently-synced stale companies are refreshed
# per run, the rest are deferred to later runs (default --max-refresh 200)
python -m scripts.daily_workflow --universe all --max-refresh 50

# Resume a run interrupted mid-universe (--resume is the DEFAULT): the
# checkpoint data/reports/daily_run_state.json is reused, so completed
# tickers are not SEC-refreshed again and transient refresh failures are
# retried. Use --no-resume to force a fresh run (the old state is archived)
# or --run-id ID to target a specific run.
python -m scripts.daily_workflow --resume
python -m scripts.daily_workflow --no-resume

# Ignore the fundamentals cache (data/cache/analysis) and re-read every
# company's financials from Financial-DataBase. Only needed after changing
# normalization logic (which should instead bump ANALYSIS_VERSION)
python -m scripts.daily_workflow --no-cache
```

What it does:

1. **SEC incremental update** (unless `--no-update`/`--dry-run`) via the
   Financial-DataBase CLI. Failures are reported in the markdown but never
   block the screen. Then a **targeted on-demand refresh** refreshes only the
   tickers about to be analyzed that are stale — capped at `--max-refresh`
   (default 200), prioritizing the most recently-synced companies, so a big
   universe never triggers an unbounded sync; the rest defer to later runs.
   With `--resume` (default), the previous run's checkpoint
   (`data/reports/daily_run_state.json`) is reused: tickers already completed
   are excluded from the refresh pool and only transient failures are retried.
2. **Screen the universe** with the quality (Buffett) engine, enriched with
   real-time prices fetched **only for the universe tickers** in paced
   batches (`PriceService.get_current_prices`, default batch size 25,
   0.2 s pause between batches; `--workers N` fetches each batch in
   parallel). Rankings use the calibrated cross-sectional `rank_score`
   (see `docs/scoring_methodology.md`).
3. **Alerts** from `backend/alerts`: `BUY_SIGNAL`, `SELL_WARNING` (chained to
   the previous day's state in `data/reports/daily_state.json`), and
   `TRIGGER_EVENT` — calibrated fundamental improvements only (see
   `docs/scoring_methodology.md` for thresholds). Expected counts on the
   ~500-company universe: TRIGGER_EVENT ≈ 6-12% (~30-60, ceiling 80),
   BUY_SIGNAL ≈ 10-40, SELL_WARNING ≈ 0-5 (only when scores actually drop
   ≥ 10 points vs the previous day).
4. **Report** written to `data/reports/daily_YYYY-MM-DD.md` (includes the
   `rank_score` column, data-coverage column, a `## Network` section with the
   SEC/Yahoo telemetry of the run, and the runtime in seconds) and
   the new state persisted for the next `SELL_WARNING` comparison.

Guardrails in the same run:

- **Yahoo preflight**: prices are probed before the universe-wide prefetch; if
  Yahoo is unreachable the prefetch is skipped, the run continues with market
  fields N/A and the report says so (see Troubleshooting).
- **Fundamentals cache**: the per-company database read is cached in
  `data/cache/analysis/<TICKER>.json` and reused while neither the company's
  facts nor the analysis version changed. Price-derived metrics are always
  recomputed, so a cache hit never serves stale market data. `--no-cache`
  forces a full re-read.
- **Network telemetry**: per-company SEC sync counts, retries and HTTP
  403/429 occurrences plus per-attempt Yahoo counters and average latency, in
  the run state and in the report's `## Network` section.

`--dry-run` skips both the SEC update and file writes and prints the report
to stdout.

## 2b. Background running and resume

The workflow is designed to run for hours in the background (SEC refresh of up
to `--max-refresh` companies) and to survive interruptions.

### Checkpoint / resume

- Every completed ticker is checkpointed in **`data/reports/daily_run_state.json`**
  (atomic write: temp file + `fsync` + rename), so a `SIGKILL` or power loss
  loses at most the ticker in flight.
- `--resume` is the **default**: same universe + same options → the run
  continues, skipping completed tickers in the SEC refresh and retrying only
  transient failures. Different options → the old state is archived
  (`daily_run_state_<run_id>.json`) and a fresh run starts.
- `SIGTERM`/`SIGINT` finish the current ticker, flush the state and exit 0.
- A successful run archives its state as `daily_run_state_<run_id>.json` (the
  live file disappears), so a *new* run never resumes a finished run.
- The report/analysis are recomputed for the whole universe on resume (the
  report needs every ticker); the expensive stage — the SEC refresh — is what
  is not redone.

```bash
# progress
python -c "import json;s=json.load(open('data/reports/daily_run_state.json'));print(s['run_id'],s['current_stage'],s['stage_progress'],len(s['completed']))"
tail -f data/logs/daily_workflow.log          # systemd run
tail -f data/reports/daily_2026-09-25.md      # last report
```

### systemd (user units, provided in `~/.config/systemd/user/`)

Enabled on 2026-09-27: the timer fires **daily at 06:00** with
`Persistent=true`, so a run missed while the machine was off/suspended starts
after the next boot and resumes from its checkpoint. The unit files are
versioned in the repo (`deploy/systemd/`); reinstall them with
`cp deploy/systemd/value-investing-daily.{service,timer} ~/.config/systemd/user/`.

`SEC_USER_AGENT` is deliberately absent from the unit (it must carry a real
e-mail and belongs in the gitignored `.env`, which the unit loads through
`EnvironmentFile`); without it the targeted SEC refresh is skipped, not
failed.

The run is started with `--verbose` so the scheduled log carries stage
progress, phase timings, fundamentals-cache stats and the network telemetry.
Stage output is structured JSON (see §2c, Logging): the default level is INFO
and `--verbose` lowers it to DEBUG.

```bash
systemctl --user daemon-reload
systemctl --user enable --now value-investing-daily.timer   # 06:00 daily, Persistent=true
systemctl --user disable --now value-investing-daily.timer  # stop scheduling
systemctl --user list-timers value-investing-daily.timer    # next elapse
systemctl --user start   value-investing-daily.service      # run once now
systemctl --user status  value-investing-daily.service
journalctl --user -u value-investing-daily.service -f
journalctl --user -u value-investing-daily.service --since today
systemctl --user stop    value-investing-daily.service      # clean checkpoint + exit 0
```

`Persistent=true` runs a missed execution after a reboot, and the run's own
checkpoint continues it.

**Where things land**

| What | Path |
| --- | --- |
| Daily report | `data/reports/daily_<YYYY-MM-DD>.md` |
| SELL_WARNING baseline (previous scores) | `data/reports/daily_state.json` |
| Live checkpoint (during a run) | `data/reports/daily_run_state.json` |
| Archived checkpoint (finished/failed run) | `data/reports/daily_run_state_<run_id>.json` |
| Service log | `data/logs/daily_workflow.log` (also in `journalctl --user -u value-investing-daily.service`) |
| Fundamentals cache | `data/cache/analysis/<TICKER>.json` |

All of these are gitignored: they are regenerated by every run.

**Interrupting and resuming**

- `systemctl --user stop value-investing-daily.service` (or `kill -TERM`) ends
  the run cleanly at the current ticker, flushes the checkpoint and exits 0.
- The next start resumes it automatically (`--resume` is the default). Never
  start a second run while one is alive: the checkpoint is a single file.
- `kill -9` loses at most the ticker in flight; the resumed run redoes it
  (transient failures are retried, permanent data failures are not).

**Reading a run afterwards**

```bash
# network telemetry of the last archived run (per-company SEC syncs, per-HTTP Yahoo)
python - <<'PY'
import glob, json
path = sorted(glob.glob("data/reports/daily_run_state_*.json"))[-1]
state = json.load(open(path))
print(state["run_id"], state["current_stage"], state["network"])
PY
```

The same numbers are rendered as a `## Network` section in the report.

Verified on 2026-09-27 with a manual `systemctl --user start`:
`Result=success`, `ExecMainStatus=0`, `NRestarts=0`, 6 min 37 s wall for the
2 528-ticker universe, `0 refreshed · 0 stale · 2 519 fresh · 9 unmapped`
(confirming the same-day sweep), 2 450 tickers screened, 279 alerts and the
report written to `data/reports/daily_2026-09-27.md`.

### Boot catch-up (`run_daily_on_boot.sh`)

`Persistent=true` replays a run missed while the machine was off, but only
once the timer's own service is triggered. On a desktop that is only online
for short stretches, `scripts/run_daily_on_boot.sh` (systemd user unit
`deploy/systemd/value-investing-daily-boot.service`) starts the workflow at
login and is a no-op when the day's run already happened — the timer and the
boot unit never double-run:

- **Per-day stamp.** The wrapper writes the date to `logs/.last_daily_run`
  after a run and exits immediately if that date is today, so a reboot later
  the same day does nothing. `--force` ignores the stamp (manual run).
- **Exclusive lock.** `flock` on `logs/.run_daily_on_boot.lock` stops two
  boots from starting concurrent runs.
- **10-minute network wait.** It polls a TCP connection to `data.sec.gov`
  before starting, instead of launching a run that would only see timeouts.
- **`--resume`.** It calls `python -m scripts.daily_workflow --universe all
  --max-refresh 200 --resume`, so it shares the scheduled run's checkpoint.
- **Post-run validation.** It runs `scripts/validate_data_sample --sample 10`
  (never fatal) and writes `logs/run_<date>.log`.
- **Weekly peer artifact.** On Sundays (`VI_PEER_STATS_DAY`, ISO weekday; `0`
  disables) it also runs `python -m scripts.build_peer_stats` to refresh the
  Scorecard's peer comparison. Best-effort: a failure is logged and never
  changes the run's exit status. `VI_PEER_STATS_EXTRA_ARGS` passes through,
  e.g. `--limit 200` for a quick partial rebuild.
- **Monthly data-quality audit.** On the **first Sunday of the month** (gate:
  `VI_AUDIT_WEEKDAY`, ISO weekday, default 7, and `VI_AUDIT_FIRST_DAY_MAX`,
  default 7, so only the first seven days count) it runs
  `python -m scripts.audit_data_quality --sample 30 --sources sec,yahoo --out
  logs`. `VI_AUDIT_SAMPLE=0` disables it and `VI_AUDIT_EXTRA_ARGS` passes
  through. Exit `0` means only expected cross-source differences, `1` means at
  least one `DATA_ERROR_FDB` (a value that traces to no SEC filing — news for
  the log, **never** a failure of the day, exactly like the validation), and `2`
  means the audit could not run (no database, no `SEC_USER_AGENT`, no network).
  Read the results with `logs/audit_data_quality_<date>.log`; every flagged
  class is explained in `docs/data_gaps_investigation.md`
  (§ Cross-source expected differences).

It needs **no sudo** (a user unit) and does not run from the agent.

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/value-investing-daily-boot.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable value-investing-daily-boot.service   # run at each login
systemctl --user status value-investing-daily-boot.service
journalctl --user -u value-investing-daily-boot.service --since today
scripts/run_daily_on_boot.sh --force                         # manual run now
```

### nohup / tmux alternative

```bash
./scripts/run_daily_background.sh              # nohup, PID + log under data/logs/
tmux new -s daily 'python -m scripts.daily_workflow --universe all --max-refresh 200 --top 20 --resume'
```

### If a run seems stuck

- `pgrep -af daily_workflow` to confirm it is alive; the state file's
  `last_update_at` tells you whether it is still progressing.
- Stop cleanly with `kill -TERM <pid>` (or `systemctl --user stop`); the state
  is flushed and the next run resumes.
- If the stored state is not what you want (wrong universe/options or a bad
  `--limit`), start fresh with `--no-resume` (the old state is archived, not
  lost) or target a specific one with `--run-id <id>`.

## 2c. Failure modes, retries, health checks and exit codes

### Health checks (pre-stage)

Before each network stage the workflow probes the provider, reusing the
project's existing preflights — there is no second mechanism:

- **SEC** — `backend/services/sec_health.py` (`check_sec_availability`): a HEAD
  on the companyfacts API (the same host ingestion uses), **3 s** timeout.
- **Yahoo** — `backend/services/yahoo_health.py` (`check_yahoo_availability`):
  a quote probe, **3 s** timeout, shared with the price service.

Each result is cached per process for 120 s, so the workflow's check and the
stage's own preflight issue **one** request, not two. When a probe fails, its
stage is skipped (the SEC refresh is not started; the price stage is aborted by
its own preflight), the run is marked **partial**, and analysis continues with
the fundamentals already stored in Financial-DataBase and N/A market fields.
`--no-update` and `--dry-run` skip the SEC probe (no SEC request is made);
`--no-prices` skips the Yahoo probe.

### Retries

The workflow's own network probes go through the shared helper
`backend/services/_retry.py` (`with_retry`): **3 attempts, backoff ×2**
(0.5 s, 1.0 s, capped at 4 s). Only transient failures are retried; an HTTP
verdict (403/429/5xx) is final and is never retried.

Deliberately **not** wrapped by the generic helper (see the provenance note in
`_retry.py`):

- **Yahoo price batch** (`PriceService`) — its quote path has a domain-aware
  policy that treats HTTP 429/401 as non-transient and aborts the stage instead
  of burning three attempts per ticker.
- **SEC sync subprocesses** — retry/backoff lives in Financial-DataBase and in
  the resume checkpoint: transient sync failures are retried by the next
  resumed run, permanent data failures are not.

### Failure modes

| Failure | Behaviour | Result |
| --- | --- | --- |
| SEC unreachable (health check fails) | Targeted refresh skipped before it starts; screening uses stored fundamentals | partial (1) |
| SEC reachable, one sync fails transiently | Recorded on the checkpoint; retried by the next resumed run | ok/partial |
| `SEC_USER_AGENT` unset | SEC probe reports unavailable without an HTTP call → refresh skipped | partial (1) |
| Yahoo unreachable | Price stage aborted by the preflight; market fields N/A | partial (1) |
| Yahoo rate-limits (429) | Price stage aborts (non-transient); streak alert after N runs | partial (1) |
| Database unreachable | `build_financial_repository` falls back to the JSON repository | ok (degraded) |
| Database unreachable and no JSON fallback | Startup raises → the workflow cannot start | failed (2) |
| Missing universe file / unknown `--universe` | `resolve_universe` raises `SystemExit` | 1 (config error) |

A **partial** run is not an error: it still writes the report and the state,
and the next run resumes from the checkpoint. A boot that never starts the
workflow (no network within 10 min) is a deliberate no-op and exits `0`.

### Exit codes

| Code | Meaning | Boot-wrapper log line |
| --- | --- | --- |
| `0` | every stage ran | `ok` |
| `1` | a network stage was skipped (provider down / retries exhausted) | `partial (a network stage was skipped)` |
| `2` | the run could not start (broken config / unreachable database) | `failed to start` |
| `130` | interrupted with Ctrl-C (`SIGINT`) | — |

`scripts/run_daily_on_boot.sh` propagates the workflow's code verbatim at the
end (`exit "$WORKFLOW_STATUS"`) — nothing masks it. The best-effort post-steps
(post-run validation, weekly peer stats, monthly audit) keep their own statuses
and never change it.

### Resume after a partial run

`--resume` is the default, so just start the workflow again (or let the next
scheduled/boot run do it): completed tickers are not SEC-refreshed again and
only transient failures are retried. Use `--no-resume` to start clean (the old
state is archived, not lost) or `--run-id <id>` to target a specific
checkpoint.

### Logging

Stage output is structured **JSON**, produced by the API's logger config
(`backend/api/logging_config.py`); the workflow installs it with
`configure_logging` (default level INFO — `--verbose` → DEBUG). Every line is a
JSON object with `asctime`, `levelname`, `name`, `message`, `pathname` and
`lineno`, so `data/logs/daily_workflow.log`, the boot-run log
(`logs/run_<date>.log`) and the systemd journal are machine-readable.

## 3. Screener with real-time prices

Market engine (fundamentals + live valuation filters):

```bash
# Default universe (config/universe.csv, S&P 500 + Nasdaq-100), real-time prices
python main.py screener

# Restricted set — prices fetched ONLY for these tickers
python main.py screener --tickers AAPL,MSFT,KO,JNJ,PG,BRK-B,XOM,JPM,V,WMT,HD,UNH

# Valuation filters (P/E, EV/EBIT, FCF yield)
python main.py screener --tickers AAPL,MSFT,KO --pe-max 20 --ev-ebit-max 15 \
  --fcf-yield-min 4

# Offline: no real-time price fetch (valuation columns will be N/A)
python main.py screener --tickers AAPL,MSFT --no-prices

# Search-based query
python main.py screener --search "apple"
```

Quality (Buffett) engine — adds real-time price columns to each result:

```bash
python main.py screener --tickers AAPL,MSFT,KO,JNJ,PG,BRK-B,XOM,JPM,V,WMT,HD,UNH \
  --filter min_score=60

python main.py screener --filter moat=STRONG min_score=80 --no-prices
```

Note on `--no-prices`: valuation filters (`--pe-max`, `--ev-ebit-max`,
`--fcf-yield-min`, `--pb-max`, ...) require a price; with `--no-prices`
companies whose valuation should come from the price are filtered out, so a
warning is printed when both are combined.

## 4. Consolidated per-company report

```bash
# Full 6-section report per ticker (one set of price calls per ticker)
python main.py analyze-full AAPL
python main.py analyze-full AAPL MSFT
python main.py analyze-full AAPL --no-prices
```

Sections: 1) company overview, 2) real-time price & valuation, 3) fundamental
metrics, 4) quality (Buffett/moat/DCF), 5) historical valuation (P/E & FCF
yield per fiscal year), 6) risks/anomalies/triggers. Every section degrades to
`N/A` if its data source is unavailable; a failing ticker never stops the
batch.

## 5. Alerts (standalone)

```bash
python main.py alerts                      # whole universe
python main.py alerts AAPL MSFT            # selected tickers
python main.py alerts --state data/reports/daily_state.json   # SELL_WARNING vs previous
```

## 5b. Catching up companies outside the universe

The daily workflow only refreshes tickers that are in the universe file, so
companies that never made it into `config/universe.csv` (Russell 2000 names,
OTC/foreign listings, delisted issuers) keep going stale. `scripts/catch_up_stale.py`
refreshes them **one CIK at a time** — there is no database-wide path in it, by
design: a blanket `sec update-all` would hammer the SEC with thousands of
requests.

```bash
# Plan only, no network call
python -m scripts.catch_up_stale --limit 20 --dry-run

# Sync the 20 companies whose newest filing is most recent
python -m scripts.catch_up_stale --limit 20 --priority recent_filings

# 7-day staleness (the daily workflow's threshold), bounded batch.
# --limit defaults to 100 (~10 min at 6 s per company); raise it
# deliberately for a long catch-up campaign.
python -m scripts.catch_up_stale --freshness-hours 168
python -m scripts.catch_up_stale --limit 500   # ~50 min, explicit
```

- `--priority recent_filings|alphabetical|random` — selection order.
- `--limit` is **mandatory in spirit**: it bounds the batch and a
  non-positive value is rejected, so a catch-up can never turn into a
  whole-database sync by accident. The default is **100** (~10 min at the
  measured 6 s per company) — aggressive enough to be useful, small enough
  that a mistake costs ten minutes, not an hour.
- `--refresh-workers` (default 2) and the SEC availability preflight apply, so
  a 403/429 stops the run before any doomed sync is launched.
- It is a **manual** tool: the daily workflow and the systemd timer never call
  it. Measured: 5 companies in 30 s (6,0 s per company, 2 workers, 0 rate
  limiting).

## 6. Universe management

The universe files are generated by a four-script pipeline (all in that order;
regenerating them overwrites the committed snapshots):

```bash
# 1) S&P 500 + Nasdaq-100 (Wikipedia) -> config/universe_sp500_nasdaq.csv
python scripts/fetch_universe.py

# 2) Russell 2000 constituents (official iShares IWM holdings snapshot,
#    Equity rows only) -> config/universe_russell2000.csv
python scripts/fetch_russell2000.py

# 3) Nine European indices (Wikipedia: FTSE 100, DAX 40, CAC 40, IBEX 35,
#    FTSE MIB, AEX, SMI, OMXS30, OMXC20/25) -> config/universe_european.csv.
#    Only SEC filers (ADR / 20-F / 40-F with an EDGAR CIK) can be analyzed, so
#    the file flags has_sec_filings and the non-filers stay out of the master.
#    Name-only SEC matching can wrongly flag a US company sharing the name
#    (NN Group/NN, Merck KGaA/Merck & Co, Compass Group/Compass Inc, EQT
#    AB/EQT Corp); those collisions are curated out in
#    scripts/universe_common.py::SEC_NAME_COLLISIONS.
python scripts/fetch_european_indices.py

# 4) Merge + dedup (by ticker, then by CIK) -> config/universe.csv (master)
python scripts/build_universe.py

# 5) Coverage gate: >= 80% of the master must resolve in Financial-DataBase.
#    Exit code != 0 when below threshold; unresolved list capped at 100.
python scripts/validate_universe_against_fdb.py
```

Shared helpers live in `scripts/universe_common.py` (SEC ticker/CIK map,
name-only European matching, `EUROPEAN_INDEXES` registry, ticker
normalization). Each fetch step resolves tickers to SEC CIKs via
Financial-DataBase `company_identifiers` and reports skipped names; the master
keeps only companies with a CIK (the project derives fundamentals exclusively
from SEC filings, so European names without an EDGAR presence and share-class
variants missing from FDB are excluded but remain visible in their per-index
files).

## 7. Monthly data-quality audit

The boot wrapper runs `scripts/audit_data_quality.py` on the first Sunday of the
month (see *Boot catch-up* above); to run it by hand:

```bash
# Cross-source audit of 50 sampled companies, SEC + Yahoo (read-only).
python -m scripts.audit_data_quality --sample 50 --sources sec,yahoo --out logs

# A specific list, SEC only — handy while chasing one finding
python -m scripts.audit_data_quality --tickers AAPL,KO --sources sec --out logs
```

Reports are written to `logs/audit_data_quality_<YYYY-MM-DD>.{log,json,csv}`.
Exit codes: `0` only expected differences, `1` at least one `DATA_ERROR_FDB`
(a value that traces to no SEC filing — the code to investigate), `2` the audit
could not run (database, `SEC_USER_AGENT`, or network). Every expected
difference class is documented in `docs/data_gaps_investigation.md`
("Cross-source expected differences"); a `DATA_ERROR_FDB` is not — work each one
against SEC `companyconcept` and fix the mapping (see
`docs/validation_methodology.md` §8 for the companion threshold report).

## Troubleshooting

- **SEC update fails** ("SEC_USER_AGENT ... required"): export it before
  running `daily_workflow.py`, or set `SEC_EMAIL` in `.env`.
- **Prices show N/A** ("missing quotes"): Yahoo may be rate-limiting or
  offline; the workflow degrades gracefully. Every unquoted ticker is
  re-probed and categorized (`docs/price_failure_diagnosis_2026-09-22.md`):
  `yahoo_glitch` → WARNING + report note (data exists on retry; analyzed
  with market fields N/A), `mapping` → ERROR + report note (symbol is not a
  known listed company — universe/CIK gap), `delisted`/`unknown` → silent
  INFO skip. Affected tickers are listed under `## Price notes`. Re-run
  later.
- **"Yahoo preflight unavailable"** (HTTP 429 / unreachable): the whole
  market-snapshot prefetch is skipped, so the run screens the universe with
  market fields N/A and the report's `## Network` section shows 0 Yahoo
  requests. This is throttle protection, not a bug — the fundamentals refresh
  still runs. Two visible consequences while it lasts: price-derived columns
  (P/E, P/B, FCF yield, EV/EBIT, price, margin of safety) are N/A, and
  `rank_score` loses its margin-of-safety and momentum components, so
  `BUY_SIGNAL` alerts can drop to 0 even though the fundamentals are intact
  (the report's cross-sectional `Rank` column stays in a usable range). Wait
  for the rate limit to expire and re-run; force a fresh probe with
  `YAHOO_HEALTH_TTL_SECONDS=0` (or a restart of the process).

  A rate limit is silent, so it is also **tracked**: each run that fails the
  preflight increments a streak in
  `data/state/yahoo_health_streak.json`, and after
  `yahoo_429_streak_threshold` consecutive failures (default 3, see
  `config/alerts.yaml`) the report gains a **`## ⚠️ Yahoo Rate Limit Alert`**
  section and `data/alerts/yahoo_429_active.flag` is created for cron or a
  dashboard to poll. Any successful preflight resets the streak and removes
  the flag.

  ```bash
  # is the rate limit still on?
  cat data/state/yahoo_health_streak.json
  test -f data/alerts/yahoo_429_active.flag && echo "Yahoo limited"

  # manual check + a small batch once it looks clear
  curl -s -o /dev/null -w "%{http_code}\n" -H "User-Agent: Mozilla/5.0" \
    "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=1d&interval=1d"
  python -m scripts.daily_workflow --universe sp500 --limit 20 --top 5
  ```
- **Refresh slower than expected**: read the report's `## Network` section —
  `sec_requests` (company syncs attempted), `sec_retries`,
  `HTTP 403/429` and `avg_sec_latency_ms` separate "SEC is slow" from
  "SEC is refusing us". A non-zero 403 count points at
   `SEC_USER_AGENT` (must contain a real e-mail, never a github.com domain;
   see the companion [SEC investigation](https://github.com/JdeJusto/Financial-DataBase/blob/main/docs/sec_403_investigation.md)).
- **Which query is slow?** `pg_stat_statements` is not enabled on this server
  and enabling it needs a PostgreSQL restart; the measured diagnosis, the
  exact commands and the alternatives that work without a restart (role-level
  `log_min_duration_statement`, `EXPLAIN (ANALYZE, BUFFERS)`, `cProfile`) are
   in [Financial-DataBase's PostgreSQL diagnosis](https://github.com/JdeJusto/Financial-DataBase/blob/main/docs/pg_stat_statements_blocker.md).
- **No basics for a ticker**: run the Financial-DataBase sync for it
  (`sec sync <CIK>`) or `load-data <TICKER>` on the Value Investing side.
- **`financial_database` module not found**: make sure `--fdb-dir` points to
  the Financial-DataBase repo and its `.venv` is installed.

## Greenblatt rankings

`backend/methodologies/greenblatt` reads the newest
`data/rankings/greenblatt_<date>.json`, computed from SEC fundamentals and
Yahoo market caps. The file is refreshed **weekly** by the user-level systemd
timer `greenblatt-rankings.timer` (Monday 06:00, `Persistent=true`); the units
are versioned in `deploy/systemd/` and installed under
`~/.config/systemd/user/`. Rankings older than **14 days** (two missed runs)
read INSUFFICIENT_DATA, so a failing timer shows up as abstaining verdicts.

```bash
systemctl --user list-timers | grep greenblatt          # next run
systemctl --user start greenblatt-rankings.service      # manual run
tail -n 20 data/logs/greenblatt_rankings.log            # output
python -m scripts.compute_greenblatt_rankings --universe sp500   # ad hoc
```
