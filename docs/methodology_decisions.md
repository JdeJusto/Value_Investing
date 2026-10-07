# Methodology design decisions

Permanente reference for the multi-methodology analysis engine. These ten
decisions were fixed after analyzing four value-investing classics
(book notes kept outside the repository) and **cannot be re-litigated by an
implementation**: if a change is wanted, edit this document first.

The books, abbreviated below:
- **FIS** — *Common Stocks and Uncommon Profits*, Philip A. Fisher (1958)
- **GRA** — *The Intelligent Investor*, Benjamin Graham (1949; 4ª ed. 1973 con Zweig)
- **BC** — *Warren Buffett y la interpretación de estados financieros*, Mary Buffett & David Clark
- **GD** — *Security Analysis*, Graham & Dodd (1934)

## Decision 1 — Fisher without scuttlebutt

**Decision:** Do **NOT** implement Fisher in this cycle. If implemented in the
future, only the quantifiable points (3, 5, 10, 13) will be coded, and the
methodology will be named `fisher_quantitative_subset` — **never** `fisher`.

**Rationale:** The core of Fisher (the scuttlebutt method) requires interviews
with competitors, suppliers, customers and ex-employees. That data source does
not exist in this system and cannot be synthesized. Coding the 15-point
checklist without scuttlebutt would produce a **fake Fisher**: a questionnaire
with no answers. A subset is honest only if it is labelled as a subset.

## Decision 2 — How disagreements are surfaced

**Decision:** Three independent columns (one per methodology) in the report,
plus a **"Disagreement summary"** section that explains the **nature** of each
conflict. **NO** methodology is presented as "dominant" for a company type.
**NO** master score.

**Rationale:** Recommending a dominant methodology by company type is a
composite score in disguise. It would hide exactly the disagreement the user
explicitly wants to see. The report must be able to say "Graham says AVOID,
Buffett says BUY" and stop there.

## Decision 3 — Graham's 22.5 test

**Decision:** Exposed **both** as a gate (reject if P/E × P/BV > 22.5) **and**
as a standalone metric in the results table.

**Rationale:** The book presents it as a *compensating* ratio — a high P/E is
allowed when P/BV is low (9× earnings at 2,5× book passes). A gate alone hides
those cases; a metric alone does not reject. Both are needed.

## Decision 4 — Era adjustment of Graham thresholds

**Decision:** Add an `era_adjustment: bool = False` parameter to the Graham
methodology. **Default `False`** (strict fidelity to the book). If `True`, apply
a documented adjustment (see `backend/methodologies/graham/README.md` § Era
adjustment). The adjusted variant is labelled `graham_modernized` in reports.

**Rationale:** Never hardcode modernization. The user must be able to compare
"Graham 1949" against "Graham modernized" side by side, and the default must be
the book, not our opinion of it.

## Decision 5 — Buffett/Clark 40% gross margin rule

**Decision:** Keep the 40% threshold **as stated**. Do **NOT** relax it for
tech or SaaS.

**Rationale:** The rule is intentionally strict. Its purpose is to filter out
companies without pricing power — and a SaaS company with a 30% gross margin
does not have a durable competitive advantage *by this definition*. Relaxing
it for a sector would defeat the rule's only function.

## Decision 6 — Books as historical or current sources

**Decision:** Treat them as **HISTORICAL**. Every `SourceRef` must include
`era` (e.g. `"1973"`) and `us_caution` (e.g. "$100M in 1973 dollars is trivial
in 2024").

**Rationale:** The system must not pretend these rules are timeless. The user
can then decide when to apply era adjustment, and the provenance of every claim
is explicit.

## Decision 7 — DCF for Fisher (or any growth valuation)

**Decision:** A `valuation/dcf.py` module **may** exist but is **EXPLICITLY not
part of any book-derived methodology**. It is labelled
`source: "not-from-canon"` in all outputs. **NOT implemented in this session.**

**Rationale:** No book in the canon values growth. Mixing a DCF into Graham or
Fisher would be a category error — it would silently import an assumption none
of them make.

## Decision 8 — Implementation order

**Decision:** Graham first, then Buffett/Clark, then Graham & Dodd. Fisher
deferred.

**Rationale:** Graham is the most mechanizable (exact thresholds that map
1:1 onto existing filters). Buffett/Clark builds on similar patterns (two
ratios). Graham & Dodd is more complex (bond coverage, NWC, margin of safety).
Fisher requires data sources we lack.

## Decision 9 — Anti-patterns (explicit)

Do **NOT**:
- Merge methodologies into a composite score.
- Average thresholds across books.
- Overwrite one verdict with another.
- Add a master score that hides disagreement.
- Present a "recommended" methodology per company type.
- Force a numeric score where the book provides none (`score: None` is a valid result).

## Decision 10 — Score is optional

**Decision:** `MethodologyResult.score` is `float | None`. When a methodology
returns `None`, reports must render **"—"** (em-dash) or **"N/A"** — **never
`0.0`**.

**Rationale:** A qualitative methodology (or one that only produces PASS/FAIL
gates) must not be reduced to a numeric score. `0.0` is a score; `None` is the
absence of one.

## Calibration log

Quantitative screen settings (thresholds / verdict gates / score formulas)
are **not** re-litigations of Decision 1–10: the book sources are untouched,
but a settings change must be logged here so a future change is caught and
the reason stays on record.

### fisher_quantitative_subset — 2026-09-28

- Rule 1 R&D: PASS 5% → **8%** (WATCH now 2–8%, FAIL stays < 2%).
- BUY gate: ≥ 3 PASS with no FAIL → **4/4 rules PASS**.
- Score: `passed / evaluable × 100` → **`passed / 4 × 100`** (INSUFFICIENT_DATA
  counts as 0; `None` only on an INSUFFICIENT_DATA verdict).
- Reason: the previous gates gave BUY 100/100 to every healthy company
  (AAPL, MSFT, KO …), useless as a filter. A 4-point subset with no
  scuttlebutt compensates with stricter quantitative gates: only top-of-range
  R&D (≥ 8%) names with full data coverage reach BUY.
- R&D concept fallback: when a filer files both `ResearchAndDevelopmentExpense`
  and `ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost` (JNJ), the
  reconstruction keeps the more complete figure so a residual plain tag cannot
  read as "no/low R&D".
- Re-verification (10 companies): AAPL/MSFT BUY 100; KO WATCH 75 (R&D not
  reported); PG HOLD 50 (R&D 2.4%); F AVOID (negative margins); JNJ HOLD 50
  after the concept fallback; XOM/GM/INTC/T remain INSUFFICIENT_DATA (partial
  FDB coverage). No verdict of the other methodologies was touched.

## Decision 11 — NOT_APPLICABLE for financial companies (2026-10-07)

**Decision:** A book screen written for product companies (leverage, net PPE,
R&D, EV/EBIT, ROC on an industrial balance sheet) returns
`Verdict.NOT_APPLICABLE` (`"N/A"`) on a bank or insurer, with the canonical
reason `financial company — rules do not apply`. This is distinct from
`INSUFFICIENT_DATA`, which means "the data to decide is missing".

**Rationale:** Reporting a bank as `INSUFFICIENT_DATA` implied a data gap and
pushed the company into the "no real verdict" bucket, where it was both shown
to the user and silently excluded from consensus rankings for the wrong
reason. `N/A` states the truth — the methodology abstains by design — and lets
the consensus count and exclude those companies explicitly (`na_count`).
Neither verdict is a buy, a hold or a sell; both render dim/neutral.

### ratio sanity guards — 2026-10-07

- `backend/methodologies/common/ratio_guards.py` introduces
  `is_meaningful_pe` / `is_meaningful_pbv` / `is_meaningful_ev_ebit` /
  `is_meaningful_fcf_yield`. A ratio that is non-positive or above a
  deliberately loose ceiling (P/E 100, P/BV 50, EV/EBIT 100, |FCF yield|
  100%) is a denominator artifact (losses or a near-zero denominator), not
  cheapness, and a ratio rule must **fail**, never pass, on it.
- Applied where a ratio gates a rule: Graham criterion 6 (P/E), criterion 7
  (P/BV) and the combined 22.5 product; Lynch PEG, dividend-adjusted PEGY and
  the asset-play P/BV; Marks' margin-of-safety rule (EV/EBIT and FCF yield).
- Net effect on the reported artifacts: CSGP's Marks verdict moves
  WATCH 60 → **HOLD 35** (a negative EBIT had been read as a margin of safety).
  AAPL (buffett_classic WATCH 74.72), KO (BUY 80.46) and every other observed
  verdict are unchanged.
- Known limitation: `buffett_classic` produces a **price-independent** quality
  score (four pillars: profitability, financial strength, cash generation,
  stability). It consumes no P/E, so a "BUY next to a negative P/E" pairing in
  a screener export is the quality score sitting beside an unrelated valuation
  column, not a valuation rule passing on a loss. Making it price-aware would
  add a new rule and is deliberately out of scope.
