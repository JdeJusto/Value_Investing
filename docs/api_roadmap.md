# API + Mobile App Roadmap

> Roadmap issue: [#27](https://github.com/JdeJusto/Value_Investing/issues/27)

Generated: 2026-10-07

## Goal

Add a REST API (FastAPI) and a native Android app (React Native/Expo) to the
Value Investing platform. The server runs on the user's own Arch Linux machine;
Tailscale provides remote access later. CLI and Streamlit keep working unchanged.

**Non-goals:** multi-user, cloud hosting, web frontend for mobile, iOS-first,
Play Store release.

---

## Phase List

### Phase 1 — FastAPI skeleton + first real endpoint (2-3 days) — done (11d2aaa)
- [x] Verify the API dependencies already declared in `Pipfile` (`fastapi`, `uvicorn[standard]`, `httpx`) — nothing to install
- [x] Replace the stale experimental `backend/api/` package (delete `main.py`, `deps.py`, `v1/`; repoint the two legacy Docker references)
- [x] Create `backend/api/` (`__init__.py`, `app.py`, `auth.py`, `responses.py`, `deps.py`, `routes/system.py`, `routes/company.py`)
- [x] `GET /api/v1/health` and `GET /api/v1/version` (no auth)
- [x] `GET /api/v1/company/{ticker}` — first real endpoint (FDB + `PriceService`, envelope, 404 `TICKER_NOT_FOUND`, fail-closed 503)
- [x] `tests/api/test_app.py` with stubbed services (no DB, no Yahoo)
- [x] `.env.example` updated
- [x] Does NOT touch existing services, CLI or Streamlit

**Testable:** `uvicorn backend.api.app:app --reload` → `/api/v1/health` 200 and `/api/v1/company/AAPL` returns the envelope; wrong key → 401.

### Phase 2 — Read-only company endpoints (2-3 days)
- [ ] `/api/v1/company/{ticker}/methodologies` — 8 verdicts
- [ ] `/api/v1/company/{ticker}/dcf` — DCF valuation
- [ ] `/api/v1/alerts/{ticker}` — per-ticker alert feed (Home fans out per open position, plus Company Detail)
- [ ] Reuse the Phase-1 envelope and error pattern

**Testable:** mobile can render the Methodologies, DCF and Alerts panels.

### Phase 3 — Filings and financials endpoints (2-3 days)
- [ ] `/api/v1/company/{ticker}/filings` — list with form/year filters
- [ ] `/api/v1/company/{ticker}/filing/{accession}/statement/{type}`
- [ ] `/api/v1/company/{ticker}/filing/{accession}/section/{type}`
- [ ] `/api/v1/company/{ticker}/financials` — facts per year
- [ ] `/api/v1/insights/{ticker}`

**Testable:** full company deep-dive via API (Financials + Filings tabs).

### Phase 4 — Screener and consensus endpoints (2 days)
- [ ] `/api/v1/screener` with filters + pagination
- [ ] `/api/v1/consensus`, `/ranking`, `/by-category`, `/disagreement`
- [ ] `/api/v1/search` — ticker/name lookup for the Home search bar

**Testable:** mobile can screen, rank and search.

### Phase 5 — Portfolio endpoints (1-2 days)
- [ ] `GET /api/v1/portfolio`
- [ ] `POST /api/v1/portfolio/positions`
- [ ] `DELETE /api/v1/portfolio/positions/{ticker}`
- [ ] `POST /api/v1/portfolio/positions/{ticker}/exit`
- [ ] `GET /api/v1/portfolio/performance`
- [ ] `PortfolioService` uses `fcntl.flock` for writes.
- [ ] CLI portfolio mutations go through `PortfolioService`.
- [ ] Streamlit portfolio mutations go through `PortfolioService`
      (`save_portfolio_prices` currently writes via the repository directly).
- [ ] Concurrent-write test passes (no lost updates).

**Testable:** mobile can add/exit positions; CLI sees the same data; two concurrent writes keep both changes.

### Phase 6 — Mobile app: skeleton (3-4 days)
- [ ] Expo project init (`npx create-expo-app`)
- [ ] Tab navigation (6 tabs)
- [ ] Settings screen (API URLs, key, theme, demo mode)
- [ ] Home screen with stubbed data
- [ ] React Query + Zustand setup
- [ ] SecureStore for API key

**Testable:** app launches, settings save, health check passes.

### Phase 7 — Mobile app: company detail (3-5 days)
- [ ] Company detail screen with 5 tabs
- [ ] Overview (ratios + verdict summary)
- [ ] Methodologies (8 cards)
- [ ] DCF (value + margin of safety + sensitivity)
- [ ] Financials (yearly table)
- [ ] Filings (list + statement + section)
- [ ] Pull to refresh, skeleton loaders

**Testable:** full company deep-dive on phone.

### Phase 8 — Mobile app: screener, consensus, portfolio (5-7 days)
- [ ] Screener with filter bottom sheet + infinite scroll
- [ ] Consensus (top, by category, disagreement)
- [ ] Portfolio (positions, add/exit/remove, performance)
- [ ] Charts (victory-native)
- [ ] Offline banner + stale-data indicator

**Testable:** all 6 tabs functional.

### Phase 9 — Polish and distribute (2-3 days)
- [ ] Charts polish, transitions
- [ ] EAS Build → APK
- [ ] Keystore stored outside repo
- [ ] Install on device via `adb install`
- [ ] OTA update workflow tested (`eas update`)
- [ ] User documentation for install + update

**Testable:** APK installed and working on the user's phone.

---

## Deferred endpoints

Not consumed by any mobile screen. They stay in `docs/api_design.md` as design
intent and can be added when a real use case appears:

| Endpoint | Why it is deferred |
|----------|--------------------|
| `GET /company/{ticker}/fundamentals` | The Financials tab consumes `/financials` (facts per year); the normalized multi-year series returns if the Overview needs it |
| `GET /historical-valuation/{ticker}` | No mobile screen shows the historical P/E + FCF-yield table |
| `GET /price/{ticker}` | Price and market cap are embedded in `/company/{ticker}` and `/portfolio`; a standalone quote endpoint waits for a pull-to-refresh need |
| `GET /price/{ticker}/history` | No mobile chart is specced to need OHLC history yet |
| `GET /consensus/matrix` | The Consensus screen shows top / by-category / disagreement, not the full verdict matrix |
| `GET /opportunities` | No mobile screen; the CLI/Streamlit opportunity view stays local |
| `GET /reports`, `GET /reports/{date}` | No Reports tab in the mobile app; reports stay local in CLI/Streamlit |

---

## Estimates

| Phase | Estimate |
|-------|----------|
| 1 — FastAPI skeleton + first endpoint | 2-3 days |
| 2 — Company endpoints | 2-3 days |
| 3 — Filings/financials | 2-3 days |
| 4 — Screener/consensus | 2 days |
| 5 — Portfolio | 1-2 days |
| 6 — Mobile skeleton | 3-4 days |
| 7 — Mobile company detail | 3-5 days |
| 8 — Mobile remaining screens | 5-7 days |
| 9 — Polish + distribute | 2-3 days |
| **Total** | **22-32 days (roughly 5-6 weeks part-time)** |

This is a real range, not marketing. Solo development with AI assistance.

---

## Risks and Open Questions

| Risk | Impact | Mitigation |
|------|--------|------------|
| Tailscale setup complexity | Remote access blocked | Document step-by-step; LAN works without it |
| Yahoo rate limits from mobile | Prices fail | Existing `yahoo_health` preflight + cache; degrade gracefully |
| APK size (~40 MB) | Storage annoyance | Acceptable for personal use; Flutter fallback if critical |
| FDB schema changes | API breaks | Version prefix `/api/v1/`; contract tests |
| Portfolio race condition | Lost writes | `fcntl.flock` in Phase 5 |
| Expo SDK upgrade churn | Build breaks | Pin versions; test before upgrade |
| Android version compatibility | App won't install | Target API 34+; test on user's device |
| Mobile app == desktop UI duplication | Divergence | API is the single source; no business logic in app |

**Open questions for the user:**
1. Play Store distribution — yes/no? (Affects Phase 9 scope only)
2. iOS — still a "maybe later"? (Affects Phase 6-8 code, not design)
3. Tailscale — install now or after Phase 5? (Affects testing timeline)

---

## Definition of Done

- [ ] CLI and Streamlit still work exactly as before
- [ ] API runs on the local machine and on Tailscale
- [ ] Mobile app connects via LAN IP and via Tailscale
- [ ] All app-facing endpoints (Phases 1-5) documented in `/docs` (FastAPI autodoc)
- [ ] APK installable on the user's phone
- [ ] Portfolio changes sync between mobile and CLI
- [ ] No duplicate business logic (mobile → API → services)
- [ ] Tests: API ≥ 80% coverage of endpoints; mobile smoke tests
- [ ] Documentation: `docs/api_design.md`, `docs/mobile_app_design.md`, `docs/api_roadmap.md`

---

## Files

- `docs/api_inventory.md` — existing surface inventory
- `docs/api_design.md` — API contract + deployment + coexistence
- `docs/mobile_app_design.md` — mobile architecture
- `docs/api_roadmap.md` — this document