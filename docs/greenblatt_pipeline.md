# Greenblatt pipeline

`GreenblattMethodology` is a **lookup, not a per-ticker calculation**. The
methodology reads `data/rankings/greenblatt_<date>.json` and returns
`INSUFFICIENT_DATA` when:

- no ranking file exists, or the newest file is stale
  (`STALE_DAYS = 14`),
- the ticker is not in the file,
- `roc <= 0` or `earnings_yield <= 0`.

The per-ticker `evaluate()` never touches the network or the database. It uses
`fundamentals` only for the `is_financial` guard; `prices` is unused.

## Data flow

1. `scripts/compute_greenblatt_rankings.py --universe sp500` runs weekly via
   `deploy/systemd/greenblatt-rankings.timer` (Monday 06:00, persistent).
2. For every ticker in `config/universe.csv` matching `SP500`, the generator:
   - reads fundamentals from Financial-DataBase with
     `get_best_available(ticker)`,
   - fetches market-cap snapshots from Yahoo through
     `PriceService.get_market_snapshots`.
3. It computes:
   - `return_on_capital = ebit / (max(current_assets - current_liabilities, 0) + net_ppe)`
   - `earnings_yield = ebit / (market_cap + total_debt - cash)`
4. It writes `data/rankings/greenblatt_<date>.json`:
   ```json
   {"date": "YYYY-MM-DD", "universe_size": 284, "rankings": {"AAPL": {"roc": ..., "earnings_yield": ..., "percentile": ...}}}
   ```
   **`universe_size` is the number of companies that received a rank**, not the
   size of the input universe. The run logs the input separately
   (`universe: 500 tickers (sp500)`). The old valid file used the same
   semantics (`270` ranked).
5. **Safety guard (2026-11-06):** if the run produces `rankings: {}` or
   `universe_size == 0`, the generator writes
   `greenblatt_<date>.failed.json`, preserves the last valid ranking file, and
   exits with code `1` so systemd records the failure.

## Failure modes

### Yahoo cookie/crumb DNSError (root cause of the 2026-10-12 outage)

Symptoms in `data/logs/greenblatt_rankings.log`:

```text
Cookie/crumb fetch failed (DNSError), continuing without crumb
universe: 500 tickers (sp500)
ranked 0 companies -> .../greenblatt_2026-11-02.json
```

Yahoo returns no `marketCap`, so every `earnings_yield` is `None`; the
generator had no rows to rank and wrote an empty file. The four weekly files
from 2026-10-12 to 2026-11-02 were empty because there was no safety guard and
the script still exited `0`. The last valid file was 2026-09-30 (270 ranked,
37 days old at the time).

Recovery on 2026-11-06: Yahoo was reachable again, the guard was added, and the
job was regenerated manually:

```text
universe: 500 tickers (sp500)
ranked 386 companies -> data/rankings/greenblatt_2026-11-06.json
```

### PostgreSQL unavailable — JSON fallback

The job log also shows:

```text
PostgreSQL unavailable — falling back to JSON storage
```

The systemd unit uses `EnvironmentFile=-%h/Value_Investing/.env`, but the
service environment did not see a working PostgreSQL connection. The JSON
fallback masks the problem. This is a **known environment issue**, not part of
the Greenblatt methodology; it is intentionally not fixed here. Treat it as a
separate systemd/env ticket and make the job fail loudly if the fallback is not
intended.

### Tickers outside the configured universe

`--universe sp500` only ranks SP500 names. BJRI (Russell2000) and European
names (CAC40/FTSE100/FTSE_MIB/OMXS30) will never appear in an SP500 ranking.
Since v0.21 they return **N/A with reason "ticker not in universe"** (the
master universe file says their source_index is not SP500) instead of
`INSUFFICIENT_DATA`; a ticker inside the SP500 that is missing from the
ranking still returns `INSUFFICIENT_DATA` so a real mapping gap is not hidden.
Running a multi-universe ranking (`sp500,russell2000,european`) remains a
product decision and is not implemented.

## Manual regeneration

```bash
# 1. Back up the current files first
mkdir -p /tmp/greenblatt_rankings_backup
cp -v data/rankings/greenblatt_*.json /tmp/greenblatt_rankings_backup/

# 2. Regenerate
.venv/bin/python scripts/compute_greenblatt_rankings.py --universe sp500

# 3. Check the exit code and the log
echo "exit: $?"
tail -20 /tmp/greenblatt_regen.log   # if redirected
```

If the run produces `rankings: {}`, the safety guard writes a `.failed.json`
and exits `1`; the last valid file is preserved. Do **not** overwrite a valid
ranking manually.

Verify the newest file:

```bash
python - <<'PY'
import glob, json, os
latest = sorted(glob.glob("data/rankings/greenblatt_*.json"))[-1]
d = json.load(open(latest))
print(os.path.basename(latest), "universe_size", d["universe_size"],
      "rankings", len(d["rankings"]))
PY
```

Verify one ticker (the correct command; `methodologies show` takes a
methodology name, not a ticker, and has no `--json`):

```bash
./vi analyze-greenblatt AAPL --no-refresh --no-color
```

`data/rankings/*` is gitignored, including `*.failed.json`; generated data is
not committed.

## Diagnosis checklist

1. `ls -lt data/rankings/greenblatt_*.json | head` — is the newest file empty?
2. `tail -100 data/logs/greenblatt_rankings.log` — look for
   `Cookie/crumb fetch failed (DNSError)` and `ranked 0 companies`.
3. Check `data/state/yahoo_health_streak.json` and a direct
   `PriceService.get_market_snapshots(["AAPL"])` probe.
4. Run the generator manually with output captured; check the exit code. A
   non-zero code + `.failed.json` means the guard worked.
5. If the input universe is 500 but `universe_size` is much lower, inspect
   missing inputs (`ebit`, `current_assets`, `current_liabilities`, `net_ppe`)
   and whether the ticker is outside the selected universe.

## Backup / rollback

The 2026-09-30 file and the four empty files were backed up to
`/tmp/greenblatt_rankings_backup/` before the job change, with SHA-256 in
`/tmp/greenblatt_rankings_backup.sha256`. To roll back the generated data,
copy the backup back into `data/rankings/`.
