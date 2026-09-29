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

> The steps below describe the **`standard` variant** (free cash flow). The
> company-type dispatcher routes REITs, financials and hyper-growth names to
> their own variants; see [Variants](#variants).

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
| `INSUFFICIENT_DATA` | missing FCF / shares / price; negative FCF; WACC ≤ terminal growth; a variant with nothing honest to discount (see Variants) |

---

## Variants

`evaluate` dispatches on the **shared company-type detector**
(`backend/methodologies/common/company_type.py` — the same classifier the
Graham/Graham & Dodd/Buffett-Clark/Fisher/Lynch-GARP screens use, so the DCF
never disagrees with the methodologies about what a company is). The chosen
variant is recorded on `DCFResult.variant` and rendered by the CLI.

| Variant | Route | Cash flow discounted | Notes |
|---|---|---|---|
| `standard` | everything not typed below; also utilities | `FCF = OCF - capex` | the historical two-stage pipeline (Formulas above) |
| `reit` | sector hint `real estate` / `reit` | **Funds from operations** ≈ `net income + depreciation & amortization` | heavy depreciation makes FCF negative for healthy landlords; property-sale gains are not in the normalized VO, so they are omitted rather than guessed |
| `ddm_financial_two_stage` | sector hint financial/bank/insurance *or* financial fingerprint | **dividends per share**: stage 1 at the 5-year DPS CAGR (capped at 12%, 10 years), then terminal 2.5% | preferred for banks — stays defined when dividend growth exceeds the cost of equity (the JPM/WFC single-stage failure mode). Needs ≥3 dividend years; `coe = risk-free + beta × ERP` is the discount rate |
| `ddm_financial` | same route | **dividends per share** (single-stage Gordon) | fallback when the two-stage cannot be computed (no valid CAGR from the window) or growth is already ≤ terminal. **No dividend stream or fewer than 3 dividend years ⇒ `INSUFFICIENT_DATA`** |
| `hyper_growth` | 5y revenue CAGR > 25% **and** latest FCF negative | average of the **observed positive** FCF years in the 3-year window | cash-burning compounders; only real figures are averaged — still FCF-negative in every recent year ⇒ `INSUFFICIENT_DATA` |

Rules of the dispatcher:

* Nothing is ever fabricated — a variant that cannot be computed from the
  data (no FFO, no dividends, no positive FCF year) returns
  `INSUFFICIENT_DATA` naming the missing input.
* Non-variant logic is untouched: the standard body, `_project_value`,
  `_sensitivity`, `_verdict` and all assumptions are shared or unchanged.
* Prices are still fetched on demand through the price service and never
  persisted; the DDM additionally calls `get_beta` for its cost of equity.

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
  has no positive FCF stream to discount. The `standard` variant returns
  `INSUFFICIENT_DATA` rather than fabricating one. (Cash-burning **hyper-growth**
  names are the one exception: they route to the `hyper_growth` variant, which
  only ever averages FCF years that were actually positive.)
* **Financials, REITs and hyper-growth names use purpose-built variants, not
  the FCF pipeline** — a bank's operating cash flow is not free cash flow, a
  landlord's FCF is depressed by depreciation, and a compounder burns cash on
  purpose. The dispatcher detects each through the shared classifier (sector
  hint first, then the documented heuristics — *not a taxonomy*) and values
  them via the DDM / FFO / observed-positive-FCF variants above. When even the
  right variant has nothing real to discount, it returns `INSUFFICIENT_DATA`
  with the missing input named.
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