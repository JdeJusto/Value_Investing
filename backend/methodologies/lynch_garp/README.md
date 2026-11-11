# Lynch GARP (Growth At a Reasonable Price) — v2.0.0

A self-contained book methodology implementing Peter Lynch's quantitative
GARP screen. Registered automatically with the methodologies registry as
`lynch_garp` — it is **one column** in the comparison table, never a
contributor to the composite score.

## Books and availability

| Book | Author | Year |
| --- | --- | --- |
| *One Up on Wall Street* | Peter Lynch with John Rothchild | 1989 |
| *Beating the Street* | Peter Lynch with John Rothchild | 1993 |

**Neither book was found on this machine** (see
`docs/books_notes/one-up-on-wall-street.md`). Every rule is a
**public-knowledge reconstruction** labelled `page="public knowledge"`; no
quote, page number or page-level paraphrase is claimed.

## The rules

v2.0.0 keeps the five original rules and adds 19 deep checks. All 24 feed the
shared weighted verdict (BUY ≥ 0.85, WATCH ≥ 0.70, HOLD ≥ 0.50, > 30% missing
weight => INSUFFICIENT_DATA). The full table and formulas are in
`docs/lynch_garp_rules.md`.

| # | Rule | Thresholds | Weight |
| --- | --- | --- | ---: |
| 1 | PEG = P/E ÷ earnings growth | PASS ≤ 1.0 · WATCH ≤ 1.5 · FAIL > 1.5 | 2 |
| 2 | Earnings growth consistency | PASS ≥ 7 of 10 years · WATCH 5-6 · FAIL < 5 | 2 |
| 3 | Debt conservatism | PASS ≤ 2.0x net income · WATCH ≤ 4.0x · FAIL above | 2 |
| 4 | Inventory watch | PASS if inventory growth ≤ sales growth; no inventory → WATCH note | 1 |
| 5 | Dividend-adjusted PEG (PEGY) | Same bands as rule 1; only dividend payers | 1 |
| 6-24 | Deep checks | PEG/PE/growth, health, valuation and the six category profiles | 1-2 |

Legacy outcomes map to the weighted framework as: `PASS` -> passed,
`WATCH`/`FAIL` -> not passed (conservative), `INSUFFICIENT_DATA` -> missing
(`passed=None`). The old "any core FAIL => AVOID" gate is gone: the verdict is
the weighted ratio.

## Company categories

The six categories are unchanged. The screen types every company with the
first matching rule (precedence: **Turnaround > Fast Grower > Cyclical >
Asset Play > Stalwart > Slow Grower > UNKNOWN**) and records it as
`metrics["lynch_category"]`.

| Category | Detection | Category-specific deep rule |
| --- | --- | --- |
| **Fast Grower** | revenue CAGR ≥ 20%, positive EPS in ≥ 4 of 5 years, net margin > 0 (no size gate) | revenue CAGR 20-25% **and** PEG < 0.5 |
| **Stalwart** | revenue CAGR 8-20%, market cap ≥ $10B, positive earnings in ≥ 4 of 5 years | revenue CAGR 10-12% **and** P/E < 15 |
| **Slow Grower** | revenue CAGR 0-8%, dividends in all 5 years, market cap ≥ $10B | yield > 5% **and** payout < 80%; dividend paid in ≥ 4 of 5 years |
| **Cyclical** | cyclical sector keyword **and** earnings volatility (σ/mean) > 0.5 over 10 years | no inventory build **and** P/E ≤ 15 |
| **Turnaround** | net income negative in ≥ 2 of the last 5 years **and** improving | debt down YoY **and** FCF > 0 |
| **Asset Play** | P/BV < 0.7 and no compounder-grade earnings growth | P/B < 1 **and** tangible assets ≥ 50% of market cap |
| **UNKNOWN** | nothing matches (or the inputs are missing) | generic rules only |

Rule 1 keeps its category substitution (`metrics["rule_1_criterion"]`:
`peg`, `dividend_stability`, `price_to_book`, `turnaround_peg`). Only the
ticker's own category rule enters the weighted denominator; the other five
remain visible as `N/A`.

## Score and confidence

```
weighted_score = sum(weight for passed) / sum(weight for evaluable)
```

`evaluable` excludes `N/A` rules and weight-0 rules. The score is shown for
every category (the old `score_note` hiding is gone; the category-specific
rules now make the score comparable). Confidence is HIGH with no missing
weight, MEDIUM up to 10%, LOW above that; more than 30% missing returns
INSUFFICIENT_DATA.

## Red flags (legacy, unchanged)

- PEG above 1.5 (paying too much for growth)
- Earnings declined in 4+ of the last 10 years
- Long-term debt above 4x net income
- Inventory growing 50% faster than sales

Deep-check failures are appended as red flags too.

## Data notes

- P/E uses the latest fiscal year's EPS (net income ÷ split-adjusted shares).
- Earnings growth is a geometric CAGR of net income over the available
  profitable years.
- Rule 3 prefers `long_term_debt` and falls back to `total_debt`.
- Rule 4 reads the optional `inventory` field; no inventory is a WATCH note.
- The own-history P/E rules use a constant-price proxy (FDB has no period-end
  dates and the batch pipeline fetches no point-in-time price history).
- Prices come in through the price adapter and are never persisted.

## Financial companies

Banks, insurers and other financials have a structurally different balance
sheet (high leverage, no inventory), so `lynch_garp` detects them and returns
**NOT_APPLICABLE** with confidence HIGH instead of forcing a verdict.
Detection lives in `backend/methodologies/common/company_type.py`
(`is_financial`).

## Known limitations

1. Does not apply to financials.
2. Growth-rate estimation depends on the source and span of the data.
3. Company categorization is a documented heuristic, not Lynch's qualitative
   judgment; missing inputs fall back to UNKNOWN.
4. Rule 2 needs at least 10 fiscal years.
5. The books were unavailable: no page-level fidelity is claimed.
6. The own-history P/E rules are constant-price approximations.
