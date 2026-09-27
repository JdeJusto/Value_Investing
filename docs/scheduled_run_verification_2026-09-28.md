# Scheduled run verification — 2026-09-28

Verification of the systemd-scheduled daily workflow with the **v2 analysis
cache**, covering the gates of the 2026-09-27 improvement session.

## Important premise correction

The task assumed the 06:00 run had already happened. **It had not.** At the
time of this verification (Sun 2026-09-27 15:15 CEST):

```
$ systemctl --user list-timers value-investing-daily.timer
NEXT                         LEFT LAST PASSED UNIT
Mon 2026-09-28 06:00:00 CEST 14h  -      value-investing-daily.timer → …service
```

`LAST` is `-` (never), so no calendar run had fired yet; the first scheduled
execution is 2026-09-28 06:00 CEST, ~14 h away. The last execution on record
was the **manual** `systemctl --user start` at 14:57 on 2026-09-27, which
rebuilt the v2 cache from scratch (cold).

To verify the gate anyway, the same service was started again at 15:15 with
the v2 cache already warm. That is the **exact condition tomorrow's 06:00 run
will find**, so the numbers below are the scheduled-run numbers.

## systemd status

| Property | Value |
| --- | --- |
| `Result` | `success` |
| `ExecMainStatus` | `0` (SUCCESS) |
| `NRestarts` | 0 |
| Wall clock | **9 min 53 s** cold run / **~2 min 10 s** warm run |
| CPU time | 8 min 45 s (cold) |
| Memory peak | 261.8 MB |
| Timer | `enabled`, `active`, next `Mon 2026-09-28 06:00:00 CEST` |

No crash, no SIGKILL, no restart, clean exit 0 on both runs.

## Stage-by-stage timings

| Stage | Cold run (14:57, v2 rebuild) | **Warm run (15:15, = tomorrow 06:00)** | Change |
| --- | ---: | ---: | ---: |
| refresh | 62.3 s | **50.5 s** | staleness scan only, 0 stale |
| prices | 5.8 s | **1.0 s** | preflight result cached in-process, no probe |
| analysis | 530.2 s | **78.8 s** | **6.7× faster** |
| alerts | 0.3 s | **0.1 s** | |
| report | 0.0 s | **0.0 s** | |
| **total** | **592.9 s** | **129.5 s** | **4.6× faster** |

**Gate: analysis < 100 s → PASSED at 78.8 s.**

The previous session projected ~28 s for the warm analysis. The real number
is 78.8 s, so **the projection was optimistic by ~2.8×** and the reason is
worth recording: the projection measured `analyze()` alone on 250 tickers,
while the stage also runs the screener, the quality/moat/Buffett scoring, the
delta metrics, the 78 no-data analyses that fail, and the parallel worker
pool. The headline conclusion (6.7× on the stage) stands; the absolute
projection did not.

## Cache statistics

```
fundamentals cache: {'hits': 2450, 'misses': 59, 'writes': 0,
                     'errors': 0, 'lookup_hits': 2450, 'lookup_misses': 0}
```

- **2 450 hits, 0 writes**: every company with fundamentals was served from
  disk; nothing was rewritten, so the cache is stable across runs.
- **59 misses**: the tickers with no fundamentals at all (78 reported as
  "analysis: no data" — the 59 that reached the cache layer). They have no
  fingerprint, hence no cacheable entry; they are not a cache defect.
- **2 450 lookup hits**: the `all_years` section added in the previous session
  is being read from cache instead of re-running `list_all()` — that was the
  single largest remaining cost in `analyze()`.
- Entries on disk: 2 450 files (`data/cache/analysis/`).

## Report content: no regression

Structural diff between the cold report and the warm one shows only:

1. the refresh duration (62 s → 50 s);
2. **the order of the TRIGGER_EVENT list** (e.g. `AMCR` one line lower).

The screened table is byte-identical: same top rows (COST 93.2, PAYX 88.9,
BF-B 95.5), same ratings, same ranks, same N/A price columns. The alert
reordering is **not** a regression: the engine iterates a dict built by the
parallel analysis pool, so the emission order follows worker completion order.
Same set, different order.

Sections verified present: universe size (2 528), refresh counts
(`0 refreshed · 0 stale · 2 519 fresh · 9 unmapped`), `## Network`,
`## Price stage`, `## Screened`, `## Alerts`, runtime.

## Gates

| Gate | Expected | Actual | Verdict |
| --- | --- | --- | --- |
| Result / exit code | success / 0 | `success` / `0` | PASS |
| Analysis stage | < 100 s | 78.8 s | PASS |
| Cache warm | mostly hits | 2 450 hits, 0 writes | PASS |
| Report content | no regression | identical table | PASS |
| `prices` table | 152 | **152** | PASS |
| `import_runs` running | 0 | 0 | PASS |
| Crash / SIGKILL | none | none | PASS |

Database after the run:

```
companies 8.023 | facts 76.124.913 | filings 1.094.172 | prices 152 | running 0
```

The live `daily_run_state.json` is absent (archived on success), as designed.

## Anomalies and follow-ups

1. **`prices_mode` says "real-time" even when the preflight skipped prices.**
   The header line `Universe screened: … | prices: **real-time**` is set from
   `--no-prices`, not from what actually happened; the `## Price stage` section
   (`no_yahoo: 2528`) carries the truth, but the header is misleading. Worth
   reporting "unavailable" when the preflight failed.
2. **Alert order is non-deterministic** with `--workers N` (worker completion
   order). Cosmetic, but it makes two reports of the same day look different
   at a glance; sorting the final list by (ticker, alert_type) would fix it.
3. **The alerts cache never hits in practice** — its digest includes
   `daily_state.json`, which every run rewrites, so `consecutive` runs always
   miss. Already documented in the module; this run confirms it
   (`alerts: {'hits': 0, 'misses': 1, 'writes': 1}`).
4. The first *real* 06:00 execution is still pending (2026-09-28 06:00 CEST);
   it should reproduce the warm-run column of the table above.

## Verdict

**PASSED.** The scheduled workflow runs clean with the v2 cache: the analysis
stage dropped 6.7× (530.2 s → 78.8 s) and the total 4.6× (592.9 s → 129.5 s),
the report content is unchanged, no gate regressed, and `prices` remains at
152 rows.
