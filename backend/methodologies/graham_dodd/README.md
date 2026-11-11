# Graham & Dodd Methodology

**Book:** *Security Analysis* by Benjamin Graham & David Dodd (1934)

Detects deep value from balance-sheet signatures.

## Rules

The original five rules below are kept (now weighted); v2.0.0 adds 21 deep
checks (net-net/NCAV, balance-sheet ladder, earnings power/EPV, asset value
and margin of safety). See `docs/graham_dodd_rules.md` for the full 26-rule
table.

| # | Rule | Threshold | Source |
|---|------|-----------|--------|
| 1 | NWC test | Price < 2/3 of NWC per share | p. 5 |
| 2 | Fixed-charge coverage | ≥ 1.5x in 5 of last 6 years | p. 230 |
| 3 | Earnings stability | Positive in 7 of last 10 years | p. 101 |
| 4 | Balance sheet strength | Liabilities/assets ≤ 0.5 | p. 38, 41 |
| 5 | Margin of safety | Qualitative (see below) | p. 5, 101 |

## Verdict Logic (weighted, v2.0.0)

Every rule has a weight (2 critical, 1 normal, 0 informational) and the
verdict is the weighted pass ratio:

`weighted_score = Σ weight(passed) / Σ weight(evaluable)`

- **BUY**: score ≥ 0.85
- **WATCH**: 0.70–0.85
- **HOLD**: 0.50–0.70
- **AVOID**: < 0.50
- **INSUFFICIENT_DATA**: > 30% of the weighted rules missing data

Rule 5 (qualitative) and two deep checks are informational (weight 0) and do
not contribute to the score. See `docs/graham_dodd_rules.md` for the full
26-rule table, sources and data limits.

## Distinction vs Graham (Intelligent Investor)

- **graham** (Intelligent Investor): defensive criteria, actionable today
- **graham_dodd** (Security Analysis): earlier, more rigorous and more
  conservative framework, with explicit fixed-charge coverage

## Known Limitations

- NWC test calibrated to Depression-era markets; rarely triggers today for large caps.
- Fixed-charge coverage examples are US railroads from 1934.
- No definitive equity criteria — the book itself warns about this.
- Rule 5 is intentionally qualitative and does not contribute to the score.
