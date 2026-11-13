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
- FMP is called through its legacy v3 endpoints. Some free accounts only have
  access to the newer *stable* API and get HTTP 403 on v3; that is logged and
  the service falls back to Yahoo (or Tiingo if its key is also present).

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
