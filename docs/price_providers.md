# Price providers

Value Investing reads prices on demand (nothing is persisted). **yfinance** is
the default and needs no key. FMP and Tiingo are optional alternatives for
environments where Yahoo rate-limits (HTTP 429).

| Provider | Key required | Free tier | Default |
|---|---|---|---|
| yfinance | No | rate-limited by Yahoo | ✅ |
| FMP (Financial Modeling Prep) | `FMP_API_KEY` | 250 req/day | — |
| Tiingo | `TIINGO_API_KEY` | 1,000 req/day | — |

## Setup

1. Copy `.env.example` to `.env`.
2. Register at [FMP](https://financialmodelingprep.com/) and/or
   [Tiingo](https://www.tiingo.com/).
3. Add your keys to `.env` (local file, gitignored):
   ```dotenv
   PRICE_PROVIDER="fmp"          # or "tiingo"; default "yfinance"
   FMP_API_KEY="..."             # only if you use FMP
   TIINGO_API_KEY="..."          # only if you use Tiingo
   ```
4. Run any command that needs prices.

**Never commit `.env`.** It is in `.gitignore` (and `.env.*` is ignored with an
explicit exception for the tracked `.env.example`).

## Behaviour

- No `PRICE_PROVIDER` and no keys → yfinance, exactly as before.
- `PRICE_PROVIDER=fmp|tiingo` with its key present → that provider is tried
  first. If both keys are present, the other provider is tried second.
- Any provider failure (network, HTTP error, empty series) is logged and the
  next provider runs; Yahoo is always the final fallback.
- A provider selected without its key silently resolves to yfinance, so a
  fresh clone without `.env` keeps working.
- Adjusted closes are used when the provider exposes them (`adjClose`), keeping
  the backtest series consistent with Yahoo.
- FMP uses the **stable** endpoints (`historical-price-eod/dividend-adjusted`
  and `quote`), which work on the free tier. Legacy paid accounts that only
  expose v3 are tried as a fallback. Adjusted closes are used, so the series
  matches Yahoo/Tiingo.

## Where it lives

- `backend/services/price_providers/` — `yfinance`, `fmp`, `tiingo` adapters.
- `backend/services/price_service.py` — tries the configured providers, then
  the existing Yahoo retry/throttle path.
- `tests/unit/test_price_providers.py` — mocked HTTP; no test needs a key.

## Security

The key is read from the environment at request time and sent as a query
parameter (FMP) or an `Authorization` header (Tiingo). It is never written to
logs, the disk cache, the repository or a test fixture. If a key is ever
committed, rotate it immediately in the provider dashboard.

## Rate limits and batch operations

| Provider | Free tier | Batch-safe? |
|---|---|---|
| yfinance | rate-limited by Yahoo, but bulk-downloadable | ✅ `yf.download` |
| FMP | 250 req/day | ❌ 500 tickers = 2 days |
| Tiingo | 50 req/hour | ❌ 500 tickers = 10h |

**Rule:** batch operations (`vi rank`, screener prefetch, consensus, portfolio
bulk views) use Yahoo's **bulk download** (`yf.download`, one request per
100-ticker chunk) and never one request per ticker to FMP/Tiingo. Single-ticker
commands (`scorecard`, `financials`, `dcf`) still respect `PRICE_PROVIDER` and
try FMP/Tiingo in the configured order.

**Circuit breaker:** after 3 consecutive 429/403 responses, a provider is
disabled for 60 seconds and skipped by the fallback chain. It logs **one**
warning per outage; per-ticker failures stay at debug level. A 500 or a network
timeout does not trip the breaker (only rate-limit/forbidden errors).

If Yahoo's bulk request itself fails, batch operations return `None` for that
chunk instead of cascading hundreds of per-ticker fallbacks. Individual missing
names inside a successful batch still fall back once.

For batches with Tiingo/FMP you need a paid plan (FMP Starter, Tiingo Power);
the free tiers are documented here only for single-ticker use.
