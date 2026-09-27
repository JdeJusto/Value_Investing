# Graham — defensive investor methodology

Implementation of the seven quantitative criteria from **Chapter 14** of
*The Intelligent Investor* (Benjamin Graham, 4th revised edition 1973, with
Jason Zweig's commentary), plus the combined valuation test from the same
chapter.

## Sources

| Rule | Book location | Page reference |
|---|---|---|
| 1. Adequate size | Ch. 14, criterion 1 | "un mínimo de 100 millones de dólares de ventas anuales… no menos de 50 millones de dólares de activo total" |
| 2. Strong financial condition | Ch. 14, criterion 2 | current ratio ≥ 2:1; long-term debt ≤ net working capital |
| 3. (see rule 2) | Ch. 14, criterion 2 | debt limit expressed against working capital |
| 4. Dividend record | Ch. 14, criterion 4 | ≥ 20 years of uninterrupted dividends |
| 5. Earnings growth | Ch. 14, criterion 5 | ≥ 1/3 growth per share over 10 years, 3-year averages |
| 6. Moderate P/E | Ch. 14, criterion 6 | price ≤ 15× average earnings of the last 3 years |
| 7. Moderate P/BV | Ch. 14, criterion 7 | price ≤ 1.5× latest book value |
| 8. Combined test | Ch. 14, criterion 7 | P/E × P/BV ≤ 22.5 |

## The eight rules

1. **Size** — revenue ≥ $100M (industrial) or total assets ≥ $50M (utility).
2. **Current ratio** — current assets / current liabilities ≥ 2.0.
3. **Debt vs working capital** — long-term debt ≤ net working capital.
4. **Dividend history** — dividends paid every year for ≥ 20 years.
5. **Earnings growth** — EPS up ≥ 1/3 over a decade, using 3-year averages of
   the endpoints.
6. **P/E** — price ≤ 15× average earnings of the last 3 years.
7. **P/BV** — price ≤ 1.5× book value per share.
8. **Combined** — P/E × P/BV ≤ 22.5. Exposed both as a gate and as a metric
   (Decision 3 of `docs/methodology_decisions.md`).

## Verdict logic

| Condition | Verdict |
|---|---|
| ≥ 6 of the 7 criteria PASS **and** rule 8 passes | BUY |
| 5 or 6 PASS | WATCH |
| < 5 PASS | AVOID |
| > 2 criteria INSUFFICIENT_DATA | INSUFFICIENT_DATA |

## Score

`score = (passed_count / 7) * 100`, rounded to 2 decimals.
`score = None` when the verdict is INSUFFICIENT_DATA (Decision 10 — a
methodology without a numeric scale must not be reduced to a number).

## Confidence

- **HIGH** — all 7 criteria evaluated, no INSUFFICIENT_DATA.
- **MEDIUM** — 1 or 2 criteria INSUFFICIENT_DATA.
- **LOW** — more than 2 INSUFFICIENT_DATA (verdict INSUFFICIENT_DATA).

## Era adjustment (Decision 4)

`era_adjustment: bool = False` by default — strict fidelity to the book.

When `True`, only the **size** threshold is rescaled:

| | Book value (1973) | Modernized |
|---|---|---|
| Industrial sales | $100M | $560M (× 5.6) |
| Utility assets | $50M | $280M (× 5.6) |

The factor is the CPI ratio 2024/1973 ≈ 5.6 (US CPI, 1973 annual average ≈ 44.4;
2024 ≈ 255.6). It is applied to the size criterion **only** — the valuation
thresholds (P/E 15, P/BV 1.5, product 22.5) and the growth threshold are left
untouched, because they are already relative rather than absolute.

The methodology is labelled `graham_modernized` in reports when the adjustment
is on, so "Graham 1949" and "Graham modernized" can be compared side by side.

## Known limitations

1. **Criterion 2 (current ratio) is not evaluable.**
   `NormalizedFinancials` stores `working_capital` (current assets − current
   liabilities) but **not** the two components separately, so the 2:1 test
   cannot be computed from the canonical VO. The rule returns
   `INSUFFICIENT_DATA` rather than guessing. A future change to the VO or a
   repository method returning the split would unlock it.
2. **Criterion 3 uses `total_debt`** as a proxy for long-term debt. Since
   total debt ≥ long-term debt, the test is **stricter** than the book's — a
   company with large short-term debt fails even if its long-term debt is
   within working capital. Conservative by design.
3. **Criterion 4 counts years with `dividends_paid > 0`.** A missing cash-flow
   statement reads as "no dividend", so a company with an incomplete history
   may fail on data availability rather than on policy.
4. **Criterion 4 is currently blocked by an empty table.** Financial-DataBase's
   `dividends` table has **0 rows**, so no company can pass this criterion
   until dividend data is ingested. This is a data gap, not a methodology gap.
5. **Uses fiscal-year data** and the latest available price; intraday moves are
   not considered.
6. **Banks and financials do not fit** — the balance-sheet criteria were written
   for industrials and utilities, and the book itself excludes financial
   companies from the defensive screen.
7. **No sell rule.** The criteria are entry screens; Graham gives no mechanical
   exit, and this implementation does not invent one.
8. **Shares outstanding** are read from the balance-sheet concepts
   (`CommonStockSharesOutstanding` / `EntityCommonStockSharesOutstanding`) via
   the repository's concept mapping. Most filers provide them, but companies
   without those concepts return `None`, which makes criteria 6 and 7
   INSUFFICIENT_DATA rather than failing.
