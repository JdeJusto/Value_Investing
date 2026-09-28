# fisher_quantitative_subset

**This methodology is a quantitative SUBSET of Philip Fisher's 15
points. It is NOT Fisher. The 11 non-quantifiable points require
scuttlebutt (interviews with competitors, suppliers, customers, and
ex-employees) which the system does not have. See
docs/methodology_decisions.md decision 1.**

## The 4 points implemented (and why)

| # | Rule | Book page | Data used | Threshold |
|---|------|-----------|-----------|-----------|
| 3 | R&D intensity relative to size | 54–55 | `research_development` / revenue | PASS ≥ 8%, WATCH 2–8%, FAIL < 2% |
| 5 | Worthwhile profit margin | 63–64 | net + operating margin | PASS net ≥ 10% AND op ≥ 15%; FAIL net < 5% |
| 10 | Cost analysis & accounting controls | 69 | gross-margin stdev (5y) | PASS < 0.03, WATCH < 0.05, FAIL ≥ 0.05 |
| 13 | Growth without equity financing | 75 | shares now vs 10y ago (split-adjusted) | PASS no increase; WATCH ≤ 10%; FAIL > 10% |

These 4 are the only points that can be computed from the financial
statements the system already has (revenue, margins, R&D spend, share
counts). Fisher himself calls the R&D ratio a "crude yardstick" (p. 55)
and insists margins be read over a series of years. Because the 11
scuttlebutt points are missing, the quantitative gates are deliberately
stricter than the book: the R&D PASS bar sits at the top of the large-cap
range (8%) and BUY requires full data coverage (see Calibration history).

## The 11 points NOT implemented (and why)

Points 1, 2, 4, 6, 7, 8, 9, 11, 12, 14 and 15 all ask questions that
financial statements cannot answer without outside research:

- **Point 1 & 2** — multi-year sales potential; management determined to develop new markets (qualitative).
- **Point 4** — above-average sales organization (scuttlebutt).
- **Points 6–9** — margin trend; labor relations; executive relations; management depth (interviews).
- **Point 11** — industry-specific factors (expert judgement).
- **Point 12** — long-range profit outlook (management disclosure).
- **Point 14 & 15** — candor and integrity of management (scuttlebutt, track record).

Coding them without scuttlebutt would produce a questionnaire full of
guesses — a *fake Fisher*. Hence decision 1 in
`docs/methodology_decisions.md`: subset only, named
`fisher_quantitative_subset`, never `fisher`.

## Verdict logic

- **BUY**: all 4 rules PASS (no INSUFFICIENT_DATA, WATCH or FAIL)
- **WATCH**: ≥ 3 rules PASS with at most 1 INSUFFICIENT_DATA/WATCH
- **HOLD**: ≥ 2 rules PASS
- **AVOID**: any rule FAIL, OR fewer than 2 rules PASS
- **INSUFFICIENT_DATA**: ≥ 3 rules INSUFFICIENT_DATA

## Score

`score = (rules_passed / 4) × 100` — always divided by all 4 rules.
INSUFFICIENT_DATA counts as 0 in the numerator. `None` only when the
verdict is INSUFFICIENT_DATA (no information ≠ a failing grade).

## Confidence

HIGH when all 4 rules evaluated, MEDIUM with 1 INSUFFICIENT_DATA, LOW otherwise.

## Red flags

- R&D below 2% of revenue without explanation
- Net margin below 5%
- Gross-margin standard deviation above 5% over 5 years
- Share count increased more than 10% over 10 years

## Interpretation caveats

- This is a **quality screen, not a valuation** — price is never consulted,
  so a BUY here can coexist with a Graham AVOID. That is intentional.
- The R&D PASS bar (8%) applies to every company because the system has
  no sector information: consumer staples will usually read WATCH (their
  spend sits in the 2–8% band) or FAIL when "R&D" happens in-process, and
  the rule degrades to INSUFFICIENT_DATA when R&D is not reported at all
  (KO). When a filer keeps its substantive R&D under
  `ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost` (JNJ), the
  reconstruction prefers that tag over a residual plain tag.
- Cost control is proxied by gross-margin stability; a real audit of
  accounting controls is impossible from filings alone.
- The 10-year share comparison restates the old share count for stock
  splits using the XBRL `StockholdersEquityNoteStockSplitConversionRatio*`
  facts (a 4:1 split multiplies pre-split counts by 4 before comparing).
  Filers that do not report a ratio keep the as-reported count (factor
  1.0), so a missed split can still read as dilution; buybacks and option
  grants show up only as the net share change, not separately.

## Calibration history

### 2026-09-28 — gates tightened for real discrimination

The previous gates gave BUY 100/100 to every healthy company (AAPL, MSFT
and KO all read 100) — mathematically correct but useless as a filter. A
4-point subset with no scuttlebutt compensates with stricter quantitative
gates:

- Rule 1 R&D: PASS 5% → **8%**, WATCH 2–5% → **2–8%**, FAIL stays < 2%.
- BUY now requires **4/4 rules PASS** (no INSUFFICIENT_DATA, WATCH or
  FAIL); previously ≥ 3 PASS with no FAIL.
- Score now divides by all 4 rules: `passed / 4 × 100`; INSUFFICIENT_DATA
  counts as 0. `None` only for an INSUFFICIENT_DATA verdict.

Re-verified on 10 companies (AAPL, MSFT, KO, JNJ, PG, XOM, F, GM, INTC,
T): only top-of-range R&D names with full data reach BUY.

## Usage

    python main.py analyze-fisher-quant AAPL
    python main.py compare-methodologies AAPL
