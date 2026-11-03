# Analysis visualization audit

**Status:** planning / design input. Read-only audit of the surfaces that
produce and render stock analysis today, plus the reference model that informs
the [scorecard design](scorecard_design.md) and
[roadmap](scorecard_roadmap.md).

**Date:** 2026-10-14 · **Scope:** `backend/`, `ui/`, `mobile/`,
`backend/api/` (audit only — no code changed). Financial-DataBase was read
read-only for peer-coverage numbers and was not modified.

The goal: today's analysis is text- and table-heavy. We want a
Simply-Wall-St-like scorecard — a small set of dimensions, each decomposed
into named, metric-backed rules, with charts and peer comparison.

---

## 1. What already computes scores and reasons (A1)

| Source | What it computes | Output shape | Where it is rendered |
|---|---|---|---|
| `backend/methodologies/*` (8 frameworks) | Independent verdict + optional numeric score, passed/failed rules, red flags, confidence | `MethodologyResult` (`methodology`, `version`, `family`, `verdict`, `score: float \| None`, `metrics`, `reasons`, `red_flags`, `confidence`, `sources`, `failed_rules`, `passed_rules`) | `ui/pages/02_analysis.py` → Methodologies tab; `cli/commands/methodologies*.py`; `backend/api/routes/methodologies.py` |
| `FinancialInsightsService` | Per-metric derived statistics | `InsightsReport` → `MetricInsight` (`metric`, `label`, `latest_value`, `latest_year`, `yoy_change_pct`, `cagr_5y`, `cagr_10y`, `average_5y`, `trend`, `stability`, `direction_changed`, `notes`, `kind`, display strings, raw `series`) | `02_analysis.py` tables; `backend/api/routes/insights.py`; CLI analyze commands |
| `AlertService` | Per-rule alerts with severity + evidence | `AlertsReport` → `Alert` (`rule_id`, `severity` INFO/WARNING/CRITICAL, `title`, `message`, `evidence: dict[str,str]`, `metric_hint`, `period`); `rules_evaluated`, `rules_skipped` | Alerts tab / alerts cache; `backend/api/routes/alerts.py`; `cli/commands/financial_alerts.py` |
| `ConsensusService` | Cross-methodology agreement | `CompanyConsensus` (`buy_count`, `consensus_score = buy − avoid`, `na_count`, `verdicts`) | `ui/pages/06_consensus.py`; `backend/api/routes/consensus.py` |
| DCF (`backend/analytics/valuation/`) | Intrinsic value, margin of safety, verdict, sensitivity rows | DCF result | `02_analysis.py` DCF tab + expanders; `backend/api/routes/dcf.py`; `cli/commands/dcf.py` |
| `backend/analytics/` (`ratios/`, `scoring/`, `screening/`, `interpretation.py`) | Plain ratios and scores (ROE, ROA, ROIC, D/E, margins, Greenblatt, Piotroski-style checks) | Values / rows | Consumed by CLI, UI, API, screener |

**Methodology inventory (8):** `buffett_clark`, `buffett_classic`,
`fisher_quantitative_subset`, `graham`, `graham_dodd`, `greenblatt`,
`lynch_garp`, `marks` — registered in `backend/methodologies/registry.py`.

### Finding 1.1 — the "no composite" invariant is explicit

`backend/methodologies/base.py` documents:

> "a methodology is an independent column, never a contributor to a composite"

This is a **hard constraint on the scorecard design**: the new dimensions
must aggregate **metrics and rules** (from insights / alerts / DCF / ratios),
and the 8 methodology scores must remain **independent, adjacent** columns.
The scorecard must never average methodology scores into a dimension.

### Finding 1.2 — rule status is available, rule *thresholds* are not structured

`MethodologyResult.failed_rules` / `passed_rules` are `list[str]` (labels),
not structured objects. `Alert.evidence` is already a `dict[str,str]` of
formatted numbers. The scorecard's `DimensionRule` therefore needs a small
adapter to attach `value` / `threshold` / `reason` / `sources` — the source
of truth is the existing rules and metrics, not a re-implementation.

---

## 2. How the current UI presents it (A2)

`ui/pages/` (1 851 lines total):

| Page | Lines | Density | Charts today |
|---|---:|---|---|
| `01_home.py` | 175 | Low | none |
| `02_analysis.py` | **816** | **High** — the single company page | 2 (`st.line_chart`: P/E, FCF yield) |
| `03_screener.py` | 307 | Medium | none |
| `04_portfolio.py` | 299 | Medium | `st.line_chart` used |
| `05_reports.py` | 69 | Low | none |
| `06_consensus.py` | 185 | Medium | none |

`02_analysis.py` tabs: **Overview, Methodologies, DCF, Historical, Filings,
Financials, Raw** (7). The page is dominated by `st.dataframe`,
`st.expander`, and `st.metric`. Only two line charts exist, both inside the
Historical tab (P/E and FCF-yield series). It already has a **Disagreement**
section (around line 481) that the scorecard can reuse conceptually.

### Finding 2.1 — dense, table-first

There is no per-dimension summary, no radar, no peer panel, and no
"explain this score" affordance. Everything is a table the reader must
interpret.

---

## 3. Charting primitives available today (A3)

| Surface | Installed | Radar / polar capable? |
|---|---|---|
| Streamlit (Python) | **`altair`** (ships with Streamlit). `matplotlib` **absent**; `plotly` **absent**. | Altair has no polar/radar mark → radar needs `plotly` (new dependency) or a dependency-free SVG. |
| Mobile (Expo/RN) | `react-native-svg` present (referenced in jest config). **No** `victory-native`, `react-native-chart-kit`, or Skia. | Hand-drawn SVG radar is feasible with **zero** new dependencies. |

Verified with `.venv/bin/python -c "importlib.util.find_spec(...)"` and by
grepping `Pipfile.lock` (0 matches for `matplotlib`/`plotly`, 1 for `altair`).

**Decision recorded:** Streamlit will use **plotly** for the radar (Phase 4,
a separately approved dependency change). Mobile will stay on
`react-native-svg` (no new dependency). Both choices are frozen in the
[design](scorecard_design.md); this session adds no dependencies.

---

## 4. Mobile analysis screens (A4)

`mobile/app/company/[ticker].tsx` (191 lines) renders a horizontal segmented
control with **5 tabs**: **Overview, Methodologies, DCF, Financials,
Filings** (components `OverviewTab`, `MethodologiesTab`, `DCFTab`,
`FinancialsTab`, `FilingsTab`).

- **Overview** — a `rows.map` label/value list (metric rows) — table-ish.
- **Methodologies, DCF, Financials, Filings** — data-rendering tabs fed by
  React Query.

### Finding 4.1 — the mobile Overview is the natural scorecard host

It is currently a flat key/value list. A scorecard (radar + cards) would
replace the top of that tab while keeping the existing rows below it, with no
new dependencies.

---

## 5. Peer-comparison data availability (read-only FDB check)

Measured against the live Financial-DataBase (read-only):

| Metric | Value |
|---|---|
| Companies total | 8 023 |
| With `sector` | 5 912 (**73.7 %**) |
| With `industry` | 5 912 (73.7 %) |
| Sector buckets with ≥ 10 companies | **11** (Financial Services 1 425, Healthcare 1 052, Technology 791, Industrials 718, Consumer Cyclical 531, Basic Materials 289, Real Estate 255, Energy 254, Communication Services 247, Consumer Defensive 243, Utilities 107) |
| Industry buckets with ≥ 10 companies | **121** |

**Conclusion:** industry-level peers (with sector fallback) are viable for the
covered ~74 % of companies; the remaining ~26 % lack sector/industry and must
degrade to "no peer comparison" rather than a wrong one.

---

## 6. Gaps relative to the Simply Wall St experience

| Capability | SWS | This project today |
|---|---|---|
| Small set of named, per-dimension scores | 5 axes × 6 checks | ❌ (8 independent methodologies, no dimensions) |
| Each score decomposes into named checks with values + thresholds | ✅ | ⚠️ rules exist but the score→rule link is a string list |
| Radar ("snowflake") summary | ✅ | ❌ |
| Historical charts per dimension | ✅ | ⚠️ 2 charts total |
| Peer / industry comparison | ✅ | ❌ |
| "Missing ≠ bad" (data-quality gate) | ✅ (subset of checks skipped) | ⚠️ alerts already skip on missing data; no dimension-level rule |
| Recomputable by the user from shown inputs | partial | ✅ philosophy already ("disagreement is information") |

---

## 7. Reference model — Simply Wall St (Phase B, public sources only)

**Method:** public documentation and an open-source specification only. No
scraping, no automated access, no data downloaded, no visual assets
reproduced. Where the public record is thin, that is stated rather than
guessed.

### 7.1 The six axes?

Public documentation describes **five** assessment criteria, not six:

- **Value**, **Future performance**, **Past performance**, **Health**,
  **Dividends** — the "Snowflake".

Some material in the wild (and the brief for this audit) also names a
**Management** axis. The public Snowflake documentation and the vendor's own
open-source model spec list **five** axes; no public source corroborates a
distinct sixth "Management" axis. **Finding:** the "six axes" premise is not
supported by public sources — the reference is a **5-axis** model with **30
binary checks**. (This only matters as background; our dimensions are our own,
not a copy.)

### 7.2 How is each axis scored?

Each axis runs **6 individual pass/fail checks**. A passed check = `1`, a
failed check = `0`; the six are summed to a **score out of 6**. That per-axis
score sets (a) how far the snowflake's boundary extends on that axis and
(b) the colour of the shape (red → orange → yellow → green as more checks
pass overall). So: **not 1–10, not percentile — a small integer out of a fixed
check count.** Missing inputs cause checks to be skipped rather than failed.

### 7.3 What is shown when an axis is clicked?

The per-axis checks, each with the label of the rule and the numbers behind
it (e.g. "is the share price ≥ 20 % below DCF fair value?", "is the dividend
covered by earnings?"). The valuation area additionally splits into **2
intrinsic checks** (price vs DCF fair value, and vs a ≥ 20 % discount) and **4
relative/analyst checks** (peer multiples, analyst target). The published
model spec is unusually explicit: it documents the literal thresholds per
check.

### 7.4 How is a company compared to its industry?

Via **relative valuation multiples** (price vs peer multiples) and a peer-set
comparison inside the valuation checks, plus industry context in the report.
It is a peer *reference*, not a full percentile dashboard.

### 7.5 Which charts appear on the individual stock page?

Broadly: an earnings-and-revenue history, a fair-value-vs-price view,
dividend history/sustainability, and balance-sheet strength indicators. We
describe the **pattern** (per-area charts behind the score) and do **not**
copy the visuals.

### 7.6 Design principles extracted (not pixels)

1. **Decomposable.** Every score is the sum of named, individually readable
   checks — never an opaque number.
2. **Metric-backed.** Each check is a metric + a value + a threshold, so a
   reader can disagree with one check without discarding the whole score.
3. **Trend + comparison.** A score is shown with its history and against
   peers/sector, not in isolation.
4. **Small set of dimensions, not one composite.** The shape is the point:
   a company can be strong on some axes and weak on others.
5. **Missing ≠ bad.** A check with no data is skipped/flagged, never scored 0.
6. **Recomputable.** A motivated user can rebuild the score from the shown
   inputs.

### 7.7 What this project will and will not copy

**Will adopt (principles):** decomposable dimensions, metric+threshold checks,
trend and peer comparison, small integer scores per dimension, missing-data
gating, user-recomputability.

**Will not copy:** their exact axes or check list; their 1–6 scale or colours;
their fair-value methodology; any visual asset; their commercial data. Our
dimensions map to **our** existing metrics, rules, alerts, and DCF, and we
deliberately **keep the 8 methodologies independent** (see Finding 1.1) rather
than collapsing everything into one shape.

### 7.8 Constraints confirmed (B3)

1. **No LLM.** All reason strings are templated from values; deterministic.
2. **Prices never persisted** — prices are fetched once per build and cached in
   memory only.
3. **Two frontends** (Streamlit + React Native/Expo) share one service.
4. **Aggregate and explain, don't replace.** The scorecard is a presentation
   layer over existing scores/rules.
5. **No master score.** `overall` is a label; cross-dimension disagreement is
   surfaced, not averaged away.

### Sources consulted

- Simply Wall St Help Center — *How does the Snowflake work*:
  <https://support.simplywall.st/hc/en-us/articles/360001740916-How-does-the-Snowflake-work>
- Simply Wall St — *Company Analysis Model* (public open-source spec):
  <https://github.com/SimplyWallSt/Company-Analysis-Model/blob/master/MODEL.markdown>
- Simply Wall St Help Center — *Understanding the Valuation section*:
  <https://support.simplywall.st/hc/en-us/articles/4751563581071-Understanding-the-Valuation-section-in-the-company-report>
- Third-party review (Snowflake mechanics, 5 axes):
  <https://helmterminal.dev/blog/simply-wall-st-review>
- Third-party review (feature summary):
  <https://stockunlock.com/simply-wall-st-review.html>

> This is background research to extract principles, **not** a spec to copy.
> No SWS content, asset, or data is reproduced.
