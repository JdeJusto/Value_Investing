# Number formatting policy (v0.11.0)

Large numbers in the Analysis page are abbreviated for readability
(`$416.16B` instead of `$416,161,000,000`). **Abbreviation is a display
concern**: the underlying facts and every computed value are unchanged.

## Where abbreviations apply

| Surface | Format | Why |
| --- | --- | --- |
| Financials tables (year columns) | abbreviated | reading view |
| Financials Summary panel (Latest/Average) | abbreviated | reading view |
| Alerts evidence (UI sidebar) | abbreviated | reading view |
| Overview tab (price, market cap) | compact (`$3.87T`) | already `fmt_money_short` |
| Raw tab | **full precision** | reference view |
| CLI (`financial-alerts`, `analyze-*`) | **full precision** | copy/paste into spreadsheets |
| Statement previews (from filings) | filing's own strings | the filing's units, left as-is |
| CSV exports | matches the visible UI (abbreviated) | exports what you see |

The services take an `abbreviate: bool = False` display-mode parameter:
the UI callers pass `True`, the CLI keeps the default (full precision).
The demo fixtures are generated abbreviated (they feed the UI only).

Not feasible in this session: a secondary "export full precision" button
(the full-precision rows are no longer kept alongside the display rows;
the CLI and the Raw tab are the full-precision references).

## Rules

| Range | Format | Example |
| --- | --- | --- |
| 0 | `0` | `0` |
| \|v\| < 1e3 | full, 2 decimals | `$42.15` |
| 1e3 – 1e6 | K | `$1.00K` |
| 1e6 – 1e9 | M | `$1.00M` |
| 1e9 – 1e12 | B | `$416.16B` |
| 1e12 – 1e15 | T | `$3.87T` |
| >= 1e15 | scientific | `$4.5e+15` |

- Currency (`USD`): `$` prefix. Other units: no prefix; `shares` gets the
  `sh` suffix (`14.78B sh`); `percent`/`pure` are already short and are
  **not** abbreviated (`24.0%`, `0.1543`).
- Negatives use the accounting parentheses convention, consistently:
  `($19.00B)`, `($42.15)` (chosen over `-$19.00B`; matches the statement
  convention used by `format_fact_value`).
- `None` -> `—` (em dash, the existing convention).
- Rounding at the boundary is accepted: `999,999` -> `$1.00M`.
- Per-share values are small and render with 2 decimals: `$7.39`.

## Functions

`backend/services/ui_format.py`:

```python
abbreviate_number(value, unit="USD", decimals=2)  # with $ / sh suffix
abbreviate_value(value, unit, decimals=2)  # no currency symbol
```

The existing `format_fact_value` / `format_metric_value` / `fmt_or_dash`
formatters stay (full precision); callers choose. `format_metric_value`
and the view/insights/alerts builders accept `abbreviate` and route
through `abbreviate_number` for currency/per-share/share kinds.

## Verified edge cases

`0` -> `0` · `42` -> `$42.00` · `999` -> `$999.00` · `1_000` -> `$1.00K`
· `999_999` -> `$1.00M` · `1_000_000` -> `$1.00M` · `1_000_000_000` ->
`$1.00B` · `416_161_000_000` -> `$416.16B` · `-19_001_000_000` ->
`($19.00B)` · `14_776_353_000` (shares) -> `14.78B sh` · `None` -> `—` ·
`0.24` (percent) -> `24.0%`.
