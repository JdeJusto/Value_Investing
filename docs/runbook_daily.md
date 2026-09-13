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
  e.g. `export SEC_USER_AGENT='your-email@example.com'`.
- Optional universe file `config/universe.txt` (one ticker per line,
  `#` comments). The screener and the daily workflow use it as the default
  universe; the static ~150 ticker list is the fallback.

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

## 2. Daily workflow

```bash
cd /home/caudillo/Value_Investing
source .venv/bin/activate

# Full run: SEC update + screen + alerts + report
python scripts/daily_workflow.py

# Skip the SEC update but still screen and write the report/state
python scripts/daily_workflow.py --no-update

# Validate without touching anything (no SEC update, no files written)
python scripts/daily_workflow.py --dry-run

# Use a custom universe / output dir / no prices
python scripts/daily_workflow.py --universe config/universe.txt \
  --out data/reports --no-prices
```

What it does:

1. **SEC incremental update** (unless `--no-update`/`--dry-run`) via the
   Financial-DataBase CLI. Failures are reported in the markdown but never
   block the screen.
2. **Screen the universe** with the quality (Buffett) engine, enriched with
   real-time prices fetched **only for the universe tickers**.
3. **Alerts** from `backend/alerts`: `BUY_SIGNAL`, `SELL_WARNING` (chained to
   the previous day's state in `data/reports/daily_state.json`), and
   `TRIGGER_EVENT` (margin/ROIC/FCF/REV movements).
4. **Report** written to `data/reports/daily_YYYY-MM-DD.md` and the new state
   persisted for the next `SELL_WARNING` comparison.

`--dry-run` skips both the SEC update and file writes and prints the report
to stdout.

## 3. Screener with real-time prices

Market engine (fundamentals + live valuation filters):

```bash
# Default universe (config/universe.txt), real-time prices
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

## Troubleshooting

- **SEC update fails** ("SEC_USER_AGENT ... required"): export it before
  running `daily_workflow.py`, or set `SEC_EMAIL` in `.env`.
- **Prices show N/A**: Yahoo may be rate-limiting or offline; the workflow
  degrades gracefully and the report lists affected tickers under
  `## Price notes`. Re-run later.
- **No basics for a ticker**: run the Financial-DataBase sync for it
  (`sec sync <CIK>`) or `load-data <TICKER>` on the Value Investing side.
- **`financial_database` module not found**: make sure `--fdb-dir` points to
  the Financial-DataBase repo and its `.venv` is installed.