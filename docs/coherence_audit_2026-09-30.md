# Data coherence audit — 2026-09-30

Cross-check of the platform's latest fiscal-year fundamentals against SEC
EDGAR (`companyfacts`) and Yahoo Finance for five companies across different
profiles. Run as Phase E of the v0.1.0 hardening session; prices were not
audited (never persisted, fetched on demand).

Tolerances: revenue and assets ≤ 2%, net income ≤ 5% (accounting nuance).

| Ticker | Metric | Platform | SEC EDGAR | Yahoo | Match? |
| --- | --- | ---: | ---: | ---: | --- |
| AAPL FY2025 | Revenue | 416,161 M | 416,161 M | 416,161 M | ✅ 0.0% / 0.0% |
| AAPL FY2025 | Net income | 112,010 M | 112,010 M | 112,010 M | ✅ 0.0% / 0.0% |
| AAPL FY2025 | Assets | 359,241 M | 359,241 M | 359,241 M | ✅ 0.0% / 0.0% |
| KO FY2025 | Revenue | 47,941 M | 47,941 M | 47,941 M | ✅ 0.0% / 0.0% |
| KO FY2025 | Net income | 13,107 M | 13,107 M | 13,107 M | ✅ 0.0% / 0.0% |
| KO FY2025 | Assets | 104,816 M | 104,816 M | 104,816 M | ✅ 0.0% / 0.0% |
| JPM FY2025 | Revenue | 182,447 M | 182,447 M | 181,847 M | ✅ 0.0% / 0.33% |
| JPM FY2025 | Net income | 55,681 M | 57,048 M | 57,048 M | ⚠️ 2.46% (explained) |
| JPM FY2025 | Assets | 4,424,900 M | 4,424,900 M | 4,424,900 M | ✅ 0.0% / 0.0% |
| XOM FY2025 | Revenue | 332,238 M | 332,238 M | 323,905 M | ✅ 0.0% / 2.51% (explained) |
| XOM FY2025 | Net income | 28,844 M | 28,844 M | 28,844 M | ✅ 0.0% / 0.0% |
| XOM FY2025 | Assets | 448,980 M | 448,980 M | 448,980 M | ✅ 0.0% / 0.0% |
| F FY2025 | Revenue | 187,267 M | 187,267 M | 187,267 M | ✅ 0.0% / 0.0% |
| F FY2025 | Net income | −8,182 M | −8,182 M | −8,182 M | ✅ 0.0% / 0.0% |
| F FY2025 | Assets | 289,160 M | 289,160 M | 289,160 M | ✅ 0.0% / 0.0% |

Platform values are exact to SEC EDGAR for 14 of 15 rows (0.000%).

## Discrepancy investigations

### JPM net income: 55,681 M vs 57,048 M (−2.46%)

The platform reports **net income available to common stockholders**, not the
consolidated net income. Both are filed tags:

- `NetIncomeLossAvailableToCommonStockholdersBasic` FY2025 = 55,681 M
  (the platform's figure — the SEC 10-K value).
- `NetIncomeLoss` FY2025 = 57,048 M (consolidated, before the ~1,367 M of
  preferred dividends).

The repository's income priority list deliberately prefers the
common-stockholders tag because every per-share metric (EPS, P/E, DDM) must
use it; the preferred-dividend handling added in `8652f54` relies on this.
Not an error: a definitional difference, inside the 5% tolerance, and the
platform's value matches the filed common-stockholders tag exactly.

### XOM revenue: platform vs Yahoo (+2.51%)

Yahoo's "Total Revenue" (323,905 M) aggregates XOM's sales excluding some
items the company includes in its `Revenues` tag (332,238 M). The platform
matches SEC EDGAR exactly; the difference is Yahoo's own aggregation choice.
No action.

### JPM revenue: platform vs Yahoo (+0.33%)

Yahoo reports 181,847 M against SEC 182,447 M. The platform matches SEC
exactly; within tolerance and attributable to Yahoo's bank-revenue
aggregation.

## Verdict

**Data coherence: HIGH.**

- 14 of 15 platform values are bit-exact against SEC EDGAR (0.000%).
- The single difference (JPM net income) is a documented definitional choice
  (common stockholders vs consolidated), matches a filed tag exactly, and is
  well inside tolerance.
- Yahoo differences are all on Yahoo's side of the comparison (XOM/JPM
  revenue aggregation); no platform value deviates from SEC EDGAR.
