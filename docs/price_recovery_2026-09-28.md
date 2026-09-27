# Price recovery — 2026-09-28

The Yahoo 429 that suppressed every price-derived metric for days turned out
**not** to be a rate limit. This records the evidence, the recovery, and the
one-line change that is still pending an operator decision.

## Probe results

| Check | Result |
| --- | --- |
| `check_yahoo_availability(force=True)` (first probe of the session) | `available=True`, HTTP 200 |
| `curl … chart/AAPL` with `User-Agent: Mozilla/5.0` | HTTP 200 (8/8 consecutive) |
| `curl … quoteSummary/AAPL` (raw curl, no cookie/crumb) | HTTP 401 — expected for raw curl; yfinance handles the crumb |
| `check_yahoo_availability()` inside a workflow run | HTTP 429 |

The contradiction between "curl 200" and "the workflow 429" is what led to
the root cause.

## Root cause: the probe's User-Agent, not the request rate

Same host, same path, same IP, same instant — only the `User-Agent` header
differed:

| User-Agent | Result |
| --- | --- |
| `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36` | **HTTP 429** |
| `Mozilla/5.0 (X11; Linux x86_64) … Chrome/120.0 Safari/537.36` (no `Accept`) | **HTTP 429** |
| `Mozilla/5.0` | **HTTP 200** |
| `Mozilla/5.0` + `Accept: application/json` | **HTTP 200** |
| `backend.services.yahoo_health._probe()` (the shipped one) | **HTTP 429** |

A browser-like UA without cookies or a crumb is exactly what bot detection
fingerprints as an unsatisfied browser client, and this host had been sending
only that. **The daily 429s were largely self-inflicted**: the preflight was
refused on its own header, while a plain client was served normally from the
same IP at the same time.

A second, unrelated failure mode also showed up on the way: one probe failed
with `Yahoo unreachable: Temporary failure in name resolution` (a local DNS
blip). That is not a rate limit and must not be reported as one — see
"Watcher fix" below.

## Recovery verified

With the probe UA overridden (no other change):

```bash
YAHOO_HEALTH_USER_AGENT="Mozilla/5.0" python -m scripts.daily_workflow --universe sp500 --top 20
```

**20-ticker check**

- `## Price stage` → `Failures by category — none`
- Price, P/E, FCF yield and EV/EBIT populated (ACN 176.1 / 14.0 / 10.1% / 10.5)
- Ranks moved **up** as predicted (ACN 74.1 → 79.6): with prices present,
  `rank_score` gets its margin-of-safety and momentum components back
  (79.6 vs the 74.1 ceiling of the price-less runs).

**Full S&P 500 check (500 companies)**

| Metric | Value |
| --- | --- |
| Timings | prices 97 s · analysis 15 s · total 112 s |
| Price stage | `yahoo_glitch: 2` (2 transient failures out of 500) |
| Network | `Yahoo requests: 506 (retries 4, avg 547.5 ms)`, SEC syncs 0 |
| Alerts | **107** = 62 TRIGGER_EVENT + **45 BUY_SIGNAL** |
| Screened | 499 / 500 |
| Top of the table | BF-B 95.5 / rank 85.0 / P/E 16.8 / FCF 7.4% / **BUY** |

The **45 BUY_SIGNAL** alerts are the clearest confirmation: with no prices the
absolute `rank_score` loses margin-of-safety and momentum and the signal
engine cannot reach its thresholds, so 0 fired for days. That matches the
documented expectation of 10-40 per daily run (this one is above the band
because it is a 500-name universe with live prices).

## Watcher fix found by this investigation

While reproducing, the streak watcher mislabelled the DNS failure as a 429
("Yahoo has returned HTTP 429" for a name-resolution error). Fixed:

- `is_rate_limit(health)` classifies the cause (explicit 429, "rate limit",
  "too many requests" → rate limit; DNS/TLS/timeout/5xx → not).
- The state stores `rate_limited`, and both channels word themselves
  accordingly: the report renders `## ⚠️ Yahoo Unavailable Alert` with a
  "Not a rate limit: check the local network first" note, and the flag file
  records `rate_limited: false`.
- The recovery worked as designed: after the successful full run the streak is
  `consecutive_failures: 0`, `alerted: false`, and
  `data/alerts/yahoo_429_active.flag` was removed.

## Pending decision for the operator

The probe UA is now configurable (`YAHOO_HEALTH_USER_AGENT`) but the
**default was deliberately left unchanged** — the instruction for this
session was not to fix the 429 in code, and the premise behind that
instruction (an IP-level rate limit) turned out to be wrong. Changing the
default is a one-line change in
`backend/services/yahoo_health.py::DEFAULT_USER_AGENT`:

```python
DEFAULT_USER_AGENT = "Mozilla/5.0"
```

With the evidence above, that is the recommended change: it restores prices
without any behaviour change beyond the header, and it removes the need to
export an environment variable for every scheduled run. Until then, add
`YAHOO_HEALTH_USER_AGENT="Mozilla/5.0"` to the git-ignored `.env` (or to the
systemd unit's `EnvironmentFile`, which already loads it) so the 06:00 run
gets prices.

Two related notes:

- `PriceService`'s actual data path uses **yfinance**, not this probe, and it
  was working or not depending on the same rate limiter. The preflight
  controls whether the pipeline is attempted at all, so a refused probe is
  what suppressed the whole stage.
- The report header still says `prices: real-time` when the preflight skipped
  the fetch (recorded as a follow-up in
  `docs/scheduled_run_verification_2026-09-28.md`); it should say
  "unavailable" so the header cannot contradict `## Price stage`.
