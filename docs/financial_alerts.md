# Financial alerts — design

Deterministic, data-driven alerts computed from the same facts the
Financials tab loads. **No LLM, no external service, no notifications:
rules only.** Each alert carries the evidence (the numbers) that triggered
it; a rule never fires on missing data (it is counted as skipped).

Status: **shipped in v0.10.1** (thresholds below are the ones in
`backend/services/alert_service.py`).

## Data flow

1. `FinancialsViewService.fetch_facts()` reads the company's FY facts once.
2. `FinancialInsightsService(facts).build()` derives the metric report.
3. `AlertService(facts).build(ticker, name)` runs the rule registry over
   the report — it does **not** re-read FDB nor recompute metrics.

To support the rules, `FinancialInsightsService` gained three metrics
(`operating_expenses`, `inventory`, `diluted_shares`) and `MetricInsight`
gained `series` (per-year values) and `yoy_pp` (percentage-point change for
percent-kind metrics).

## Rules

| # | rule_id | Severity | Condition | Evidence |
| --- | --- | --- | --- | --- |
| 1 | `low_cash_runway` | CRITICAL | `cash / (operating_expenses / 12) < 6` months | cash, opex, runway |
| 2 | `margin_collapse` | WARNING | gross or net margin dropped **> 5 pp** YoY | current, prior, Δpp |
| 3 | `debt_spike` | WARNING | D/E up **> 30%** YoY, or debt up **> 50%** with equity flat (≤10%) | ratios / growth |
| 4 | `inventory_buildup` | WARNING | inventory growth **> 10%** and **> 2× revenue growth** | both growths |
| 5 | `negative_fcf_streak` | WARNING | FCF < 0 for **2+** consecutive years | the FCF values |
| 6 | `revenue_decline` | INFO | revenue declined **2+** consecutive years | values + YoY |
| 7 | `earnings_quality` | INFO | net income **> 0** but OCF **< 0** | NI, OCF |
| 8 | `eps_dilution` | INFO | diluted shares up **> 5%** YoY | shares, growth |
| 9 | `dividend_cut` | WARNING | dividends down **> 20%** YoY (paid both years) | amounts, change |
| 10 | `strong_fcf_conversion` | INFO | FCF/NI **> 1.0** for **3** consecutive years | the ratios |

Rationale: the first five come from `docs/backlog.md` (the original plan);
6–8 catch slow deterioration and dilution; 9 protects income investors;
10 is the deliberate **positive** alert — a system that only warns is less
useful than one that also highlights what is working.

Tuning notes:
- Rule 4 requires inventory growth above **10%** (and above 2× revenue
  growth): real data showed a small inventory tick against a small revenue
  dip (TSLA +3.1% vs −2.9%) is not a buildup worth alerting on.
- Rule 2 can fire twice (gross and net) when both collapse; each alert
  names its margin.
- Percent-kind YoY (margins) is shown in percentage points, matching the
  Summary panel.

## Severity mapping

- **CRITICAL** — solvency risk (cash runway). The CLI exits 1 so shell
  chains can react (`financial-alerts AAPL || notify-send …`).
- **WARNING** — deterioration worth acting on (margins, debt, inventory,
  FCF streak, dividend cut).
- **INFO** — context and positives (revenue decline, earnings quality,
  dilution, strong FCF conversion).

Sorting: CRITICAL → WARNING → INFO; within a severity, by `rule_id`.

## Alert shape

```python
@dataclass(frozen=True)
class Alert:
    rule_id: str                # "low_cash_runway"
    severity: str               # "INFO" | "WARNING" | "CRITICAL"
    title: str                  # short human label
    message: str                # one-sentence explanation
    evidence: dict[str, str]    # formatted numbers that triggered it
    metric_hint: str | None     # "revenue", "net_margin", ...
    period: str                 # "FY2025"

@dataclass
class AlertsReport:
    ticker: str
    company_name: str
    alerts: list[Alert]
    rules_evaluated: int
    rules_skipped: int          # missing data — never a false positive
    warnings: list[str]
```

## Explicit non-goals (this session)

- No LLM, no summarization, no external calls.
- No notifications (email/Telegram/desktop) and no alert history.
- No user-configurable thresholds — deferred follow-up (see
  `docs/backlog.md`); the constants live at the top of `alert_service.py`
  so a future config file can override them.
