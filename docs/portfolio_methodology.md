# Portfolio columns and signals

`vi portfolio view` shows one row per open position. This page explains where
each value comes from so a high `Buffett score` next to a `HOLD` signal is not
misread as a contradiction.

| Column | Source | Meaning |
|---|---|---|
| `Ticker` | `data/portfolio.json` | Position identifier |
| `Sector` | FDB `companies.sector`, mapped to GICS labels | `Consumer Defensive` → `Consumer Staples`, `Consumer Cyclical` → `Consumer Discretionary`, `Technology` → `Information Technology`; missing → `Unknown` |
| `Qty` / `Price` / `Value` / `Return` | Position + refreshed price | Shares, current price, market value and unrealized return |
| `Buffett score` | `buffett_classic` methodology | **Score 0-100, not a verdict.** The methodology verdict is available in `vi scorecard`. |
| `Moat` | Moat analysis | `WIDE` / `STRONG` / `WEAK` (informational) |
| `Signal (screener)` | `backend/screener/signals.py::generate_signal` | Portfolio-level screener signal, combining rank, composite score, confidence and a Buffett floor. **Not** the Buffett verdict. |
| `Opp.` | Opportunity engine | Opportunity type, when detected |

## Why PDD shows Buffett 47 + HOLD

The two values answer different questions:

- **Buffett score 47** is the 0-100 score of the `buffett_classic` rules. The
  methodology's own verdict bands (0.50 / 0.70 / 0.85) are applied in the
  scorecard, where a 0.47 score is an `AVOID`.
- **Signal (screener) HOLD** comes from `generate_signal`:
  - `AVOID` only when `buffett_score < 40` (the screener's coarse floor);
  - `BUY` when rank ≥ 75, composite ≥ 70, confidence HIGH/MEDIUM and
    Buffett ≥ 50 (with LOW confidence: rank ≥ 80, composite ≥ 75);
  - `WATCHLIST` when rank ≥ 60;
  - otherwise `HOLD`.

A 47 score clears the screener's `< 40` floor but does not clear the Buffett
methodology's 50-point AVOID band. With a rank below 60, the screener says
`HOLD`. There is no threshold bug; the old headers (`Buffett`, `Signal`) hid
which system produced each number. They are now `Buffett score` and
`Signal (screener)`.

## Thesis

`thesis` is an optional field on each position (`null`/missing = none). It is
not part of the schema migration: existing portfolios load unchanged.

```bash
vi portfolio thesis HSY --set "Strong brand, pricing power, chocolate moat"
vi portfolio thesis HSY --show
vi portfolio thesis HSY --set-from-file ~/theses/HSY.md
vi portfolio thesis HSY --clear
```

The interactive menu exposes the same flow under **Portfolio → [6] Thesis**
(select position → set/clear → text). `vi portfolio view` prints a 48-character
preview per position; `--show` prints the full text.

## Sector exposure

`vi portfolio performance` groups by the canonical sector above, weighted by
market value. Missing metadata is grouped as `Unknown`, never as `N/A`. The
sector is read once per ticker from FDB and cached for the service lifetime;
a database outage degrades to `Unknown` instead of failing the page.
