# DCF Valuation (`backend/valuation/`) — `not-from-canon`

**This module is NOT part of any book-derived methodology. It is labeled
`not-from-canon` because the canon books (Graham, Fisher, Buffett,
Graham & Dodd) predate modern growth-company economics and never proposed a
DCF as a primary valuation tool. The DCF here is a practical addition, not a
rule from any book.**

The five methodologies (`graham`, `buffett_classic`, `buffett_clark`,
`graham_dodd`, `fisher_quantitative_subset`) systematically reject
high-multiple compounders like AAPL or MSFT because their source books
predate software/network economics. `backend/valuation/` is a separate
namespace that answers a different question: *what is this company actually
worth?*

---

## Why it does NOT become a methodology (design decision)

* It lives in `backend/valuation/`, **not** `backend/methodologies/`, so the
  methodology registry (`discover()`) and auto-discovery can never see it.
* Its output is labeled `source="not-from-canon"` everywhere:
  - the `DCFResult` dataclass field,
  - the CLI header (`dcf AAPL` renders "... (not-from-canon)"),
  - this README,
  - any future report that includes it.
* It never feeds `compare-methodologies`, `methodologies list`, or any
  composite score. It is a supplementary tool, not a verdict that competes
  with Graham/Buffett.

---

## Assumptions (all constants, all overridable)

| Constant | Default | Meaning |
|---|---|---|
| `risk_free_rate` | `4.0%` | US 10y nominal proxy (documented) |
| `equity_risk_premium` | `5.0%` | Documented ERP assumption |
| `tax_rate` | `21.0%` | US statutory corporate rate |
| `terminal_growth` | `2.5%` | Long-run nominal growth (documented) |
| `max_growth_years_1_5` | `20%` | Cap on stage-1 growth |
| `max_growth_years_6_10` | `10%` | Cap on stage-2 growth |
| `wacc_override` | `None` | CLI `--wacc` (skip WACC model) |
| `growth_override` | `None` | CLI `--growth` (skip CAGR model) |

Every default lives in `DCFAssumptions` (frozen dataclass) and can be
replaced before calling `evaluate`; the CLI exposes `--wacc`, `--growth`,
`--terminal-growth`.

---

## Formula (step by step)

1. **FCF base** — average of the newest 3 usable fiscal years, where
   `FCF = operating_cash_flow - capex` (or the filed `free_cash_flow` tag
   when present, which wins). Falls back to the latest year when fewer rows
   exist. **Negative FCF ⇒ `INSUFFICIENT_DATA`** ("cash-burning companies").
2. **Growth years 1-5** — min(historical 5-year revenue CAGR, 20%).
3. **Growth years 6-10** — min(stage-1 growth / 2, 10%).
4. **Terminal growth** — fixed `2.5%` per stage.
5. **WACC** —
   `cost_of_equity = risk_free_rate + beta * equity_risk_premium` (beta from
   the price service; `1.0` when unavailable),
   `cost_of_debt = interest_expense / total_debt` (else `cost_of_equity`),
   `wacc = E/V * CoE + D/V * CoD * (1 - tax_rate)`,
   weights from `market_cap` (fallbacks: `price * shares`, then book equity).
   **WACC ≤ terminal growth ⇒ `INSUFFICIENT_DATA`.**
6. **Project 10 years** of FCF at stage-1 then stage-2 growth.
7. **Terminal value** = `FCF_10 * (1 + terminal_growth) / (wacc - terminal_growth)`,
   discounted at WACC along with the explicit 10 years.
8. **Intrinsic value per share** = PV sum / shares outstanding
   (split-adjusted).
9. **Margin of safety** = `(intrinsic - price) / intrinsic`, reported on a
   `[-10, +10]` band.

### Verdict thresholds

| Verdict | Margin of safety |
|---|---|
| `UNDERVALUED` | `>= +25%` |
| `FAIR` | between `-10%` and `+25%` |
| `OVERVALUED` | `<= -10%` |
| `INSUFFICIENT_DATA` | missing FCF / shares / price; negative FCF; financial company; WACC ≤ terminal growth |

### Sensitivity

A 3×3 grid of intrinsic value per share for `WACC ∈ {wacc-2%, wacc, wacc+2%}`
× `growth ∈ {g-2%, g, g+2%}` (stage-2 growth re-derived as half of the
grid growth, capped at 10%). Cells that are not well posed (WACC ≤ terminal
growth) render as `—`.

---

## Known limitations

* **Sensitive to WACC and growth assumptions** — the sensitivity grid exists
  precisely because a ±2% change in either can move the value materially.
* **Not applicable to negative-FCF companies** — a company that burns cash
  has no positive FCF stream to discount; the DCF returns `INSUFFICIENT_DATA`
  rather than fabricating one.
* **Not applicable to financials (banks, insurers)** — they book an
  interest-based top line and their operating cash flow is not free cash
  flow. The module treats a company as financial via two documented
  heuristics (not a taxonomy) and returns `INSUFFICIENT_DATA` with that
  reason:
  - interest expense ≥ 30% of revenue, or
  - positive net income with non-positive operating cash flow and no
    reported capital expenditure (the JPM fingerprint — its interest
    expense and capex are not reconstructed by the data layer).
  Sector-aware variants are future work.
* **The beta is often unavailable or stale** — when unavailable it falls back
  to `1.0` (documented in the reasons); when stale it underprices recent
  model risk.
* **Not a substitute for the canon** — it never competes with the
  book-derived verdicts; run `compare-methodologies` for those.

---

## CLI

```
python main.py dcf AAPL
python main.py dcf AAPL --wacc 0.10
python main.py dcf AAPL --growth 0.08
python main.py dcf AAPL --terminal-growth 0.03
```

The module is deterministic (pure arithmetic over data + an injected price
service) and never persists anything.