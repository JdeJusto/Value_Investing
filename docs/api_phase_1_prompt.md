# Phase 1 Implementation Prompt — FastAPI Skeleton + First Real Endpoint

> Paste this entire document into a new OpenCode session to start Phase 1.
> Roadmap issue: [#27](https://github.com/JdeJusto/Value_Investing/issues/27)
>
> Revised 2026-10-07: Phase 1 now ships one real endpoint
> (`/api/v1/company/{ticker}`) so the full pattern — auth → service →
> serialization → response envelope → error handling — is validated before it
> is replicated across the remaining endpoints. It also replaces the stale
> experimental API package already in the repo.

---

## Task: FastAPI skeleton + first real endpoint (Phase 1)

Repo: `/home/caudillo/Value_Investing`
Context repo: `/home/caudillo/Financial-DataBase` (read-only — do NOT modify)
Branch: `main`

This is the first implementation phase of the API + mobile app route
(see [#27](https://github.com/JdeJusto/Value_Investing/issues/27)).
The API is **additive**: the CLI and Streamlit UI must keep working exactly
as today. Do NOT modify any existing service, CLI command, or UI page.

### Repository context — replace the stale experimental API

`backend/api/` currently holds a dormant experimental API from an earlier
attempt: `main.py`, `deps.py` and `v1/{auth,companies,screener,portfolios,alerts,watchlists}.py`
(commits `665b5d2`, `52b16cb`). It uses a different architecture (JWT login,
SQLAlchemy user models) and nothing outside that cluster imports it — the only
references are two legacy Docker files.

Phase 1 **replaces** it:

- delete `backend/api/main.py`, `backend/api/deps.py` and `backend/api/v1/`;
- keep the package directory and rewrite `backend/api/__init__.py`;
- repoint the two legacy references from `backend.api.main:app` to
  `backend.api.app:app` (`docker-compose.yml` line ~33, `Dockerfile.backend`
  line ~18) so nothing points at deleted code;
- leave `backend/core/`, `backend/models/`, `backend/schemas/` and
  `backend/tasks/` untouched — `alembic/env.py` and `backend/tasks` still
  import them; their removal is a separate cleanup follow-up.

Before deleting, re-run
`grep -rn "backend\.api" --include="*.py" . | grep -v backend/api` and stop
if any live import appears.

### Deliverables

1. **Dependencies.** This repo has no `pyproject.toml`; dependencies live in
   `Pipfile`, which already declares `fastapi`, `uvicorn[standard]` and
   `httpx` (the FastAPI TestClient). Verify they import:
   `.venv/bin/python -c "import fastapi, uvicorn, httpx, pydantic"`.
   Do NOT add dependencies. (A `pyproject.toml` `api` extra is a future
   packaging follow-up — see `docs/api_design.md`, "Dependency Isolation".)

2. **New thin package `backend/api/`** — orchestration only, no business
   logic:
   - `backend/api/__init__.py` — `API_VERSION = "v1"`.
   - `backend/api/responses.py` — envelope helpers:
     - `ok(data, source="mixed", cache_ttl=300)` →
       `{"data": ..., "meta": {"source": ..., "as_of": <ISO-8601 UTC "Z">, "cache_ttl": ...}}`
     - `fail(status_code, code, message)` → `JSONResponse` with
       `{"error": {"code": ..., "message": ...}}`
   - `backend/api/auth.py` — `require_api_key` FastAPI dependency:
     - reads `API_KEY` from the environment **at request time** (so tests can
       monkeypatch it);
     - compares with `hmac.compare_digest` against the `X-API-Key` header;
     - missing or wrong key → 401 `UNAUTHORIZED`;
     - `API_KEY` unset → 503 `API_KEY_NOT_CONFIGURED` (fail closed).
   - `backend/api/deps.py` — injectable service accessors:
     - `get_repository()` → `build_financial_repository()` (from `backend.app.cli`);
     - `get_price_service()` → a shared `PriceService`;
     - both overridable via `app.dependency_overrides` in tests.
   - `backend/api/routes/system.py`:
     - `GET /api/v1/health` → `ok({"status": "ok"}, source="internal", cache_ttl=0)`;
       no auth.
     - `GET /api/v1/version` → `ok({"api_version": API_VERSION, "app_version": backend.__version__}, source="internal", cache_ttl=0)`;
       no auth.
   - `backend/api/routes/company.py` — **the first real endpoint**:
     - `GET /api/v1/company/{ticker}` (protected).
     - Flow: upper-case the ticker → `repository.get_best_available(ticker)`;
       empty list → 404 `TICKER_NOT_FOUND`; take the newest row for
       `sector` / `currency` / `fiscal_year`; `repository.get_company_name(ticker)`;
       `price = price_service.get_current_price(ticker)`;
       `market_cap = price_service.get_market_cap(ticker)`.
     - Yahoo failure degrades to `null` values — never a 500. An unexpected
       service exception maps to 503 `SERVICE_UNAVAILABLE` with the standard
       error body (no tracebacks).
     - Response:
       ```json
       {"data": {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology",
                  "cik": "0000320193", "price": 336.67,
                  "market_cap": 4950000000000.0, "currency": "USD",
                  "fiscal_year": 2025},
        "meta": {"source": "mixed", "as_of": "2026-10-07T18:30:00Z", "cache_ttl": 300}}
       ```
     - Never persist a price.
   - `backend/api/app.py` — `create_app()` factory:
     - module-level `app = create_app()` (`uvicorn backend.api.app:app`);
     - CORS from `API_CORS_ORIGINS` (default `http://localhost:8501`);
     - OpenAPI docs on by default, disabled when `API_ENABLE_DOCS=false`;
     - includes the routers above.

3. **Tests `tests/api/test_app.py`** — must pass WITHOUT the real database or
   Yahoo. Build a `TestClient` from `create_app()`, override
   `get_repository` / `get_price_service` with stubs via
   `app.dependency_overrides`, and set `API_KEY` per test with
   `monkeypatch.setenv`:
   - `/api/v1/health` → 200 with the envelope, no API key needed;
   - `/api/v1/version` → 200, `app_version == backend.__version__`;
   - `/api/v1/company/AAPL` → 200 with ticker/name/sector/price/market_cap;
   - `/api/v1/company/ZZZZ` (stub returns no rows) → 404 `TICKER_NOT_FOUND`;
   - request without `X-API-Key` → 401 `UNAUTHORIZED`;
   - request with a wrong key → 401 `UNAUTHORIZED`;
   - `API_KEY` unset → 503 `API_KEY_NOT_CONFIGURED`;
   - `pytest tests/unit -q` stays green.

4. **`.env.example`** additions:
   ```
   API_HOST=127.0.0.1
   API_PORT=8000
   API_KEY=
   API_ENABLE_DOCS=true
   API_CORS_ORIGINS=http://localhost:8501,http://127.0.0.1:8501
   ```

5. **Run command** documented in the module docstring:
   ```
   uvicorn backend.api.app:app --reload
   ```

### Why a real endpoint in Phase 1

`/api/v1/company/{ticker}` exercises the whole pattern in one place: the
API-key dependency, a service call, the `data`/`meta` envelope, the
`source`/`as_of` metadata, null-degradation for prices, and the 404/503 error
bodies. If the pattern is wrong, it is wrong once — not across every endpoint
that follows.

### Constraints

- NO changes to CLI, Streamlit, services, repositories, or methodologies.
- NO new dependency beyond what `Pipfile` already declares.
- Keep `backend/api/` thin: no SQL, no Yahoo calls outside `PriceService`, no
  analysis logic.
- Type hints everywhere; PEP 8; `ruff check .` and `ruff format --check .`
  clean.
- Each new behavior gets a test; run `pytest tests/unit -q` and
  `pytest tests/api -q` before committing.
- Commit atomically as `jdejusto`
  (e.g. `feat(api): add FastAPI skeleton with API key auth and company endpoint`).
- Do NOT combine this phase with Phase 2.

### Exit criteria

- [ ] `uvicorn backend.api.app:app --reload` starts; `/api/v1/health` → 200.
- [ ] `/api/v1/version` reports `backend.__version__`.
- [ ] `/api/v1/company/AAPL` returns the envelope with price + market cap.
- [ ] Unknown ticker → 404 `TICKER_NOT_FOUND`.
- [ ] Missing/wrong `X-API-Key` → 401; `API_KEY` unset → 503 (fail closed).
- [ ] Stale `backend/api` modules removed; Docker files repointed; CLI and
      Streamlit untouched and green.
- [ ] `pytest tests/unit -q` and `pytest tests/api -q` pass.
- [ ] `ruff check . && ruff format --check .` pass.