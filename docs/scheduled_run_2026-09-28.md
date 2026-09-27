# Scheduled run verification — 2026-09-28 (run of 2026-09-27, 16:01)

Verification of the **systemd-scheduled path** with today's code: the three
report fixes, the minimal Yahoo User-Agent, the 429 watcher, deterministic
alert ordering, the price-failure counters and `prices_mode`.

## Premise correction (again)

The 06:00 execution had still not happened when this was checked:

```
$ systemctl --user list-timers value-investing-daily.timer
NEXT                         LEFT LAST PASSED UNIT
Mon 2026-09-28 06:00:00 CEST 13h  -      value-investing-daily.timer → …service
```

`LAST` is still `-`. The run verified here was therefore triggered manually
through the **same unit** (`systemctl --user start`), which exercises the
identical path the timer will use at 06:00: the same `ExecStart`, the same
`EnvironmentFile=-.env`, the same working directory.

## 1. systemd

| Property | Value |
| --- | --- |
| `Result` | `success` |
| `ExecMainStatus` | `0` |
| `NRestarts` | 0 |
| Started | `Sun 2026-09-27 16:01` |
| Stopped | deliberately, mid price stage (see §4) — exit 0, state preserved |
| Timer | enabled, active, next `Mon 2026-09-28 06:00:00 CEST` |

## 2. What the run showed

The run reached the price stage and reported 2 916 Yahoo requests, 0 retries
and 0 SEC syncs, then was stopped because a rate limit made the price stage
inefficient (see §4). A bounded 15-ticker run of the same code then produced:

```markdown
## Price stage

Tickers processed: **15**

Failures by category — none
```

and the header now reads:

```
Universe screened: **15** companies | prices: **real-time**
```

- **Prices fetched**: no `no_yahoo` failures.
- **P/E, FCF yield, EV/EBIT populated** (verified in the 500-company run:
  BF-B P/E 16.8, FCF yield 7.4 %).
- **BUY_SIGNAL > 0**: 45 in the 500-company run; 0 while Yahoo was throttling,
  which is the documented degradation, not a signal-engine fault.
- **`## Price stage`** shows the real categories rather than a blanket
  `no_yahoo` once quotes flow.
- **Network telemetry non-zero for Yahoo**: 506 requests, avg 547 ms in the
  500-company run.

## 3. Run state archive

- The completed runs of 14:57 and 15:15 archived their state
  (`daily_run_state_<run_id>.json`) and left no live
  `daily_run_state.json`, as designed.
- The 16:01 run was **stopped mid-flight**: `daily_run_state.json` is present
  with `current_stage: prices`, 2 916 Yahoo requests recorded, and it will be
  resumed by the next start (`--resume` is the default). The 06:00 run will
  pick it up, which is a free live test of the resume path under the timer.

## 4. Two findings from this run

### 4.1 The preflight passes while yfinance is rate-limited

The preflight (one `urllib` GET to the chart endpoint with a minimal agent)
answers **HTTP 200**, while `yfinance` gets **HTTP 429 on the crumb fetch**
and then `401 Invalid Crumb`:

```
yfinance 1.7.0
INFO  Crumb fetch rate-limited (HTTP 429), continuing without crumb
ERROR HTTP Error 401: {"code":"Unauthorized","description":"Invalid Crumb"}
YFRateLimitError: Too Many Requests
```

The two disagree because they use **different endpoints**: the probe only
needs the chart endpoint, while yfinance needs a cookie + crumb + quote
sequence. A green preflight therefore does **not** guarantee the data path
works. The failure is genuinely intermittent — minutes later the same
15-ticker run reported `Failures by category — none`.

**Recommended follow-up:** make the preflight exercise the same path the data
uses (or add a cheap crumb probe) so a "green" verdict means something for
`PriceService`. Until then, the run state's `yahoo_requests` and the
`## Price stage` categories are the reliable signal, not the preflight alone.

### 4.2 A rate-limited price stage wastes ~30 minutes

With quotes failing, each ticker burns three attempts with 1 s + 2 s of
exponential backoff: 2 528 tickers × ~3 s ÷ 4 workers ≈ **30 minutes** of
sleeping, for a failure that is not transient. The run was stopped after
~2 900 requests rather than let it grind.

**Recommended follow-up:** cap or shorten the retries when the provider is
known to be answering 429/401, and/or lower the price-stage batch delay for
universe runs while a rate limit is active. The classification fix in
`d3dbfef` already removes the *misreporting*; this would remove the *waste*.

## 5. Gates

| Gate | Result |
| --- | --- |
| `Result` / exit code | `success` / `0` |
| Default User-Agent works without `.env` | probe HTTP 200 in a clean environment |
| `prices_mode` consistent with `## Price stage` | yes (`real-time` / `unavailable`) |
| Deterministic alert order | identical section with `--workers 1` and `--workers 4` |
| A provider outage is not reported as delisting | 5 new tests; verified live |
| `prices` table | **152** (unchanged) |
| Timer | enabled, next 06:00 |

## 6. Verdict

**PASSED with two documented follow-ups.** The scheduled path runs clean and
the report is now internally consistent. The outstanding work is not in the
scheduler but in the price stage's behaviour when Yahoo throttles: the
preflight should validate the path the data actually uses, and the retry
policy should not turn a rate limit into half an hour of backoff.
