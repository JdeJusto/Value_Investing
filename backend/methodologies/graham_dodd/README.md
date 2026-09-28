# Graham & Dodd Methodology

**Book:** *Security Analysis* by Benjamin Graham & David Dodd (1934)

Detects deep value from balance-sheet signatures.

## Rules

| # | Rule | Threshold | Source |
|---|------|-----------|--------|
| 1 | NWC test | Price < 2/3 of NWC per share | p. 5 |
| 2 | Fixed-charge coverage | ≥ 1.5x in 5 of last 6 years | p. 230 |
| 3 | Earnings stability | Positive in 7 of last 10 years | p. 101 |
| 4 | Balance sheet strength | Liabilities/assets ≤ 0.5 | p. 38, 41 |
| 5 | Margin of safety | Qualitative (see below) | p. 5, 101 |

## Verdict Logic

- **BUY**: rule 1 PASS AND rule 2 PASS AND rule 3 PASS
- **WATCH**: rule 1 PASS AND rule 2 FAIL, OR rule 1 FAIL AND rule 2 PASS
- **HOLD**: 2 of 4 quantitative rules pass
- **AVOID**: < 2 quantitative rules pass OR rule 4 FAIL
- **INSUFFICIENT_DATA**: > 2 rules INSUFFICIENT_DATA

## Score

`score = (quantitative_passed / 4) × 100`

Rule 5 (qualitative) does NOT contribute to the score.

## Confidence

- **HIGH**: all 4 quantitative rules evaluated
- **MEDIUM**: 1–2 rules unknown
- **LOW**: > 2 rules unknown

## Distinction vs Graham (Intelligent Investor)

- **graham** (Intelligent Investor): defensive criteria, actionable today
- **graham_dodd** (Security Analysis): earlier, more rigorous and more
  conservative framework, with explicit fixed-charge coverage

## Known Limitations

- NWC test calibrated to Depression-era markets; rarely triggers today for large caps.
- Fixed-charge coverage examples are US railroads from 1934.
- No definitive equity criteria — the book itself warns about this.
- Rule 5 is intentionally qualitative and does not contribute to the score.
