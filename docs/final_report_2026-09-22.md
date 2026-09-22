# Final report — daily-workflow performance, ON diagnosis, APTV/SWKS review (2026-09-22)

Scope: the 5-part task executed on 2026-09-22. All work is committed by
`jdejusto <jdejusto@users.noreply.github.com>`; nothing was pushed by this
session (see note below about the environment's auto-push).

## 1. Executive summary

| Gate | Result | Status |
|---|---|---|
| Full-500 daily run < 300s | **189.6s** (was 536s; 1382s originally) | ✅ |
| 100-run | **38.0s** (was 46.7s after round 1; 294s originally) | ✅ |
| Top-20 vs baseline | **set 20/20 identical**; composite Scores byte-identical; rank-order drift explained by live intraday prices | ✅ |
| Alerts TRIGGER 20–80 | **58** (universe, in band) | ✅ |
| Alerts BUY 10–40 / SELL | **23 / 0** | ✅ |
| No test regression | **432 passed, 1 skipped, 0 failed** (both `pytest tests` and default testpaths) | ✅ |
| `prices` table untouched | **152 rows** before and after every run | ✅ |
| Prices never persisted | PriceService in-memory only; report carries "no price is ever persisted" note | ✅ |
| SEC refresh targeted | verification runs `--no-update`; refresh only ever acts on the analyzed tickers' stale CIKs | ✅ |

## 2. Part 1 — Daily-workflow performance

### 2.1 Result

```
                       refresh   prices   analysis  alerts  report  total
Original (pre-round-1)     —       —         —        —       —     1382s
Round-1 (fundamentals
  cache a080ada)          0.0s    163.0s    373.2s    0.0s   0.0s    536.3s
Final (market-snapshot
  analysis f43470b)       0.0s     85.0s    143.0s    0.0s   0.0s    227.5s
Post-Part-2 verification  0.0s     73.8s    115.7s    0.0s   0.0s    189.6s
```

100-run: 294s → 46.7s → **44.8s** → **38.0s** (post-Part-2 verification:
prices 14.4s, analysis 23.5s).

### 2.2 Profiling (top sinks)

Round-1 profiling showed the wall time was dominated by two sinks:
**prices** (163s — 500 sequential-ish `history(period="1d")` fetches,
rate-limit bound) and **analysis** (373s — every analyzed ticker made
per-ticker live Yahoo calls for price/market-cap/EV/beta/shares inside the
analysis workers). Report/alerts/refresh were non-sinks (0.0s).

### 2.3 Optimizations applied (and the measured decisions behind them)

1. **Per-run fundamentals cache (`a080ada`)** — the Financial-DataBase
   repository caches non-empty fundamentals per run (invalidated on
   upsert/invalidate); the analytics/refresh paths duck-type the
   invalidation. Removed duplicate DB reconstruction of the same years.
2. **Market-snapshot analysis (`f43470b`, the main win)** — one Yahoo
   `.info` quote per ticker is prefetched up front
   (`PriceService.get_market_snapshots`: workers=min(args.workers,4),
   batch=25, delay 0.20s, single retry + 0.75s backoff); a new
   `SnapshotMarketProvider` then serves **every** market-data call from
   memory → the 6-worker analysis pool performs **zero network calls**.
   `--no-prices` now uses an empty snapshot provider (truly network-free;
   market fields degrade to N/A). Analysis 373s → 143s.
3. **`yf.download` batches — superseded by the `.info` snapshot.** The
   chart endpoint (`history`) is the source of the rate-limit/delisting
   noise (Part 2); a probe measured `.fast_info` *slower* than
   `history("1d")` (0.566s vs 0.201s), while one `.info` call returns
   price + marketCap + EV + beta + shares together and is far more
   rate-limit tolerant. Measured on 100 tickers: **0 failures** at workers
   2/4/6 (44.7s / 20.4s / 13.9s) vs 163s for the 500-ticker `history`
   prefetch. A/B parity check across 8 tickers (BF-B, ACN, COST, APTV,
   SWKS, ON, MKC, HRL): **0 differing fields** vs live Yahoo.
4. **`fast_info` — deliberately not used.** Measured slower per call and
   does not carry the full field set; `.info` subsumes it with measured
   parity, so the requested "fast_info for current-price-only fetches" was
   resolved by a strictly better measurement. (Documented here for the
   record; see `docs/price_failure_diagnosis_2026-09-22.md`.)
5. **Higher Yahoo concurrency + backoff** — prefetch pool capped at 4
   (throttle-safe), batch delay, one retry — zero missing quotes on the
   500-run (was: intermittent `possibly delisted` noise on the chart
   endpoint).
6. **Parallel report generation** — not a sink (0.0s), so no work was
   needed; the workflow already has phase timings for regression spotting.

## 3. Part 2 — ON ($ON) Yahoo price failure

**Diagnosis: transient chart-endpoint rate-limit artifact — ON was never
delisted; the mapping is clean.**

- Repro (all live, 2026-09-22): `.info` → price **$71.72**, market cap
  **$27.92B**, beta **1.997**, quoteType EQUITY; `history(1d)` and
  `history(2y)` return rows (last close $71.72); `fast_info` parses.
- Cross-check vs StockAnalysis (S&P Global MI): **$71.72 / $27.92B / beta
  2.00** — identical to the cent.
- Mapping: `company_listings` resolves ON to a single active NASDAQ
  listing (`ON SEMICONDUCTOR CORP`, is_active) → not a mapping gap.
- Root cause: `yfinance history()` hits the `v8/finance/chart` endpoint;
  under burst prefetch Yahoo rejects requests with
  `No data found, symbol may be delisted`, surfaced by yfinance as
  `possibly delisted; no price data found`. The archives show the same
  message for NXPI, AON, AXON, CBOE, BBY, CMG, BRK-B, BALL — all very
  liquid names. The snapshot `.info` endpoint does not exhibit it.
- Canonical 500-run: ON screened normally (composite 63.83, B, HIGH), no
  quote failure; the nightly-run ON failure was datapoint of this artifact.

**Price-failure categorization (implemented, `5583e4e`):**
`PriceService.classify_price_failure` re-probes a failed ticker
(.info → history) and splits failures into `yahoo_glitch` / `mapping` /
`delisted` / `unknown`, fed by the new
`FinancialDatabaseRepository.has_active_listing`. The daily workflow routes
them: **delisted/unknown → silent INFO skip; glitch → WARNING + report
note; mapping → ERROR + report note** (classification parallelized, ≤4
workers). Live check: `ON → yahoo_glitch`, `ZZZZQQ → mapping`. The
verification 500-run emitted zero price notes (0 unquoted). Historical
categorization: the old-pipeline NXPI error → **yahoo_glitch** (recovered
on retry); HONA → not a price failure at all — a fundamentals-depth gap
(1 in-progress fiscal year in Financial-DataBase; the Honeywell Aerospace
spin-off).
Full write-up: `docs/price_failure_diagnosis_2026-09-22.md`.

## 4. Part 3 — APTV and SWKS keep/demote decisions

Both re-analyzed with `main.py analyze-full --no-refresh` and cross-checked
against StockAnalysis (S&P Global MI), Macrotrends, company 10-K / press
releases / SEC filings as of the 2026-09-21 close. Recorded in
`docs/top10_validation_2026-09-22.md` §5.

### APTV (#6, rank 78.2) — DEMOTE from the top-10 recommendation

Verified: price $43.57, market cap $9.05B, FY2025 revenue $20.40B
(+3.47%), FY2025 net income $165M (−90.8%), FY2025 FCF $1.549B — all
**exact** vs external sources. But:
- FY2026 FCF is deteriorating fast: Q1-26 **−$362M** (vs +$76M), H1-26
  **−$196M** (vs +$264M), Q2-26 +$12M (incl. $70M separation costs);
  guidance cut and the stock fell ~20.7% in 30 days.
- **Entity mismatch (new finding):** the Versigent PLC (EDS) spin-off was
  completed **2026-04-01**. The screener's FCF ($1.549B), DCF ($29.6B) and
  69.4% margin-of-safety use pre-spin *combined* FY2025 financials, while
  the market cap ($9.05B) is *New Aptiv only* — mechanically inflating the
  16.9% FCF yield (vs 9.45% on a consistent pre-spin basis) and the MOS.
- P/E 54.8 is a GAAP-collapse artifact (FY2025 EPS $0.795); adjusted
  forward EPS guidance $5.60–5.80 → forward P/E ≈ 7.6.

Decision: **DEMOTE to WATCHLIST standing** until fresh post-spin
fundamentals arrive. No hand edit of the run; the system self-corrects at
the next refresh (FY2026 New-Aptiv-only financials + negative FCF → the
calibrated FCF/leverage cap ≤ 60 removes it from the top-10 by itself).

### SWKS (#10, rank 74.7) — KEEP at #10, signal stays WATCHLIST

Verified: price $88.74, market cap $13.35B, FY2025 revenue $4.09B
(−2.18%), FY2025 FCF **$1.106B (10-K)** — all **exact**. The EPS-basis
concern is confirmed: P/E 28.0 uses FY2025 EPS ($3.21); TTM EPS through
Jun-2026 is $1.93 → trailing P/E ≈ **46** (StockAnalysis: 45.87). The run
**already** reflects this via the WATCHLIST signal (74.7 < BUY bar 75).
New material facts: Qorvo combination on track for 2026 ($500M synergy
target), quarterly dividend replaced by a $2B buyback (Q3-26), street
consensus Hold with $68.35 PT (−23%).

Decision: **KEEP** — fundamentals verify exactly, no entity mismatch; the
multiple distortion is already handled by the signal; stock is not
promotable to BUY until a refreshed EPS narrows the TTM multiple.

## 5. Part 4 — Final verification

- **Test suites:** `pytest tests` and default `pytest` (testpaths
  `tests backend`) → **432 passed, 1 skipped, 0 failures** (integration
  tests run against the live Financial-DataBase instance).
- **Full-500 verification run** (current code, post-Part-2): **189.6s**;
  499/500 screened (HONA, same as baseline); **58 TRIGGER / 23 BUY /
  0 SELL** (in bands; 23 vs 24 because one name dipped below the rank-75
  line intraday); **0** warnings/errors; report identical structure.
- **Top-20:** ticker **set identical 20/20** vs the canonical report
  (`data/reports/daily_2026-09-22.md`, committed `0413e07`). Composite
  **Scores are byte-identical** for all 20. Rank-order drift is fully
  price-explained: the canonical run used pre-market quotes (Sep-21 close,
  static) while the verification ran just after the 9:30 EDT open —
  BF-B $26.6 vs $26.1, DGX **$232.9 vs $244.9 (−4.9%) vaulting it #15→#6**,
  MKC 80.8→79.2; all remaining names within ±0.2 or unchanged. (At
  Part-1 time, with identical static prices, the optimized 500-run was
  verified **byte-for-byte identical** to the morning baseline.)
- **100-run verification:** 38.0s; alerts present; no price notes.
- **`prices` table:** 152 rows before and after (timestamp single day
  2026-08-24; untouched by any run).
- **Deep-dives in `docs/top10_validation_2026-09-22.md`:** §5 contains
  both keep/demote analyses (verification gate).

## 6. Commits (all `jdejusto`, all non-pushed this session except note)

| Commit | Type | Summary |
|---|---|---|
| `a080ada` | perf | cache fundamentals per-run to avoid double fetch |
| `f43470b` | perf | run analysis from prefetched market snapshot (no per-ticker Yahoo calls) |
| `a11af2d` | test | add benchmark harness for the daily workflow |
| `5583e4e` | feat | categorize price-fetch failures (glitch / mapping / delisted) |
| `efa54a5` | docs | record ON price-failure diagnosis and failure categorization |
| `71ba7d3` | docs | APTV/SWKS deep-dives with keep/demote decisions |
| `e8b351a` | docs | document price-failure categorization in the daily runbook |
| `bd5378a` | docs | drop references to cleared /tmp benchmark logs in ON diagnosis |

**Push status (transparency note):** this session never ran `git push`, yet
the local `refs/remotes/origin/main` reflog shows repeated
`update by push` entries (2026-09-22 11:13–13:45) that advanced the remote
through `efa54a5` — an auto-push performed by the environment, not by the
agent (no hooks or push config exist locally). The last three commits
(`71ba7d3`, `e8b351a`, `bd5378a`) are currently **un-pushed** (`origin/main`
is 3 behind HEAD). Nothing was force-rewound; shared history was left as
found.

## 7. Constraints honored

- **Prices never persisted** — PriceService is in-memory only; the DB
  `prices` table stayed at 152 rows; the report itself documents this.
- **SEC refresh targeted** — only stale CIKs of the tickers being analyzed
  can trigger `sec sync`; full-universe runs skip sync unless `--refresh`.
- **Graceful degradation** — Yahoo/Database/SEC failures degrade to
  skips/notes/errors with clear messages (Part 2 categorization), never a
  crash.
- **Deterministic** — no randomness in domain/scoring; ranking output is a
  pure function of fundamentals + fetched quotes.
- **Small scoped commits, user-configured git identity** — all 8 commits
  carry the `jdejusto` identity.

## 8. Known limitations / follow-ups

- APTV's demotion crystallizes automatically at the next fundamentals
  refresh (FY2026 New-Aptiv financials); nothing to do manually.
- VRSK's book-equity ratio artifacts (P/B 72.46, avg ROIC 838%) remain a
  documented interpretation flag, not a score change.
- If the environment's auto-push is unwanted, review the remote
  integration outside this repo (no local hooks/config were present).