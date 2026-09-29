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
| 4 | Inventory watch | PASS if inventory growth ≤ sales growth · WATCH ≤ 1.5x sales growth (1.25x for fast growers) · FAIL above; no inventory reported → WATCH with a note | *One Up on Wall Street*, ch. on checking the story |
| 5 | Dividend-adjusted PEG (PEGY = PEG ÷ (1 + dividend yield)) | Same bands as rule 1; only evaluated for dividend payers | *Beating the Street*, ch. on dividend-adjusted valuations |

Only rules 1-3 count towards the verdict; rules 4-5 feed confidence, score
and red flags but never change the verdict.

## Company categories (One Up on Wall Street, ch. 6)

Lynch insists on categorizing a company *before* judging it: the same numbers
mean different things for a fast grower and for a slow grower. The screen
types every company with the first matching rule (precedence:
**Turnaround > Fast Grower > Cyclical > Asset Play > Stalwart > Slow Grower >
UNKNOWN**) and records it as `metrics["lynch_category"]`.

| Category | Detection | Success criteria | Verdict thresholds |
| --- | --- | --- | --- |
| **Fast Grower** | revenue CAGR ≥ 20%, positive EPS in ≥ 4 of 5 years, net margin > 0, and (market cap ≥ $10B or CAGR ≥ 25%) | hyper growth with margins | generic logic; inventory watch tightened to 1.25x; above 30% growth the PEG band gets a +0.2 premium |
| **Stalwart** | revenue CAGR 8-20%, market cap ≥ $10B, positive earnings in ≥ 4 of 5 years | steady growth at a reasonable PEG | generic logic (unchanged) |
| **Slow Grower** | revenue CAGR 0-8%, dividends in ≥ 5 of 5 years, market cap ≥ $10B | stable dividends, no earnings decline | **BUY** if the dividend did not decline in ≥ 4 of 5 years and the net margin is stable; **WATCH** if the dividend was paid every year; **HOLD** otherwise; a core-rule FAIL caps at WATCH. A low PEG is *not* required |
| **Cyclical** | sector Basic Materials / Energy / Industrials (or Consumer Cyclical) **and** earnings volatility (σ/mean) > 0.5 over 10 years | buying near the trough | generic logic + a "check position in the cycle" warning in the reasons |
| **Turnaround** | net income negative in ≥ 2 of the last 5 years **and** improving | debt reduction and earnings recovery | PEG is relaxed: a negative-growth PEG reads INSUFFICIENT_DATA (not FAIL) while the recovery is unproven |
| **Asset Play** | P/BV < 0.7 and no compounder-grade earnings growth | discount to net asset value | rule 1 is replaced by P/BV: PASS < 0.7, WATCH < 1.0, FAIL ≥ 1.0 |
| **UNKNOWN** | nothing matches (or the inputs are missing) | — | generic logic with the PEG rule |

Rule 1 substitutions are recorded as `metrics["rule_1_criterion"]` (`peg`,
`dividend_stability`, `price_to_book`, `turnaround_peg`). Rule 1 for slow
growers is a dividend-stability test (PASS when the dividend was paid in ≥ 9
of the last 10 years, WATCH 7-8, FAIL below); for asset plays it is the P/BV
test above. All other categories keep the PEG rule.

## Verdict logic

- **BUY** — rule 1 PASS **and** rule 2 PASS **and** rule 3 PASS.
- **WATCH** — 2 of {1, 2, 3} PASS.
- **HOLD** — 1 of {1, 2, 3} PASS.
- **AVOID** — any of {1, 2, 3} FAIL, or fewer than 1 PASS.
- **INSUFFICIENT_DATA** — more than 2 of the verdict rules are
  INSUFFICIENT_DATA.

**Slow growers are the exception**: their verdict follows the category
thresholds above (dividend stability + margin stability, never PEG), because
Lynch does not ask a mature dividend payer for growth. Their score is hidden
(see Score formula).

## Score formula

```
score = (rules passed / rules evaluable) × 100
```

`evaluable` = a rule that returned PASS, WATCH or FAIL (not
INSUFFICIENT_DATA), across all five rules. `score` is `None` when fewer than
2 rules are evaluable (rendered as "—", never as 0).

**Slow Growers and Asset Plays show no score**: their Rule 1 is not the PEG
(dividend stability / P/BV), so the generic passed/evaluable ratio is not
comparable across categories and is hidden (rendered as "—", with a
`score_note` metric explaining why) rather than inventing a formula the book
does not define. The verdict and the category carry the judgment.

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
3. **Company categorization** — the screen categorizes companies into Lynch's
   six types from growth, dividends, sector and market cap; when sector or
   market cap are missing the company falls back to UNKNOWN and the generic
   PEG screen applies. The categorization is a documented heuristic, not
   Lynch's qualitative judgment.
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