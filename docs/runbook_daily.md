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
  github.com address family (see Financial-DataBase
  `docs/sec_403_investigation.md`); a descriptive UA with a normal email
  domain is required.
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
cd /home/caudillo/Financial-DataBase
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
cd /home/caudillo/Value_Investing
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
   `rank_score` column, data-coverage column, and the runtime in seconds) and
   the new state persisted for the next `SELL_WARNING` comparison.

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

```bash
systemctl --user daemon-reload
systemctl --user enable --now value-investing-daily.timer   # 06:00 daily, Persistent=true
systemctl --user start   value-investing-daily.service      # run once now
systemctl --user status  value-investing-daily.service
journalctl --user -u value-investing-daily.service -f
systemctl --user stop    value-investing-daily.service      # clean checkpoint + exit 0
```

`Persistent=true` runs a missed execution after a reboot, and the run's own
checkpoint continues it.

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
- **No basics for a ticker**: run the Financial-DataBase sync for it
  (`sec sync <CIK>`) or `load-data <TICKER>` on the Value Investing side.
- **`financial_database` module not found**: make sure `--fdb-dir` points to
  the Financial-DataBase repo and its `.venv` is installed.