# fisher_quantitative_subset

**This methodology is a quantitative SUBSET of Philip Fisher's 15
points. It is NOT Fisher. The 11 non-quantifiable points require
scuttlebutt (interviews with competitors, suppliers, customers, and
ex-employees) which the system does not have. See
docs/methodology_decisions.md decision 1.**

## The 4 points implemented (and why)

| # | Rule | Book page | Data used | Threshold |
|---|------|-----------|-----------|-----------|
| 3 | R&D intensity relative to size | 54–55 | `research_development` / revenue | PASS ≥ sector bar (tech 8%, industrials 4%, staples 2%; fallback 8%), FAIL < 0.5–2% floor |
| 5 | Worthwhile profit margin | 63–64 | net + operating margin | PASS net ≥ 10% AND op ≥ 15%; FAIL net < 5% |
| 10 | Cost analysis & accounting controls | 69 | gross-margin stdev (5y) | PASS < 0.03, WATCH < 0.05, FAIL ≥ 0.05 |
| 13 | Growth without equity financing | 75 | shares now vs 10y ago (split-adjusted) | PASS no increase; WATCH ≤ 10%; FAIL > 10% |

These 4 are the only points that can be computed from the financial
statements the system already has (revenue, margins, R&D spend, share
counts). Fisher himself calls the R&D ratio a "crude yardstick" (p. 55)
and insists margins be read over a series of years. Because the 11
scuttlebutt points are missing, the quantitative gates are deliberately
stricter than the book: the innovation-led R&D PASS bar sits at the top of
the large-cap range (8%) and BUY requires full data coverage (see
Calibration history).

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

- R&D below the sector's FAIL floor (0.5–2% of revenue) without explanation
- Net margin below 5%
- Gross-margin standard deviation above 5% over 5 years
- Share count increased more than 10% over 10 years

## Interpretation caveats

- This is a **quality screen, not a valuation** — price is never consulted,
  so a BUY here can coexist with a Graham AVOID. That is intentional.
- The R&D bar is **sector-aware**, keyed on the Yahoo/GICS sector label the
  repository attaches from Financial-DataBase metadata: innovation-led
  sectors (Technology/Healthcare/Communication Services) require 8% of
  revenue, capital-goods sectors 4%, and low-R&D sectors (staples, utilities,
  energy, real estate) only 2%, with a 0.5% "no meaningful R&D" floor. An
  unknown or missing sector keeps the calibrated 8%/2% bar, so missing
  metadata never silently relaxes the screen. Consumer staples therefore no
  longer read near-AVOID for a 2% spend, and the rule still degrades to
  INSUFFICIENT_DATA when R&D is not reported at all (KO). When a filer keeps
  its substantive R&D under
  `ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost` (JNJ), the
  reconstruction prefers that tag over a residual plain tag.
- **Companies that structurally do not report R&D** (consumer staples are the
  common case) read INSUFFICIENT_DATA on rule 1 and are judged on the
  remaining three rules. KO is the canonical example: its full XBRL history
  carries 724 us-gaap concepts and **zero** R&D tags (verified against SEC
  `companyfacts`, 2026-09-29) — R&D is embedded in SG&A and immaterial to the
  total, so there is no tag to map and nothing to reconstruct. This is a
  structural limit of a filing-based screen, not a data gap.
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
