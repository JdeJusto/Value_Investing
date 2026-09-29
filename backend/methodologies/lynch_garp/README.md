# Lynch GARP (Growth At a Reasonable Price)

A self-contained book methodology implementing Peter Lynch's quantitative
GARP screen. Registered automatically with the methodologies registry as
`lynch_garp` — it is **one column** in the comparison table, never a
contributor to the composite score.

## Books and editions

| Book | Author | Edition used | Year |
| --- | --- | --- | --- |
| *One Up on Wall Street* | Peter Lynch with John Rothchild | Fireside edition | 1989 |
| *Beating the Street* | Peter Lynch with John Rothchild | 1st edition | 1993 |

## The five rules

| # | Rule | Thresholds | Source |
| --- | --- | --- | --- |
| 1 | PEG = P/E ÷ earnings growth | PASS ≤ 1.0 · WATCH ≤ 1.5 · FAIL > 1.5 | *One Up on Wall Street*, ch. on the perfect stock |
| 2 | Earnings growth consistency | PASS ≥ 7 of 10 years · WATCH 5-6 · FAIL < 5; INSUFFICIENT < 10 years | *One Up on Wall Street*, ch. on the stable stalwarts |
| 3 | Debt conservatism | PASS ≤ 2.0x net income · WATCH ≤ 4.0x · FAIL > 4.0x | *One Up on Wall Street*, ch. on the balance sheet |
| 4 | Inventory watch | PASS if inventory growth ≤ sales growth · WATCH ≤ 1.5x sales growth · FAIL > 1.5x; no inventory reported → WATCH with a note | *One Up on Wall Street*, ch. on checking the story |
| 5 | Dividend-adjusted PEG (PEGY = PEG ÷ (1 + dividend yield)) | Same bands as rule 1; only evaluated for dividend payers | *Beating the Street*, ch. on dividend-adjusted valuations |

Only rules 1-3 count towards the verdict; rules 4-5 feed confidence, score
and red flags but never change the verdict.

## Verdict logic

- **BUY** — rule 1 PASS **and** rule 2 PASS **and** rule 3 PASS.
- **WATCH** — 2 of {1, 2, 3} PASS.
- **HOLD** — 1 of {1, 2, 3} PASS.
- **AVOID** — any of {1, 2, 3} FAIL, or fewer than 1 PASS.
- **INSUFFICIENT_DATA** — more than 2 of the verdict rules are
  INSUFFICIENT_DATA.

## Score formula

```
score = (rules passed / rules evaluable) × 100
```

`evaluable` = a rule that returned PASS, WATCH or FAIL (not
INSUFFICIENT_DATA), across all five rules. `score` is `None` when fewer than
2 rules are evaluable (rendered as "—", never as 0).

Confidence: **HIGH** when all 5 rules are evaluated, **MEDIUM** with 1-2
INSUFFICIENT_DATA, **LOW** with 3 or more.

## Red flags (verbatim from the books)

- PEG above 1.5 (paying too much for growth)
- Earnings declined in 4+ of the last 10 years
- Long-term debt above 4x net income
- Inventory growing 50% faster than sales

## Data notes

- P/E uses the latest fiscal year's EPS (net income ÷ shares outstanding).
- Earnings growth is a geometric CAGR of net income over the available
  profitable years because that is the series the repository can actually
  reproduce.
- Rule 3 prefers `long_term_debt` and falls back to `total_debt` when it is
  not reported (stricter than the book's long-term-debt-only comparison).
- Rule 4 reads the optional `inventory` field of `NormalizedFinancials`;
  companies that do not report inventory (service, asset-light) get a WATCH
  with a note.
- Prices come in through the price adapter and are never persisted.

## Financial companies

Lynch's rules assume a product company: growth is measured on earnings, debt
is compared against the earnings a shareholder can actually see, and
inventory is part of the story. Banks, insurers and other financials have a
structurally different balance sheet — high leverage, no inventory — so
`lynch_garp` detects them and returns **INSUFFICIENT_DATA** with confidence
HIGH instead of forcing a verdict.

Detection (`backend/methodologies/common/company_type.py::is_financial`, any signal suffices):

1. `sector` field (when present) is a financial industry.
2. No inventory reported **and** (long-term) debt is more than 5x net income.
3. Bank-like balance sheet: `total_liabilities / total_assets > 0.85`.
4. Positive net income with non-positive operating cash flow and no reported
   capital expenditure (bank cash-flow fingerprint).

For a company that trips the detector the score is `None`, no rules are
evaluated, and the reason explains that the GARP rules do not apply.

## Known limitations

1. **Does not apply to financials** — no inventory line, and the debt model
   of a bank is not Lynch's book model.
2. **Growth rate estimation** — the quality of the PEG hinges on the earnings
   CAGR, which depends on the source and span of the data.
3. **Company categorization** — Lynch expects the investor to first classify
   the company (fast grower, stalwart, slow grower, cyclical, turnaround,
   asset play) and then choose the appropriate yardstick; this implementation
   applies the same rules to every company.
4. Rule 2 needs at least 10 fiscal years; younger histories return
   INSUFFICIENT_DATA.

## Distinction vs the other methodologies

| Methodology | Family | Focus |
| --- | --- | --- |
| `graham` | DEEP_VALUE | Defensive value; no growth emphasis |
| `buffett_classic` | QUALITY_COMPOUNDER | 4-pillar quality moat |
| `buffett_clark` | QUALITY_COMPOUNDER | Financial-statement quality |
| `graham_dodd` | DEEP_VALUE | Balance-sheet deep value |
| `fisher_quantitative_subset` | QUALITY_COMPOUNDER | R&D / margin quality |
| `lynch_garp` | GARP | Growth at a reasonable price — the missing middle |

Lynch fills the gap between the deep-value screens (which underweight growth)
and the quality compounders (which rarely demand a low multiple): he is
willing to pay a multiple for growth, but only a reasonable one (PEG ≤ 1).