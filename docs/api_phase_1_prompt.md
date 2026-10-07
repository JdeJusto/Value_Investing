# Phase 1 Implementation Prompt — FastAPI Skeleton

> Paste this entire document into a new OpenCode session to start Phase 1.
> Roadmap issue: [#27](https://github.com/JdeJusto/Value_Investing/issues/27)

---

## Task: FastAPI skeleton for the Value Investing API (Phase 1)

Repo: `/home/caudillo/Value_Investing`
Context repo: `/home/caudillo/Financial-DataBase` (read-only — do NOT modify)
Branch: `main`

This is the first implementation phase of the API + mobile app route
(see [#27](https://github.com/JdeJusto/Value_Investing/issues/27)).
The API is **additive**: the CLI and Streamlit UI must keep working exactly
as today. Do NOT modify any existing service, CLI command, or UI page.

### Deliverables

1. **Optional dependency extra** in `pyproject.toml` (do NOT install it in
   this phase's tests unless needed for the TestClient; if installing is
   required to run the new tests, use the `api` extra and document it):

   ```toml
   [project.optional-dependencies]
   api = [
     "fastapi>=0.110",
     "uvicorn[standard]>=0.29",
     "python-multipart>=0.0.9",
   ]
   ```

   Also add the same extra to `Pipfile` if the project manages extras there;
   otherwise document the `pipenv install -e ".[api]"` command in
   `docs/api_design.md` (already referenced there).

2. **New package `backend/api/`** with:

   - `backend/api/__init__.py` — package version constant (e.g.
     `API_VERSION = "v1"`).
   - `backend/api/app.py` — `FastAPI` application factory:
     - `create_app() -> FastAPI`
     - module-level `app = create_app()` for `uvicorn backend.api.app:app`
     - CORS middleware reading `API_CORS_ORIGINS` (comma-separated, default
       `http://localhost:8501`)
     - OpenAPI docs enabled by default, disabled when
       `API_ENABLE_DOCS=false`
     - include a router with the endpoints below
   - `backend/api/auth.py` — API key dependency:
     - `require_api_key` as a FastAPI dependency
     - reads `API_KEY` from the environment
     - validates the `X-API-Key` header with `hmac.compare_digest`
     - raises 401 with the standard error body
       `{"error": {"code": "UNAUTHORIZED", "message": "..."}}`
     - **fail closed**: if `API_KEY` is unset, every protected endpoint
       returns 503 `API_KEY_NOT_CONFIGURED` (never silently open)
     - `/health` and `/api/v1/version` are exempt from auth
   - `backend/api/routes/__init__.py` and
     `backend/api/routes/system.py` — the system endpoints:
     - `GET /health` → `{"data": {"status": "ok"}, "meta": {...}}`
     - `GET /api/v1/version` → API version + app version (read from
       `backend/__init__.py` `__version__`)

3. **Response envelope convention** (documented in
   `docs/api_design.md`; implement a tiny helper in
   `backend/api/responses.py`):
   - success: `{"data": ..., "meta": {"source": ..., "as_of": ISO-8601-UTC, "cache_ttl": int}}`
   - error: `{"error": {"code": "...", "message": "..."}}`

4. **Tests** in `tests/api/test_app.py`:
   - a `TestClient` fixture built from `create_app()`
   - `/health` returns 200 with the envelope and no API key
   - `/api/v1/version` returns 200 with the app version
   - a protected sample endpoint (add `GET /api/v1/whoami` in this phase,
     returning 200 with the key) returns 401 without the header and 200
     with the correct key
   - `API_KEY` unset → protected endpoint returns 503
   - The existing test suite (`pytest tests/unit -q`) must stay green.

5. **`.env.example`** additions:

   ```
   API_HOST=127.0.0.1
   API_PORT=8000
   API_KEY=
   API_ENABLE_DOCS=true
   API_CORS_ORIGINS=http://localhost:8501,http://127.0.0.1:8501
   ```

6. **Run command documented** in `docs/api_design.md` (already present) and
   in the new module docstring:

   ```
   uvicorn backend.api.app:app --reload
   ```

### Constraints

- NO changes to CLI, Streamlit, services, repositories, or methodologies.
- NO new dependency beyond the `api` extra listed above.
- Keep `backend/api/` thin: it calls existing services in later phases; this
  phase only wires the app, auth and system endpoints.
- Type hints everywhere; PEP 8; ruff clean; ruff format clean.
- Each new behavior needs a test. Run `pytest tests/unit -q` and
  `pytest tests/api -q` before committing.
- Commit atomically as `jdejusto` (e.g.
  `feat(api): add FastAPI skeleton with API key auth`).
- Do NOT combine this phase with Phase 2.

### Exit criteria

- [ ] `uvicorn backend.api.app:app --reload` starts and `/health` responds 200.
- [ ] `/api/v1/version` reports the app version.
- [ ] Protected endpoint 401s without `X-API-Key`, 200s with it, 503s when
      `API_KEY` is unset.
- [ ] Existing CLI and Streamlit untouched and green.
- [ ] `pytest tests/unit -q` and `pytest tests/api -q` pass.
- [ ] `ruff check . && ruff format --check .` pass.