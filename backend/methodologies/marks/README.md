# marks — cycles, resilience, value and quality (quantitative subset) — v2.0.0

Howard Marks' philosophy from *The Most Important Thing* (2011): the cycle,
risk control, second-level thinking and buying below value. Marks is a
**qualitative** investor — market temperature and the pendulum of psychology
cannot be read from a filing — so this module implements only the
**measurable subset**, and every result says so in its sources.

**The book was not found on this machine** (see
`docs/books_notes/the-most-important-thing.md`). Every rule is a
**public-knowledge reconstruction** labelled `page="public knowledge"`; no
quote, page number or page-level paraphrase is claimed.

## Rules

v2.0.0 keeps the four original rules and adds 13 deep checks. All 17 feed the
shared weighted verdict. The full table is in `docs/marks_rules.md`.

| # | Rule | Measure | Weight |
| --- | --- | --- | ---: |
| 1 | Cycle position | current operating margin and ROIC vs their own multi-year mean | 1 |
| 2 | Resilience | net debt/EBITDA ≤ 2.5x, interest coverage ≥ 4x, FCF > 0 | 2 |
| 3 | Margin of safety | FCF yield ≥ 4% **or** EV/EBIT ≤ 12 | 2 |
| 4 | Quality persistence | 5y average ROIC ≥ 10% and positive in ≥ 4 of 5 years | 2 |
| 5-17 | Deep checks | DCF margin, own-history P/E, P/B, earnings yield, ROIC 15%, 5y FCF, margin stability, revenue growth, low debt, 10x coverage, no dilution, P/E percentile, not-peak margin | 1-2 |

## Score and verdict

```
weighted_score = sum(weight for passed) / sum(weight for evaluable)
```

| Condition | Verdict |
| --- | --- |
| net debt/EBITDA > 4x | **AVOID** (hard risk gate; the score still shows the weighted ratio) |
| weighted score ≥ 0.85 | **BUY** |
| ≥ 0.70 | **WATCH** |
| ≥ 0.50 | **HOLD** |
| < 0.50 | **AVOID** |

More than 30% of the weighted rules missing data returns
INSUFFICIENT_DATA. Confidence is HIGH with no missing weight, MEDIUM up to
10%, LOW above that.

INSUFFICIENT_DATA also when the company is financial (the shared guard) or
there are fewer than 3 fiscal years of history (a cycle reading needs
history).

## Usage

```bash
python main.py analyze-marks AAPL
python main.py compare-methodologies AAPL   # marks is the 8th row
```

## Known limitations

- Market-wide cycle timing, the credit cycle, the pendulum of psychology and
  second-level thinking are **not** measurable from filings; this is a
  subset, never a Marks replica.
- EV/EBIT and FCF yield need a live price; without one, rule 3 cannot pass.
- The own-history P/E rules use a constant-price proxy.
- The DCF rule reuses the not-from-canon two-stage DCF and is N/A when its
  inputs are missing.
