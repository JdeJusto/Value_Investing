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

## Verdicts (weighted rank + overlay)

The ranking remains the primary input. The verdict is the weighted pass ratio
of the rank checks (in file, top 50, top 100), the ROC / earnings-yield
decomposition and a quality overlay:

| Weighted score | Verdict |
| --- | --- |
| ≥ 0.85 | BUY |
| 0.70–0.85 | WATCH |
| 0.50–0.70 | HOLD |
| < 0.50 | AVOID |

More than 30% of the weighted rules missing data returns INSUFFICIENT_DATA;
weight-0 rules (capital turnover, bank scope guard) never enter the score.
The full table, sources (`page="public knowledge"` — the book was not
available) and data limits are in `docs/greenblatt_rules.md`.

INSUFFICIENT_DATA also when: the ranking file is missing, empty or older than
14 days; the ticker is in the universe but not in the file; or the stored
ROC/EY is not positive. Tickers outside the S&P 500 ranking universe and
financials/REITs return N/A.

## Usage

```bash
python main.py analyze-greenblatt AAPL
python main.py compare-methodologies AAPL   # greenblatt is the 7th row
```

## Known limitations

- The rankings must be refreshed periodically (weekly recommended); a stale
  file (> 14 days) reads INSUFFICIENT_DATA. The file is refreshed weekly by
  the user-level systemd timer `greenblatt-rankings.timer` (Monday 06:00);
  manual run: `systemctl --user start greenblatt-rankings.service`.
- Filers without a `PropertyPlantAndEquipmentNet` tag are excluded from the
  ranking (net fixed assets cannot be computed).
- Financials abstain (shared company-type detector).
