# fisher_quantitative_subset

**This methodology is a quantitative SUBSET of Philip Fisher's 15
points. It is NOT Fisher. The 11 non-quantifiable points require
scuttlebutt (interviews with competitors, suppliers, customers, and
ex-employees) which the system does not have. See
docs/methodology_decisions.md decision 1.**

## The 4 points implemented (and why)

| # | Rule | Book page | Data used | Threshold |
|---|------|-----------|-----------|-----------|
| 3 | R&D intensity relative to size | 54–55 | `research_development` / revenue | PASS ≥ 5%, WATCH 2–5%, FAIL < 2% |
| 5 | Worthwhile profit margin | 63–64 | net + operating margin | PASS net ≥ 10% AND op ≥ 15%; FAIL net < 5% |
| 10 | Cost analysis & accounting controls | 69 | gross-margin stdev (5y) | PASS < 0.03, WATCH < 0.05, FAIL ≥ 0.05 |
| 13 | Growth without equity financing | 75 | shares now vs 10y ago | PASS no increase; WATCH ≤ 10%; FAIL > 10% |

These 4 are the only points that can be computed from the financial
statements the system already has (revenue, margins, R&D spend, share
counts). Fisher himself calls the R&D ratio a "crude yardstick" (p. 55)
and insists margins be read over a series of years, so the thresholds
are deliberately conservative.

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

- **BUY**: ≥ 3 rules PASS and no rule FAIL
- **WATCH**: ≥ 2 rules PASS
- **HOLD**: 1 rule PASS
- **AVOID**: any FAIL on rules 2 or 4, OR fewer than 1 rule PASS
- **INSUFFICIENT_DATA**: ≥ 3 rules INSUFFICIENT_DATA

## Score

`score = (rules_passed / evaluable_rules) × 100`, where *evaluable*
excludes INSUFFICIENT_DATA rules. `None` when fewer than 2 rules are
evaluable.

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
- The R&D bar (5%) applies to every company because the system has no
  sector information: consumer staples will usually read WATCH/FAIL even
  when their "R&D" happens in-process, and the rule degrades to
  INSUFFICIENT_DATA when R&D is not reported at all.
- Cost control is proxied by gross-margin stability; a real audit of
  accounting controls is impossible from filings alone.
- Dilution uses reported share counts; buybacks and splits are only as
  good as the as-reported data.

## Usage

    python main.py analyze-fisher-quant AAPL
    python main.py compare-methodologies AAPL
