# QA session — cross-methodology coherence (2026-09-30)

`compare-methodologies` for five profiles plus the individual runs from the
CLI smoke test.

| Ticker | graham | graham_dodd | buffett_classic | buffett_clark | fisher | lynch | Flag |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AAPL | AVOID 28.6 | AVOID 25.0 | WATCH 74.7 | BUY 71.4 | BUY 100 | AVOID 20.0 | OK |
| KO | AVOID 14.3 | WATCH 50.0 | BUY 80.5 | WATCH 57.1 | WATCH 75.0 | BUY — | OK |
| JPM | INS | INS | AVOID 29.2 | INS | INS | INS | OK by design |
| F | INS | INS | AVOID 34.7 | INS | INS | INS | UNCLEAR (detector) |
| XOM | AVOID 14.3 | HOLD 50.0 | HOLD 55.9 | AVOID 28.6 | AVOID 0.0 | AVOID 20.0 | UNCLEAR (summary) |

## Per ticker

- **AAPL — OK.** Quality family agrees direction (BUY/WATCH/BUY); deep
  value and GARP reject the price. The summary explains the split
  correctly ("strong-but-expensive company"). Scores are in range and the
  lynch score is 20.00 (numeric: Stalwart).
- **KO — OK.** Quality family WATCH/BUY/WATCH; deep value rejects
  (graham AVOID, graham-dodd WATCH). Fisher's 75 comes from rule 1
  INSUFFICIENT (R&D not reported — documented). Lynch BUY with score
  `None` is the SLOW_GROWER design (score hidden, dividend-driven
  verdict) and the `score_note` explains it.
- **JPM — OK by design, with one caveat.** The five guarded
  methodologies return INSUFFICIENT_DATA (financial detection) as
  required. `buffett_classic` shows AVOID 29.2 because it was
  deliberately left without the financial guard (original scope rule:
  "Do NOT modify buffett_classic"). The task brief expected "all 5"
  INSUFFICIENT — there are 6 methodologies and the 5 guarded ones comply.
  Caveat recorded in the backlog: decide whether buffett_classic should
  also abstain on banks (its financial_strength pillar reads a bank's
  leverage as weakness).
- **F (Ford) — UNCLEAR (calibration).** All five guarded methodologies
  abstain because `total_liabilities / total_assets > 0.85` (Ford Credit).
  The detector is doing what it documents, but Ford is an industrial with
  a captive finance arm, not a bank. Backlog P2: consider requiring "no
  inventory" alongside the ratio, or a sector hint override.
- **XOM — UNCLEAR (summary text).** Verdicts are plausible for a cyclical
  (deep value AVOID/HOLD, quality AVOID/HOLD/AVOID, fisher AVOID 0.0 —
  its energy R&D rule). However the disagreement summary prints the
  generic "expensive/levered balance sheet vs strong-but-expensive
  quality" paragraph, which does not describe this split. The family
  lines are correct; the explanation is boilerplate. Backlog P2: make
  the explanation conditional (e.g., only when a value member is AVOID
  and a quality member is BUY; otherwise say "different lenses").

## Scores audit

All scores are within 0-100; `None` appears only for SLOW_GROWER (KO
lynch) and for INSUFFICIENT verdicts. No score > 100 or < 0 was observed.
