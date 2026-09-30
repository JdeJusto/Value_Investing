# greenblatt — Magic Formula (cross-sectional)

Joel Greenblatt's Magic Formula from *The Little Book That Beats the Market*
(2005): rank a universe by **return on capital** and **earnings yield**, buy
the best combined ranks.

## Rules

| # | Rule | Formula | Source |
| --- | --- | --- | --- |
| 1 | Return on Capital | `EBIT / (max(current assets − current liabilities, 0) + net PPE)` | ch. 3, the Magic Formula |
| 2 | Earnings Yield | `EBIT / (market cap + total debt − cash)` | ch. 3, the Magic Formula |
| 3 | Combined Rank | `rank_ROC + rank_EY` (lower is better) | ch. 4, ranking the universe |

## Cross-sectional design

The Magic Formula is inherently **cross-sectional**: a company's score is its
rank inside a universe. The framework evaluates one ticker at a time, so the
rankings are pre-computed by a script:

```bash
python -m scripts.compute_greenblatt_rankings --universe sp500   # weekly
```

The script writes `data/rankings/greenblatt_<YYYY-MM-DD>.json`
(`rank_roc`, `rank_ey`, `combined_rank`, `percentile`, `roc`,
`earnings_yield` per ticker; idempotent within a day). The methodology reads
the newest file — it never touches the network or the database itself.

## Verdicts (percentile, lower is better)

| Percentile | Verdict |
| --- | --- |
| ≤ 10% | BUY |
| ≤ 30% | WATCH |
| ≤ 50% | HOLD |
| > 50% | AVOID |

`score = (1 − percentile) × 100`. INSUFFICIENT_DATA when: the ticker is a
financial (the ROC denominator assumes an industrial balance sheet), the
ranking file is missing or older than 30 days, the ticker is not in the
file, or the stored ROC/EY is not positive.

## Usage

```bash
python main.py analyze-greenblatt AAPL
python main.py compare-methodologies AAPL   # greenblatt is the 7th row
```

## Known limitations

- The rankings must be refreshed periodically (weekly recommended); a stale
  file (> 30 days) reads INSUFFICIENT_DATA.
- Filers without a `PropertyPlantAndEquipmentNet` tag are excluded from the
  ranking (net fixed assets cannot be computed).
- Financials abstain (shared company-type detector).
