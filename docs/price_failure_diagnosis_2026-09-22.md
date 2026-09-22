# ON ($ON) Yahoo price failure — diagnosis (2026-09-22)

On the previous nightly run ON turned up with the Yahoo error
`possibly delisted; no price data found (period=1d)`, which was reported as a
price-fetch failure. This document records the reproduction, the root cause
and the follow-up that makes this class of failure diagnosable.

## Conclusion

**ON was never delisted, and there is no mapping problem.** The error is the
generic text Yahoo's *chart endpoint* returns when a quote request is
rejected/rate-limited during high-burst prefetching. ON (and many other very
liquid S&P names) produces exactly this error intermittently while the
exchange/brokerage world keeps trading it normally.

The quote pipeline has since been changed to use Yahoo's quote-summary
(`.info`) endpoint for the entire universe — which does not exhibit the
chart-endpoint rate-limit noise — so the failure mode no longer occurs on the
daily 500-universe run, and any remaining failure is categorized instead of
being misread as a delisting.

## Reproduction (all current, verified 2026-09-22)

Yahoo `.info`:

```
ON info keys: beta=1.997 mcap=27921932288 price=71.72 name=ON Semiconductor Corporation quoteType=EQUITY currency=USD
```

`history(period="1d")` → 1 row, last close `71.72`
`history(period="2y")` → 500 rows, last close `71.72`
`fast_info` → parses fine (exchange, currency, price fields present)

Independent cross-check (StockAnalysis, S&P Global MI data):

| Source | Price | Market cap | Beta |
|---|---|---|---|
| Yahoo `.info` | 71.72 | $27.92B | 1.997 |
| StockAnalysis.com | 71.72 (Sep 21 close) | $27.92B | 2.00 |

Both sources agree to the cent. ON is actively covered (29 analysts, consensus
Buy), trades on NASDAQ as `ON SEMICONDUCTOR CORP`, and was the subject of an
Investor Day on 2026-09-16 (multiple price-target updates since).

## Mapping check

`company_listings` in Financial-DataBase resolves `ON` cleanly:

```
 ticker | is_active | exchange |      legal_name
--------+-----------+----------+-------------------
 ON     | t         | NASDAQ   | ON SEMICONDUCTOR CORP
```

Single active listing — no ambiguity, so the failure is not in the
universe→company mapping category.

## Why the error happened

`yfinance`'s `history(period="1d")` hits Yahoo's `v8/finance/chart` endpoint.
When many requests are fired in short bursts (the 500-universe prefetch), Yahoo
rejects excess requests with a payload whose message is
`No data found, symbol may be delisted` — surfaced by yfinance as the
`possibly delisted; no price data found` error. It is endpoint-generic, not
ticker-specific. Evidence from archives:

- On the pre-change 500-universe run with the old history-based prefetch the
  exact same error appeared for `$NXPI` — yet NXPI screened normally, and the
  quote pipeline recovered on retry.
- Earlier logs show the same message for `$AON`, `$AXON`, `$CBOE`, `$BBY`,
  `$CMG`, `$BRK-B`, `$BALL`, etc. — all liquid, actively-traded names that are
  definitively not delisted.
- Re-running ON through a 6-burst `history(1d)` hammer reproduced **zero**
  failures — the artifact needs the full 500-request burst to manifest.

## Follow-up implemented

1. **Prefetch switched to quote-summary (.info)** — one `.info` call per
   ticker (price, market cap, EV, beta, shares) uses a different Yahoo
   endpoint that is far more rate-limit tolerant. Measured on the 500-run:
   **0 missing quotes** (previously the chart endpoint emitted intermittent
   `possibly delisted` noise and occasional blank rows).
2. **Failure categorization** — `PriceService.classify_price_failure` re-probes
   a failed ticker and splits the result into
   `yahoo_glitch` / `mapping` / `delisted` / `unknown`, using
   `FinancialDatabaseRepository.has_active_listing` for the mapping↔delisted
   split. The daily workflow routes them as: delisted → silent INFO skip,
   glitch → WARNING + report note, mapping → ERROR + report note.
3. If `ON` ever fails again it will be labeled **yahoo_glitch** (data is
   verified present on re-probe) with a warning note — never a false
   "delisted" conclusion.

## Categorization of the price failures observed in the canonical 500-run

| Ticker | Symptom (old pipeline) | Category |
|---|---|---|
| NXPI | `possibly delisted; no price data found` (chart burst) | **yahoo_glitch** (screened normally on retry) |
| HONA (Honeywell Aerospace spin-off) | missing from screen — not a price failure | **fundamentals depth gap** (only 1 in-progress FY in Financial-DataBase; reported under "Missing data") |
| ALL OTHERS (500) | — | fully quoted (0 missing) |

With the snapshot+classification pipeline the 500-universe run had **zero**
unquoted tickers, so no glitch/mapping/delisted notes were emitted.