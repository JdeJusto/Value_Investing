# marks — cycles, resilience, value and quality (quantitative subset)

Howard Marks' philosophy from *The Most Important Thing* (2011): the cycle,
risk control, second-level thinking and buying below value. Marks is a
**qualitative** investor — market temperature and the pendulum of psychology
cannot be read from a filing — so this module implements only the
**measurable subset**, and every result says so in its sources.

## Rules

| # | Rule | Measure | Source |
| --- | --- | --- | --- |
| 1 | Cycle position | current operating margin and ROIC vs their own multi-year mean (±3 pp = peak / trough) | ch. 14, being attentive to cycles |
| 2 | Resilience | net debt/EBITDA ≤ 2.5x, interest coverage ≥ 4x, FCF > 0 | ch. 5, controlling risk |
| 3 | Margin of safety | FCF yield ≥ 4% **or** EV/EBIT ≤ 12 | ch. 4, value |
| 4 | Quality persistence | 5y average ROIC ≥ 10% and positive in ≥ 4 of 5 years | ch. 7, knowing what you don't know |

## Verdict

25 points per passed rule, adjusted by the cycle reading (**−15** at a peak,
**+10** at a trough, clamped to 0-100):

| Condition | Verdict |
| --- | --- |
| net debt/EBITDA > 4x | **AVOID** (balance sheet is the risk) |
| score ≥ 75 **and** resilience **and** margin of safety **and** quality **and** not peak | **BUY** |
| score ≥ 50 | **WATCH** |
| score ≥ 25 | **HOLD** |
| otherwise | **AVOID** |

INSUFFICIENT_DATA when: the company is financial (the shared guard — leverage,
coverage and EV/EBIT are not comparable), or there are fewer than 3 fiscal
years of history (a cycle reading needs history). Confidence is HIGH with 5+
years and a market cap, MEDIUM otherwise.

## Usage

```bash
python main.py analyze-marks AAPL
python main.py compare-methodologies AAPL   # marks is the 8th row
```

## Known limitations

- Market-wide cycle timing, the pendulum of psychology and second-level
  thinking are **not** measurable from filings; this is a subset, never a
  Marks replica (same decision as Fisher's quantitative subset).
- EV/EBIT and FCF yield need a live price; without one, rule 3 cannot pass.
