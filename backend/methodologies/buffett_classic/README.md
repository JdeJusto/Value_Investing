# buffett_classic — Buffett/Munger 4-pillar filter (wrapped)

`buffett_classic` is the existing, production Buffett filter in
`backend/intelligence/buffett_engine.py` exposed as a framework methodology.
It is a **wrapper only**: `backend/intelligence/buffett_engine.py` is not
modified.

## What it evaluates

Four pillars, scored 0–100 with explicit published thresholds and fixed weights
(profitability 0.35, financial strength 0.25, cash generation 0.25, stability
0.15), blended into one composite score:

- profitability — ROE, ROIC, gross-margin stability
- financial_strength — debt/equity, interest coverage, retained earnings
- cash_generation — positive FCF ratio, FCF growth
- stability — earnings CV, max YoY decline

A moat estimate from `backend/intelligence/moat_analysis.py` is attached to
the metrics for display; it does not drive the verdict.

## Mapping to the framework

| Engine output                     | MethodologyResult                    |
| --------------------------------- | ------------------------------------ |
| `score` (0-100)                   | `score`                              |
| `breakdown` (4 pillars)           | `metrics` (plus `moat`)              |
| no verdict in engine              | BUY ≥ 75, WATCH ≥ 60, HOLD ≥ 40, else AVOID |
| no confidence in engine           | `HIGH` (deterministic engine)        |

The verdict thresholds are the framework's convention for wrapped numeric
filters (`docs/methodology_decisions.md`); the engine itself defines none.

## Distinction vs `buffett_clark`

- `buffett_classic` — the qualitative Buffett/Munger *business-quality*
  filter (is it a great business?). Verdict is about strength, not price.
- `buffett_clark` — the *DCA rules* from the Buffett/Clark book (buy in
  tranches into undervalued quality). Different book, different rules.

## Distinction vs `graham` / `graham_dodd`

`graham` and `graham_dodd` are value screens: they judge the price paid against
assets/earnings and require a margin of safety. `buffett_classic` does not
look at the price — a strong-but-expensive company can get BUY here and AVOID
from the value screens. That disagreement is by design.

## Usage

    python main.py analyze-buffett-classic AAPL
    python main.py compare-methodologies AAPL

## Known limitations

- Quality-only: does not value the company or check the price.
- Verdict thresholds are framework conventions (75/60/40).
- Sources point to the engine module (implementation-defined), not a book.
- **Does not apply to financial companies** (banks, insurers): the shared
  company-type detector routes them to INSUFFICIENT_DATA with confidence
  HIGH, because the financial-strength pillar (debt/equity, interest
  coverage) reads bank leverage as weakness. This matches the other five
  book methodologies; the guard was added on 2026-09-30 for consistency.
