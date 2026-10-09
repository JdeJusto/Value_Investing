# API Design — Value Investing Platform

> Roadmap issue: [#27](https://github.com/JdeJusto/Value_Investing/issues/27)

Generated: 2026-10-07

This document describes the REST API contract for the Value Investing platform.
The API is **additive** — it reuses existing services and does not replace the CLI or Streamlit UI.

---

## B1 — Framework Choice: FastAPI

**Decision:** FastAPI (via `uvicorn`)

**Rationale:**
- Native async support — essential for Yahoo Finance I/O and concurrent requests
- Automatic OpenAPI/Swagger docs at `/docs` and `/redoc`
- Pydantic v2 for request/response validation and serialization
- Type-hint driven — matches existing codebase style
- Small footprint (~500 lines for a full app with auth, caching, docs)
- Standard in Python ecosystem; easy to hire/debug

**Alternatives considered:**
- Flask: no async, no auto-docs, manual validation
- Django REST Framework: heavyweight (~200MB), overkill for ~30 endpoints
- Litestar: newer, smaller community, similar to FastAPI but less proven

**Dependencies (added as optional extra):**
```toml
[project.optional-dependencies]
api = ["fastapi>=0.110", "uvicorn[standard]>=0.29", "python-multipart>=0.0.9"]
```

Install with: `pipenv install -e ".[api]"` (base install unchanged)

---

## B2 — Endpoint Surface (30 endpoints: 22 near-term + 8 deferred)

All endpoints prefixed with `/api/v1/`. Versioning allows future breaking changes without breaking installed mobile apps. Phases 1-5 implement the 22 app-facing endpoints; the remaining 8 stay here as design intent and are deferred (see `docs/api_roadmap.md`, "Deferred endpoints").

### Response Envelope

All successful responses:
```json
{
  "data": { ... } | [ ... ],
  "meta": {
    "source": "financial_database" | "yahoo" | "mixed",
    "as_of": "2026-10-07T18:30:00Z",
    "cache_ttl": 3600
  }
}
```

List responses include pagination in `meta`:
```json
{
  "data": [ ... ],
  "meta": {
    "source": "financial_database",
    "as_of": "2026-10-07T18:30:00Z",
    "cache_ttl": 3600,
    "total": 500,
    "page": 1,
    "page_size": 50
  }
}
```

Error responses:
```json
{
  "error": {
    "code": "TICKER_NOT_FOUND",
    "message": "Company AAPL not found in Financial-DataBase"
  }
}
```

### Company Endpoints (10)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Health check (no auth) |
| GET | `/api/v1/version` | API version + build info (no auth) |
| GET | `/api/v1/company/{ticker}` | Company profile (name, sector, CIK, identifiers) |
| GET | `/api/v1/company/{ticker}/fundamentals` | Fundamentals (last N fiscal years); `?years=10` |
| GET | `/api/v1/company/{ticker}/methodologies` | All 8 methodology verdicts + scores (✅ shipped v0.14.0) |
| GET | `/api/v1/company/{ticker}/dcf` | DCF valuation (not-from-canon) (✅ shipped v0.14.0) |
| GET | `/api/v1/company/{ticker}/filings` | SEC filings list; `?form=10-K&year=2025&limit=20` (✅ shipped v0.15.0) |
| GET | `/api/v1/filings/{accession}/statement/{type}` | Statement from filing; `type` = `balance_sheet`, `income_statement`, `cash_flow` (✅ shipped v0.15.0) |
| GET | `/api/v1/filings/{accession}/section/{type}` | Narrative section; `type` = `risk_factors`, `md_a` (✅ shipped v0.15.0) |
| GET | `/api/v1/company/{ticker}/financials` | All XBRL facts per year; `?period=FY&years=10&abbreviate=true` (✅ shipped v0.15.0) |

### Discovery & Analysis Endpoints (6)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/company/{ticker}/insights` | Narrative insights (moat, quality, risks) (✅ shipped v0.15.0) |
| GET | `/api/v1/alerts/{ticker}` | Deterministic alerts for a ticker (✅ shipped v0.14.0) |
| GET | `/api/v1/historical-valuation/{ticker}` | Historical P/E + FCF yield table |
| GET | `/api/v1/price/{ticker}` | Current price + market cap + dividend metrics |
| GET | `/api/v1/price/{ticker}/history` | Historical prices; `?start=2025-01-01&end=2025-12-31` |
| GET | `/api/v1/search?q=apple` | Ticker search (uses FDB universe) |

### Screener & Consensus Endpoints (7)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/screener` | Screen with filters; `?universe=sp500&per_max=15&roe_min=12&page=1&page_size=50` |
| GET | `/api/v1/consensus` | Consensus file summary (date, count, meta) |
| GET | `/api/v1/consensus/ranking` | Top companies by consensus score; `?top=20&universe=sp500` |
| GET | `/api/v1/consensus/by-category` | Best per Lynch category |
| GET | `/api/v1/consensus/disagreement` | Disagreement zone (value AVOID vs quality BUY) |
| GET | `/api/v1/consensus/matrix` | Full verdict matrix; `?page=1&page_size=100` |
| GET | `/api/v1/opportunities` | Detected opportunities; `?type=cheap_quality` |

### Portfolio Endpoints (5)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/portfolio` | Full portfolio view (positions, PnL, allocation) |
| POST | `/api/v1/portfolio/positions` | Add position; body: `{ticker, shares, price, thesis}` |
| DELETE | `/api/v1/portfolio/positions/{ticker}` | Remove position (no exit record) |
| POST | `/api/v1/portfolio/positions/{ticker}/exit` | Exit position; body: `{price, date}` |
| GET | `/api/v1/portfolio/performance` | Performance & risk metrics |

### Reports Endpoints (2)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/reports` | List daily reports; `?limit=10` |
| GET | `/api/v1/reports/{date}` | Full report text (markdown) |

---

## B3 — Authentication Design

**Option 1 — Static API Key (Recommended)**

Header: `X-API-Key: <long-random-string>`

- Key stored in server `.env` as `API_KEY`
- Mobile app stores key in Android Keystore / iOS Keychain
- Simple, no login flow, no sessions, no token refresh
- If leaked: rotate `.env` `API_KEY`, restart server, update mobile app
- Middleware validates on every request (except `/health`, `/version`)

**Option 2 — JWT (Overkill)**

- Requires login screen, token storage, refresh logic
- Not needed for single-user personal use

**Rotation strategy:**
1. Generate new key: `openssl rand -hex 32`
2. Update `.env` `API_KEY`
3. Restart FastAPI server (`systemctl restart` or `uvicorn` reload)
4. Update mobile app settings → new key takes effect immediately

---

## B4 — Caching Strategy

The API must NOT hit SEC or Yahoo on every request.

| Data Source | Cache Layer | TTL | Invalidation |
|-------------|-------------|-----|--------------|
| FDB facts (fundamentals, filings, financials) | In-process LRU (or Redis later) | 1 hour | File mtime of consensus JSON / FDB `updated_at` |
| Yahoo prices (current, dividend) | In-process LRU | 5 minutes | Automatic expiry |
| Historical prices | In-process LRU | 15 minutes | Automatic expiry |
| Consensus JSON | In-process + file mtime watch | Until file changes | `watchdog` or mtime check |
| Filings HTML cache (`data/raw/filings/`) | Filesystem (existing) | Permanent | Manual cleanup |
| Screener results | In-process LRU | 10 minutes | N/A (recomputed per request) |

**Cache interface (shared with existing services):**
```python
class Cache:
    async def get(self, key: str) -> Any | None
    async def set(self, key: str, value: Any, ttl: int) -> None
    async def delete(self, key: str) -> None
    async def clear(self) -> None
```

---

## B5 — Deployment Model

### Phase 1: Local Only (Current)
```
┌─────────────────────────────────────────────────────────┐
│  Arch Linux (user's machine)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ CLI          │  │ Streamlit    │  │ FastAPI      │  │
│  │ (direct)     │  │ (direct)     │  │ :8000        │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│         │                │                ▲             │
│         └────────────────┼────────────────┘             │
│                          ▼                              │
│              ┌────────────────────────┐                 │
│              │ Financial-DataBase PG   │                 │
│              └────────────────────────┘                 │
└─────────────────────────────────────────────────────────┘
```

- FastAPI runs on `http://127.0.0.1:8000`
- Exposed to LAN via `http://<arch-lan-ip>:8000`
- Mobile app connects to LAN IP when at home

### Phase 2: Tailscale (Later)
```
Mobile (anywhere) → Tailscale IP:8000 → FastAPI
Mobile (home)     → LAN IP:8000     → FastAPI
```

- Tailscale provides HTTPS via tailnet, device-level auth, no NAT config
- Same FastAPI process; only base URL changes
- Mobile app stores both URLs, prefers LAN when reachable

### Configuration (`.env`)
```bash
API_HOST=127.0.0.1
API_PORT=8000
API_KEY=<long-random-from-openssl-rand-hex-32>
API_ENABLE_DOCS=true
API_CORS_ORIGINS=http://localhost:8501,http://127.0.0.1:8501
```

---

## B6 — Coexistence with Local Usage

### Rules
1. **FastAPI is a new entry point** — `uvicorn backend.api.app:app --reload`
2. **CLI and Streamlit import services directly** — no HTTP hop
3. **FastAPI imports the SAME services** — `PriceService`, `FinancialDatabaseRepository`, `ConsensusService`, etc.
3. **No business logic duplicated** — API handlers are thin wrappers

### Dependency Isolation

This repo has no `pyproject.toml`; dependencies are declared in `Pipfile`.
`fastapi`, `uvicorn[standard]` and `httpx` (the FastAPI TestClient) are already
declared there and installed in `.venv`, so the API adds no new dependency to
install. A future move to a `pyproject.toml` `api` extra — so a base CLI +
Streamlit install does not pull FastAPI — is a packaging follow-up, not a
Phase-1 blocker.

### Data Consistency
- Same FDB PostgreSQL
- Same price snapshot (Yahoo fetched on request)
- Same portfolio JSON (`data/portfolio.json`)
- Same reports directory (`data/reports/`)

### Race Conditions (Portfolio Writes)
- See "Portfolio write invariant" below — it is a design requirement, not an
  implementation detail of Phase 5.

---

## Portfolio write invariant

The portfolio JSON (`data/portfolio.json`) has **three potential writers**:

- the mobile app, via the REST API;
- the local CLI (`python main.py portfolio ...`);
- the Streamlit UI.

If two writers do a read-modify-write simultaneously, one of the changes is
lost (or the JSON is corrupted).

**Invariant:** every write goes through a single service (`PortfolioService`)
that holds an exclusive file lock (`fcntl.flock`) around the whole
read-modify-write block. No consumer writes the JSON directly.

Consequences for the design:

- API handlers for portfolio mutations do NOT read-modify-write the JSON;
  they call `PortfolioService`.
- The CLI already goes through `PortfolioService` (verified 2026-10-07:
  `cli/commands/portfolio.py` uses `build_portfolio_service()`).
- Streamlit add/exit/remove already go through `PortfolioService`, and the
  "Save prices to portfolio" button now also goes through
  `PortfolioService.save_prices()` — the Phase 5 fix (v0.16.0) rerouted
  both `ui/pages/04_portfolio.py` and `ui/pages/01_home.py` through the
  service, so every writer uses the exclusive `fcntl.flock`.
- Reads may stay lock-free when they tolerate a slightly stale snapshot;
  writes must hold the lock.

This invariant is tested and verified (v0.16.0):

- a test that runs two concurrent `PortfolioService` writes from separate
  threads and asserts the final file contains both changes (no lost update);
- a test that verifies the CLI, the API, and the Streamlit UI mutate only
  through the service (not the JSON file directly).
- the lock file (`portfolio.json.lock`) is created next to the JSON and is
  gitignored.

---

## B7 — Files Created

- `docs/api_design.md` — this document
- Referenced by: `docs/api_roadmap.md`, `docs/mobile_app_design.md`