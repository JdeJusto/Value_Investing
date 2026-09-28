# Buffett/Clark Methodology

**Book:** *Warren Buffett and the Interpretation of Financial Statements* by Mary Buffett & David Clark (2001)

Detects durable competitive advantage (DCA) from financial-statement signatures.

## Rules

| # | Rule | Threshold | Source |
|---|------|-----------|--------|
| 1 | Gross margin | ≥ 40% = DCA; < 20% = competitive | p. 55–56 |
| 2 | Interest burden | ≤ 10% of operating income = DCA | p. 73–74 |
| 3 | Margin durability | Stable/rising over 5+ years | p. 56 |
| 4 | Debt | Low debt/equity = DCA indicator | p. 38, 41 |
| 5 | Cash | High cash = DCA indicator | p. 41 |
| 6 | Capex | Low capex/FCF = DCA indicator | p. 41 |
| 7 | Retained earnings | Rising = compounding value | p. 34 |

## Verdict Logic

- **BUY**: ≥ 5 of 7 rules pass
- **WATCH**: 4 of 7 pass
- **HOLD**: 3 of 7 pass
- **AVOID**: < 3 pass

## Score

`score = (passed / 7) × 100`

## Confidence

- **HIGH**: all 7 rules evaluated
- **MEDIUM**: 1–2 rules unknown
- **LOW**: > 2 rules unknown

## Relationship to the Existing Buffett Module

There is an existing implementation at `backend/intelligence/buffett.py` that
implements a 4-pillar Buffett filter. This is **different** from Buffett/Clark's
financial-statement-based rules.

- `backend/intelligence/buffett.py`: qualitative 4-pillar filter, broader
  Buffett/Munger philosophy.
- `backend/methodologies/buffett_clark/`: book-specific rules from Mary Buffett
  & David Clark's *Warren Buffett and the Interpretation of Financial Statements*.

Both coexist. Reports may show them under different names:
- `buffett` (existing)
- `buffett_clark` (new)

## Known Limitations

- Gross margin thresholds calibrated to US industrials; SaaS may structurally differ.
- Interest burden examples are US airlines/tires from 2001.
- No valuation method — the book explains how to find DCA companies but not how to value them.
- Margin durability requires 5+ years of data; companies with shorter histories get INSUFFICIENT_DATA for that rule.
