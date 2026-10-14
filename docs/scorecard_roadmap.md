# Scorecard roadmap — interactive, visual stock analysis

**Status:** Phases 1–2 shipped (backend + API/CLI); Phase 3 shipped in
Streamlit (text only). Phases 4–7 planned. Implements the
[scorecard design](scorecard_design.md) on top of the current surfaces
described in the [analysis visualization audit](analysis_visualization_audit.md).

**Principles for sequencing:** each phase is independently shippable; backend
first (so both frontends share one contract); no phase adds a dependency
except Phase 4, which adds **plotly** in a *separate, explicitly-approved*
commit. No phase changes existing scoring behavior — the scorecard is a
presentation layer.

All commits are authored `jdejusto`; no force-push; no tag rewrites;
Financial-DataBase is read-only.

---

## Phase overview

| # | Phase | Est. | Depends on |
|---|---|---:|---|
| 1 | Scorecard domain + `ScorecardService` (backend only) | 1.5–2 d | — |
| 2 | API endpoint + CLI command | 0.5–1 d | 1 |
| 3 | Streamlit Scorecard tab (cards, no charts) | 1–1.5 d | 1 |
| 4 | Radar + 4 charts (adds **plotly**) | 1–1.5 d | 3 |
| 5 | Peer percentiles (script + artifact + UI) | 1.5–2 d | 1 |
| 6 | Mobile parity | 2–3 d | 1, 2 |
| 7 | Polish, interactions, exports, docs | 1–2 d | 3–6 |

**Total: ~9–13 working days.** Phases 2, 3 and 5 can run in parallel after
Phase 1.

---

## Phase 1 — Scorecard domain + service (backend only)

**Deliverable.** `DimensionRule`, `DimensionScore`, `Scorecard` and
`ScorecardService.build(ticker, period="FY")`, wired to
`FinancialsViewService` → `FinancialInsightsService` / `AlertService` / DCF /
`backend/analytics`, with the 6 dimensions and default thresholds from the
design.

**Dependencies.** None.

**Acceptance criteria.**

- `ScorecardService().build("AAPL")` returns a valid Scorecard with exactly 6
  dimensions in fixed order.
- Every dimension `score` **recomputes** from its rules via the §2 formula.
- A dimension with < 2 evaluable rules is `INSUFFICIENT` (never 0).
- Two consecutive builds of the same ticker are **byte-identical** (no clock,
  no randomness).
- No price is persisted (the `prices` table row count is unchanged).

**Tests.** Unit: rule→status mapping per dimension; score formula; the
<2-evaluable → INSUFFICIENT rule; determinism; a missing-metric case degrades
one rule, not the dimension. Integration: build for 5 tickers incl. one
non-payer and one bank/insurer.

---

## Phase 2 — API + CLI exposure

**Shipped.** API `007fc9a` (`feat(api): expose GET /company/{ticker}/scorecard`);
CLI `ea6c5f0` (`feat(cli): add scorecard command with rich rendering and json
output`). Both return the frozen Phase 1 `Scorecard.to_dict()` verbatim — the
API and the CLI add no computation of their own.

**Deliverable.** `GET /api/v1/company/{ticker}/scorecard` (existing
`{ok, data}` envelope, errors via `fail()`), and `./vi scorecard AAPL
[--json] [--period FY]`.

**Dependencies.** Phase 1.

**Acceptance criteria.**

- Endpoint returns `200` + a schema-valid Scorecard for `AAPL`; `404` for an
  unknown ticker; `500` never leaks internals (covered by the B3 handler).
- CLI prints a readable text scorecard by default and the raw payload with
  `--json`; exit code 0 on success, non-zero on unknown ticker.

**Tests.** API test via `TestClient` (happy path + unknown ticker); CLI test
(stdout shape); payload round-trip (serialize/deserialize stability).

---

## Phase 3 — Streamlit Scorecard tab (text only)

**Status:** shipped ✅.

**Shipped.** Disagreement gate `1203808` (`fix(scorecard): detect
disagreements at (>=7, <=3) pair thresholds`); the tab `676409d`
(`feat(ui): add Scorecard tab with dimension cards and rule tables`); tests
`32f3eba` (`test(ui): cover the Scorecard tab cards, rule tables and panels`).
The tab renders the frozen `Scorecard.to_dict()` verbatim through
`ui.services.load_scorecard` (ttl 3600) — no view-side math. See
[design §7 → Shipped in Streamlit](scorecard_design.md#shipped-in-streamlit-phase-3).

**Deliverable.** A new **Scorecard** tab in `ui/pages/02_analysis.py`,
**between `Methodologies` and `DCF`** (not default): header, one card per
dimension with the rules table, the **disagreement panel**, and the
financial-company note. Charts are **not** part of this phase.

**Dependencies.** Phase 1 (Phase 2 optional).

**Acceptance criteria.**

- The tab renders for a warm-cache ticker in **< 3 s** (measured ≈ 0.5 s;
  cold ≈ 7.5 s).
- Every displayed number traces to an existing service (no view-side math).
- The tab is present but **not** the default; the new order is Overview ·
  Methodologies · **Scorecard** · DCF · Historical · Filings · Financials · Raw.

**Tests.** Streamlit `AppTest`: the tab sits between Methodologies and DCF,
six cards render with score + verdict, the rule table has the expected columns,
an `INSUFFICIENT` dimension renders `—` (never 0), the disagreement panel
appears only when non-empty, and the data-quality badge/error path render.
Phase A adds the disagreement-gate unit tests in `test_scorecard_service.py`.

**Deviations from the original sketch.** No `altair` bar placeholder and no
JSON/Markdown export shipped: charts are deferred to Phase 4 and export to
Phase 7. Text-only cards are the deliberate deliverable here.

---

## Phase 4 — Radar + charts (adds plotly)

**Deliverable.** Add **plotly** to `Pipfile`/`Pipfile.lock` in a **separate
dependency commit**, then the 6-axis radar (`go.Scatterpolar`, 0–10) and the
4 charts (revenue & net income bars; margin lines; ROE & ROIC lines; DCF value
vs price). Axis-click expands the matching card.

**Dependencies.** Phase 3; explicit approval to add plotly (Streamlit-only).

**Acceptance criteria.**

- Radar renders 6 axes with the dimension scores; the shape degrades to the
  altair-bar fallback if plotly import fails.
- Axis-click expands the matching card (or the `st.selectbox` fallback works).
- Charts render with **no current price** (valuation segment shows
  "price unavailable" instead of erroring).

**Tests.** `AppTest` smoke with plotly present; a unit test on the radar
axis/radius data shaping; a test that the tab degrades cleanly when the price
service returns `None`.

---

## Phase 5 — Peer percentiles

**Deliverable.** `scripts/build_peer_stats.py` producing
`data/peer_stats/<level>_<slug>.json` (+ `_index.json`) on a **weekly
(Sunday)** schedule; a `.gitignore` entry for `data/peer_stats/`; the
`pe_vs_peers` valuation rule and a peer column in the cards plus the peer
table.

**Dependencies.** Phase 1. Reads Financial-DataBase read-only.

**Acceptance criteria.**

- The script regenerates the artifact deterministically for a fixed day.
- Peer gating is exact: industry → sector fallback; **< 10 peers → skipped**
  with a `notes` entry, no percentile.
- Percentile ∈ [0, 1]; a company equal to the median reads ~0.5.
- The artifact is git-ignored (local build product), matching
  `data/reports/daily_*.md`.

**Tests.** Unit: percentile from stored quantiles (incl. ties and clamped
edges); artifact schema validation; <10-member gating. Integration: optional
live-FDB test that **skips** when the DB is unavailable.

---

## Phase 5.5 note — `.gitignore`

Measured: `data/` is *selectively* ignored (`data/logs/*`, `data/reports/daily_*.md`,
…) and `data/peer_stats/` is **not** ignored today. Phase 5 adds
`data/peer_stats/` to `.gitignore` so peer stats stay a local build product.

---

## Phase 6 — Mobile parity

**Deliverable.** A **Scorecard** tab in `mobile/app/company/[ticker].tsx`
(5 → 6 tabs): radar hand-drawn with the already-present `react-native-svg`,
expandable dimension cards, and `react-native-svg` charts. The Overview tab
gains a compact radar + overall chip.

**Dependencies.** Phase 1 (and Phase 2 payload).

**Acceptance criteria.**

- The tab renders for `AAPL` on device with **no new native dependency**.
- The payload maps 1:1 to the backend `Scorecard` (no mobile-side scoring).
- With no network, the last cached payload renders (existing query cache).

**Tests.** Jest: radar point math (`angle → x/y`), status→color mapping,
payload mapping. No snapshot of visuals.

---

## Phase 7 — Polish

**Deliverable.** The full interaction set (design §8): radar-click, card/rule
expansion, absolute↔sector toggle, FY toggle (quarterly deferred), JSON +
Markdown export. Docs: `docs/` index rows, a `docs/runbook_daily.md` note, and
a README mention.

**Dependencies.** Phases 3–6.

**Acceptance criteria.**

- Every interaction in design §8 works or has its documented fallback.
- No regression in the existing test suite or the screener outputs.
- Docs updated; no code-only feature ships undocumented.

**Tests.** `AppTest` for the interactive paths; docs lint/consistency tests.

---

## Risks and unknowns

| Risk | Evidence | Mitigation |
|---|---|---|
| `plotly` is a new dependency | not in `Pipfile.lock` (0 matches) | Phase 4, separate approved commit; altair-bar fallback keeps Phase 3 shippable |
| ROIC / interest coverage / current ratio not in insights | insights metric keys lack them | source from `backend/analytics/ratios` or mark `INSUFFICIENT`; **open question 2** |
| Sector/industry availability | 73.7 % of companies have it | industry→sector→skip gating; note when absent |
| Small peer buckets | 11 sectors ≥ 10; 121 industries ≥ 10 | `n ≥ 10` gate; skip + note below it |
| Added latency per ticker | DCF + insights already run on the analysis page | header-first render; reuse existing analysis/scorecard cache; incremental peer/DCF |
| Scorecard contradicting methodologies | design keeps methodologies independent | shared thresholds (D/E, interest coverage) documented; no averaging |
| Peer artifact staleness | weekly regeneration | artifact carries `generated`; UI labels "as of <date>" |

---

## Open questions (need a decision before/within a phase)

1. **plotly version pin** for Phase 4.
2. **Ratio source:** do `ROIC`, interest coverage and current ratio exist in
   `backend/analytics/ratios`, or should those rules start `INSUFFICIENT`?
2. **Sector/industry exposure** — confirm `CompanyRepository` returns
   `sector`/`industry` for a ticker.
3. **Valuation peer rule** — soft dependency (skipped without the artifact) or
   peer-free until Phase 5?
4. **Scorecard caching** — reuse `data/cache/analysis/` or add
   `data/cache/scorecard/`?

---

## Publishing

A **new** GitHub issue — *"Roadmap: interactive, visual stock analysis
(scorecard)"* — with the design summary, links to the three docs, and the open
questions. It cross-links issue #27 (*"Roadmap: REST API + native Android
app"*), which is the API/Android delivery track; the scorecard is a distinct
feature, so it gets its own thread rather than a comment on #27.
