# Scorecard design — interactive, visual stock analysis

**Status:** design / planning. No code in this document is implemented; this
is the contract the [roadmap](scorecard_roadmap.md) implements.

**Inputs:** [Analysis visualization audit](analysis_visualization_audit.md).
**Decisions locked with the maintainer (2026-10-14):** dimensions = Growth,
Profitability, Financial Health, Valuation, Shareholder Returns,
Management/Moat; methodology scores stay independent; radar via **plotly**
(Phase 4); peers = industry → sector fallback; new opt-in Streamlit tab,
mobile later; **no master score**.

---

## 0. Purpose and non-goals

**Purpose.** Turn the existing text/table analysis into a small set of
**decomposable dimensions** — each with a score, the named rules behind it,
the metrics and thresholds that fired, a trend, and a peer comparison — so a
reader can see *why* a company scores as it does and disagree with one rule
without discarding the whole picture.

**Non-goals.**

- No new financial computation. Every value comes from
  `FinancialInsightsService`, `AlertService`, the DCF, `backend/analytics/`,
  or the methodology registry. The only new number is the **peer
  percentile**, which is necessary and is built from a precomputed artifact.
- No LLM and no generated prose. Reason strings are templated from values.
- **No numeric master score.** `overall` is a label; cross-dimension
  disagreement is surfaced, never averaged.
- The 8 methodologies are **not** folded into dimensions (see audit Finding
  1.1: "a methodology is an independent column, never a contributor to a
  composite").

---

## 1. Dimensions

Six dimensions, each answering a different question. Thresholds are **first
defaults, explicitly tunable** in Phase 1 and validated against the universe.
`INSUFFICIENT` is a first-class status: missing data is never scored 0.

Legend: **PASS = 2**, **WATCH = 1**, **FAIL = 0**, **INSUFFICIENT = skipped**.

### 1.1 Growth — "Is the business getting bigger?"

| Rule | Metric source | PASS | WATCH | FAIL |
|---|---|---|---|---|
| `revenue_cagr_5y` | insights `revenue.cagr_5y` | ≥ 10 % | 3–10 % | < 3 % |
| `eps_or_ni_cagr_5y` | insights `eps_diluted.cagr_5y` (else `net_income`) | ≥ 10 % | 3–10 % | < 3 % |
| `fcf_cagr_5y` | insights `free_cash_flow` series CAGR | ≥ 8 % | 0–8 % | < 0 % |
| `revenue_trend` | insights `revenue.trend` / `stability` | growing & stable | mixed | declining |
| `revenue_decline_alert` | `AlertService` `revenue_decline` | no alert | — | alert fires |

Methodologies shown **as context only** (not scored): `lynch_garp`,
`fisher_quantitative_subset`, `buffett_clark`.

### 1.2 Profitability — "Does it earn good returns on its money?"

| Rule | Metric source | PASS | WATCH | FAIL |
|---|---|---|---|---|
| `net_margin` | insights `net_margin` | ≥ 10 % | 3–10 % | < 3 % |
| `roe` | insights `roe` | ≥ 15 % | 8–15 % | < 8 % |
| `roic` | `backend/analytics/ratios` (ROIC) | ≥ 10 % | 6–10 % | < 6 % |
| `gross_margin_stability` | insights `gross_margin.stability` | stable | volatile | sharply declining |
| `fcf_conversion` | insights `fcf_conversion` | ≥ 80 % | 50–80 % | < 50 % |
| `margin_collapse_alert` | alerts `margin_collapse`, `earnings_quality` | no alert | `earnings_quality` | `margin_collapse` |

Context methodologies: `buffett_classic`, `greenblatt`, `marks`.

### 1.3 Financial Health — "Can it service its debts?"

| Rule | Metric source | PASS | WATCH | FAIL |
|---|---|---|---|---|
| `debt_to_equity` | insights `debt_to_equity` | ≤ 0.5 | 0.5–1.5 | > 1.5 |
| `interest_coverage` | `backend/analytics/ratios` | ≥ 6× | 3–6× | < 3× |
| `current_ratio` | `backend/analytics/ratios` | ≥ 1.5 | 1.0–1.5 | < 1.0 |
| `fcf_positive` | insights `free_cash_flow` latest | > 0 | — | < 0 |
| `liquidity_&_debt_alerts` | alerts `low_cash_runway` (CRITICAL), `debt_spike`, `negative_fcf_streak` | none | `inventory_buildup` | any of the three |

The D/E ≥ 1.5 and interest-coverage < 3× thresholds are chosen to **match the
existing screener cap** (`LEVERAGED_RANK_CAP`, `docs/scoring_methodology.md`)
so the scorecard cannot contradict the screener.

### 1.4 Valuation — "Is the price reasonable?"

| Rule | Metric source | PASS | WATCH | FAIL |
|---|---|---|---|---|
| `dcf_margin_of_safety` | DCF result vs market cap | ≥ 20 % | 0–20 % | < 0 % |
| `pe_vs_peers` | historical-valuation P/E vs peer artifact | ≤ peer median | ≤ peer p75 | > peer p75 |
| `fcf_yield` | `HistoricalValuationService` | ≥ 4 % | 2–4 % | < 2 % |
| `earnings_sign` | insights `net_income` latest | > 0 | — | ≤ 0 |

Depends on the **one** price fetch (current price + market cap; never
persisted) and on the peer artifact. If peers are unavailable, `pe_vs_peers`
is `INSUFFICIENT`, not FAIL.

### 1.5 Shareholder Returns — "Does the owner get paid?"

| Rule | Metric source | PASS | WATCH | FAIL |
|---|---|---|---|---|
| `share_dilution` | insights `diluted_shares` series | ≤ 0 %/yr (flat/buyback) | 0–1 %/yr | > 1 %/yr |
| `per_share_accretion` | EPS CAGR − share-count CAGR | ≥ 0 | −1–0 % | < −1 % |
| `dividend_growth` | insights `dividends_paid` (payers only) | growing/stable | declining | cut |
| `dividend_cover` | FCF vs dividend (payers only) | ≥ 2× | 1–2× | < 1× |
| `dividend_cut_alert` | alerts `dividend_cut` | no alert | — | alert fires |

`share_dilution` + `per_share_accretion` apply to **everyone**, so a
non-payer still has ≥ 2 evaluable rules (never INSUFFICIENT merely for not
paying a dividend). Payer-only rules are `INSUFFICIENT` for non-payers.

### 1.6 Management/Moat — "Will the returns last?" (quantitative only)

| Rule | Metric source | PASS | WATCH | FAIL |
|---|---|---|---|---|
| `roic_persistence` | ROIC ≥ 10 % in N of last 5 years | ≥ 5 of 5 | 3–4 | ≤ 2 |
| `gross_margin_stability` | insights `gross_margin.stability` | stable | volatile | declining |
| `management_red_flags` | `buffett_clark` `red_flags` count | 0 | 1 | ≥ 2 |

No qualitative text, no LLM. Dilution lives only in Shareholder Returns, so
the two dimensions do not double-count the same signal.

---

## 2. Scoring model

For each dimension:

```
evaluable = rules with status in {PASS, WATCH, FAIL}      # INSUFFICIENT excluded
points    = Σ (PASS:2, WATCH:1, FAIL:0)
if len(evaluable) < 2:
    score = None            # dimension verdict = INSUFFICIENT
else:
    score = round(10 * points / (2 * len(evaluable)))     # 0..10
```

**Dimension verdict bands** (from `score`):

| `score` | Verdict |
|---|---|
| ≥ 8 | **Strong** |
| 5–7 | **Mixed** |
| ≤ 4 | **Weak** |
| `None` | **Insufficient** |

**Overall label (no number):**

- `Insufficient data` — ≥ 4 of 6 dimensions are Insufficient.
- `Strong` — median dimension score ≥ 8 **and** no dimension ≤ 3.
- `Weak` — ≥ 3 dimensions ≤ 4.
- `Mixed` — otherwise.

**Disagreement list** (deterministic, from dimension scores) — examples:

- `Growth ≥ 8 and Valuation ≤ 4` → "Growing, but the price already reflects it."
- `Profitability ≥ 8 and Financial Health ≤ 4` → "Profitable, but the balance sheet is stretched."
- `Valuation ≥ 8 and Growth ≤ 4` → "Cheap, but the business is not growing."
- `Shareholder Returns ≥ 8 and Financial Health ≤ 4` → "Shareholder-friendly, but financed at risk."

No numeric total is ever shown. This is the project's "disagreement is
information" rule made concrete.

---

## 3. Data contracts

```text
DimensionRule
  rule_id              str          # "revenue_cagr_5y"
  label                str          # "Revenue CAGR (5y)"
  status               PASS | WATCH | FAIL | INSUFFICIENT
  value                str          # "12.4%" (formatted, from insights)
  threshold            str          # "≥ 10%"
  reason               str          # templated one-liner
  source_metric        str          # "revenue.cagr_5y"
  source_methodology   str | None   # "graham" (context only, not scoring)
  source_book          str | None   # "The Intelligent Investor (1949)"
  peer_percentile      float | None # 0..1, if a peer artifact applied

DimensionScore
  key, label, question str          # "growth", "Growth", "Is the business getting bigger?"
  score                int | None   # 0..10, None when INSUFFICIENT
  verdict              str          # Strong | Mixed | Weak | Insufficient
  evaluable_rules      int
  rules                list[DimensionRule]
  trend                str          # improving | stable | deteriorating
  summary              str          # "7/10 — revenue CAGR 12.4%, EPS CAGR 9.1%"

Scorecard
  ticker, company, sector, industry str
  period               str          # "FY"
  price, market_cap    float | None # fetched once, never persisted
  generated            str          # ISO date of the peer artifact (or "")
  dimensions           list[DimensionScore]   # fixed order, 6
  overall              str          # label only
  disagreements        list[str]
  methodologies        list[MethodologyResult]  # independent, unscored
  data_quality         str          # from the existing reliability heuristic
  notes                list[str]    # skipped rules, missing peers, etc.
```

`score` is **derivable** from `rules` by the formula in §2, so a reader (or a
test) can recompute it. The `Scorecard` never collapses `methodologies` into
`dimensions`.

---

## 4. Aggregation flow — `ScorecardService` (design)

```text
backend/services/scorecard_service.py

class ScorecardService:
    def __init__(self, repository, price_service, *, insights=None, alerts=None,
                 dcf=None, registry=methodology_registry, peer_stats=None): ...
    def build(self, ticker: str, period: str = "FY") -> Scorecard: ...
```

Flow (one fetch per source; nothing re-fetched downstream):

1. `facts` ← `FinancialsViewService.fetch_facts(ticker)` — **the only
   fundamentals fetch**; also yields company name, sector, industry, years.
2. `rows` ← `FinancialsViewService.build(facts)`.
3. `insights` ← `FinancialInsightsService(...).build()` from `facts`.
4. `alerts` ← `AlertService(...).run()` from `facts`.
5. `methodologies` ← evaluate the 8 registered methodologies from `rows`.
6. `quote` ← `PriceService.get_current_price(ticker)` — **the only price
   fetch**; never persisted (invariant preserved).
7. `dcf` ← existing DCF entry point on `rows` + `quote`.
8. `peers` ← `PeerStats.load(sector, industry)` (artifact; may be absent).
9. Aggregate → `Scorecard` (pure function over the objects above).

**Guarantees.**

- **Deterministic.** No randomness, no `now()` inside scoring. The only date
  is the peer artifact's own `generated` field, passed through verbatim.
- **No re-fetch.** One fundamentals fetch, one price fetch, one DCF.
- **Per-rule degradation.** A missing metric marks only its rule
  `INSUFFICIENT`; the dimension stays evaluable if ≥ 2 rules remain.
- **No new math** except the peer percentile (§5) and the trivial roll-up in
  §2.

---

## 5. Peer comparison

- **Peer group:** `industry` first; if the industry bucket has < 10 members,
  fall back to `sector`; if that also has < 10, **skip** and record a note.
- **Source:** precomputed artifact regenerated by a script, **weekly
  (Sundays)**, never on request.
- **Percentile:** share of peers strictly below the company's value (ties
  count ½), interpolated from stored quantiles, clamped to `[0, 1]`.

### Artifact shape — `data/peer_stats/<level>_<slug>.json`

```json
{
  "level": "industry",
  "name": "Semiconductors",
  "n": 63,
  "generated": "2026-10-14",
  "metrics": {
    "revenue_cagr_5y": {"n": 61, "min": -0.08, "p10": 0.02, "p25": 0.06,
                        "p50": 0.11, "p75": 0.19, "p90": 0.34, "max": 0.61},
    "net_margin":      {"n": 62, "min": -0.30, "p10": 0.03, "p25": 0.08,
                        "p50": 0.14, "p75": 0.22, "p90": 0.31, "max": 0.48}
  }
}
```

Plus `data/peer_stats/_index.json` (sector → industries → membership counts)
so the UI can label "vs Semiconductors (n=63)".

**Ignore status (measured).** `data/` is *selectively* ignored; `data/peer_stats/*`
is **not** ignored today. Phase 5 must add `data/peer_stats/` to `.gitignore`
(as `data/reports/daily_*.md` already is) so the artifact stays a local build
product. Until then a stray artifact would show as untracked.

**Coverage (measured, read-only):** 8 023 companies, 5 912 with sector
(73.7 %), **11** sector buckets ≥ 10, **121** industry buckets ≥ 10. The ~26 %
without sector/industry degrade to "no peer comparison".

---

## 6. Exposure (design only — nothing built here)

| Surface | Proposal |
|---|---|
| API | `GET /api/v1/company/{ticker}/scorecard` → existing envelope `{ok, data}`; errors via `fail()` (the global handler added in B3). |
| CLI | `./vi scorecard AAPL [--period FY] [--json]` — new `cli/commands/scorecard.py`; text render default, `--json` for the payload. |
| Streamlit | New **Scorecard** tab in `ui/pages/02_analysis.py` (appended, opt-in; not the default tab). |
| Mobile | Add **Scorecard** to `TABS` in `mobile/app/company/[ticker].tsx` (5 → 6 tabs). |

---

## 7. Visualization (Streamlit first)

New **Scorecard** tab, six zones:

1. **Header** (cheap, renders first): company · sector · ticker · current
   price · `overall` label · data-quality chip.
2. **Radar** (6 axes, 0–10) — realized with **plotly** (`go.Scatterpolar`)
   in Phase 4. A dependency-free fallback (horizontal `altair` bars) ships in
   Phase 3 so the tab is useful before plotly lands.
3. **Dimension cards** — one `st.expander` per dimension: score, verdict
   badge, one-line `summary`; expanded → the **rules table**
   (`Rule | Status | Value | Threshold | Why | Source`); a rule expands to its
   underlying trend chart.
4. **Charts (max 4):** revenue & net income bars; margin lines
   (gross/operating/net); ROE & ROIC lines; DCF value vs price.
5. **Peer table** — per metric: company value · peer median · percentile;
   only when the bucket has ≥ 10 peers.
6. **Disagreement panel** — the §2 list; explicitly says *no master score*.

All numbers come from the services; nothing is recomputed in the view.

### Illustrative wireframe (static SVG, design only)

```html
<svg viewBox="0 0 320 260" width="320" height="260" role="img"
     aria-label="Scorecard radar wireframe">
  <g fill="none" stroke="#cbd5e1">
    <polygon points="160,30 260,88 260,204 160,262 60,204 60,88"/>
    <polygon points="160,70 220,105 220,187 160,222 100,187 100,105"/>
    <polygon points="160,110 180,122 180,170 160,182 140,170 140,122"/>
  </g>
  <!-- company shape (Growth .9, Profitability .7, Health .6,
       Valuation .3, Returns .5, Moat .8) -->
  <polygon points="160,42 230,101 220,193 160,206 110,178 92,113"
           fill="#0B1B3A" fill-opacity="0.15" stroke="#0B1B3A" stroke-width="2"/>
  <g font-size="10" fill="#334155" text-anchor="middle">
    <text x="160" y="20">Growth</text>
    <text x="286" y="86">Profitability</text>
    <text x="286" y="212">Health</text>
    <text x="160" y="256">Valuation</text>
    <text x="34" y="212">Returns</text>
    <text x="34" y="86">Moat</text>
  </g>
</svg>
```

---

## 8. Interactivity

| Interaction | Streamlit mechanism | Fallback if unsupported |
|---|---|---|
| Click a radar axis → expand its card | plotly `on_select="rerun"` (Streamlit ≥ 1.35) | `st.selectbox` axis picker above the radar |
| Click a card → show rules | `st.expander` | — |
| Click a rule → show its chart | nested `st.expander` | — |
| Toggle absolute / vs sector | `st.toggle` → swaps thresholds / overlays peer markers | — |
| Toggle FY (quarterly deferred) | disabled control + note | — |
| Export JSON / Markdown | `st.download_button` (payload + rendered table) | — |

---

## 9. Mobile parity (design)

- **Radar:** hand-drawn with **`react-native-svg`** (`Polygon`/`Path`) — no
  new dependency. `victory-native` stays a deferred option, not required.
- **Cards:** expandable list items on the existing company screen.
- **Charts:** `react-native-svg` paths (sparklines/rows).
- **Placement:** the 6th tab in `mobile/app/company/[ticker].tsx`, reusing the
  same `/scorecard` payload. The Overview tab gains a compact radar + overall
  chip once the Streamlit layout settles.

---

## 10. Consistency and determinism

- The scorecard is a **presentation layer over the same rules** the
  methodologies, alerts and screener already use. Where a threshold is shared
  (e.g. D/E ≥ 1.5, interest coverage < 3×), it is copied on purpose so the
  scorecard cannot disagree with the screener's cap.
- `methodologies` are carried **verbatim** and rendered independently; the
  scorecard never re-weights or averages them.
- Missing data → `INSUFFICIENT` + a `notes` entry; never a 0.
- No wall-clock in scoring; the peer artifact's date is data, not "now".

---

## 11. Design-level open questions

1. **plotly pin** — exact version to add in Phase 4 (Streamlit-only;
   mobile stays on `react-native-svg`).
2. **ROIC / interest coverage / current ratio** — these are not in
   `FinancialInsightsService` today; source from `backend/analytics/ratios`
   (confirmed module) or mark `INSUFFICIENT` until wired. Confirm the ratio
   module exposes them without new math.
3. **Sector/industry source** — confirm `CompanyRepository` exposes
   `sector`/`industry` for a ticker (the FDB `companies` table has both).
4. **Valuation peer rule** — keep `pe_vs_peers` as a soft dependency (skipped
   without the artifact) or make Valuation peer-free until Phase 5?

---

## Appendix A — Worked example (AAPL, FY)

A concrete reference of what `ScorecardService` produces. It is built from
Financial-DataBase fundamentals plus a real-time Yahoo price; no figure below is
computed by a view layer — the API, the CLI and the (Phase 3) Streamlit tab all
render this same summary.

| Dimension | Score | Verdict | Trend | Evaluable rules |
|---|---|---|---|---|
| Growth | 7/10 | Mixed | improving | 5 |
| Profitability | 10/10 | Strong | improving | 6 |
| Financial Health | 8/10 | Strong | stable | 3 |
| Valuation | 2/10 | Weak | stable | 4 |
| Shareholder Returns | 10/10 | Strong | stable | 4 |
| Management/Moat | 7/10 | Mixed | stable | 3 |

**Overall:** Mixed · **Sector:** Technology · **Industry:** Consumer Electronics
· **Data quality:** HIGH.

The spread (Profitability 10 vs Valuation 2) is the point: the roll-up is a
**label**, not a master score, and this disagreement is carried in the
`disagreements` field rather than averaged away. Two Financial Health rules
(`interest_coverage`, `current_ratio`) degrade to `INSUFFICIENT` for AAPL, so
that dimension scores on three rules, not five.
