"""Deterministic financial alerts over the insights report (no LLM).

Rules read the metric report built by ``FinancialInsightsService`` from the
same facts the Financials tab loads (no second read, no parallel metric
table) and emit alerts with the evidence that triggered them. A rule whose
required data is missing returns ``None`` and is counted as skipped — it
never fires on missing data. See ``docs/financial_alerts.md`` for the
thresholds, severity mapping and rationale.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from backend.services.demo_mode import DEMO_ROOT
from backend.services.financial_insights_service import (
    FinancialInsightsService,
    InsightsReport,
    MetricInsight,
    format_metric_value,
)

#: Thresholds (see docs/financial_alerts.md).
MIN_CASH_RUNWAY_MONTHS = 6.0
MARGIN_COLLAPSE_PP = 5.0
DEBT_SPIKE_PCT = 30.0
DEBT_GROWTH_PCT = 50.0
EQUITY_FLAT_PCT = 10.0
INVENTORY_VS_REVENUE_FACTOR = 2.0
#: Absolute floor for rule 4: a small inventory tick against a small revenue
#: dip (TSLA +3% vs -3%) is not a buildup worth alerting on.
INVENTORY_GROWTH_FLOOR_PCT = 10.0
FCF_NEGATIVE_YEARS = 2
REVENUE_DECLINE_YEARS = 2
DILUTION_PCT = 5.0
DIVIDEND_CUT_PCT = 20.0
STRONG_FCF_YEARS = 3
STRONG_FCF_RATIO = 1.0

SEVERITY_ORDER = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}


@dataclass(frozen=True)
class Alert:
    """One rule firing, with the numbers that triggered it."""

    rule_id: str  # "low_cash_runway"
    severity: str  # "INFO" | "WARNING" | "CRITICAL"
    title: str  # short human label
    message: str  # one-sentence explanation
    evidence: dict[str, str]  # formatted numbers that triggered it
    metric_hint: str | None  # "revenue", "net_margin", ...
    period: str  # "FY2025" or "Q2 2025"


@dataclass
class AlertsReport:
    ticker: str
    company_name: str
    alerts: list[Alert]
    rules_evaluated: int
    rules_skipped: int  # missing data — never a false positive
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _metric(report: InsightsReport, name: str) -> MetricInsight | None:
    return next((m for m in report.metrics if m.metric == name), None)


def _latest_common(
    first: MetricInsight, second: MetricInsight
) -> tuple[int, float, float] | None:
    """Newest fiscal year present in both series, with both values."""
    years = set(first.series) & set(second.series)
    if not years:
        return None
    year = max(years)
    return year, first.series[year], second.series[year]


def _latest_two(
    series: dict[int, float],
) -> tuple[tuple[int, float], tuple[int, float]] | None:
    """The two newest values when they are consecutive years (a true YoY)."""
    ordered = sorted(series.items(), reverse=True)
    if len(ordered) < 2:
        return None
    (year, value), (prior_year, prior) = ordered[0], ordered[1]
    if year != prior_year + 1:
        return None
    return (year, value), (prior_year, prior)


def _growth(pair: tuple[tuple[int, float], tuple[int, float]]) -> float | None:
    (_, value), (_, prior) = pair
    if prior == 0:
        return None
    return (value - prior) / abs(prior) * 100


def _consecutive_from_newest(series: dict[int, float]) -> list[tuple[int, float]]:
    """Values from the newest year back, stopping at the first gap."""
    run: list[tuple[int, float]] = []
    for year, value in sorted(series.items(), reverse=True):
        if run and year != run[-1][0] - 1:
            break
        run.append((year, value))
    return run


def _period(year: int, fiscal_period: str) -> str:
    period = (fiscal_period or "FY").upper()
    return f"FY{year}" if period == "FY" else f"{period} {year}"


# ---------------------------------------------------------------------------
# rules — each returns None when its data is missing (skipped), else the
# alerts that fired (possibly none)
# ---------------------------------------------------------------------------
AlertRule = Callable[[InsightsReport, str, bool], list[Alert] | None]


def _rule_low_cash_runway(
    report: InsightsReport, period: str, abbreviate: bool
) -> list[Alert] | None:
    cash = _metric(report, "cash")
    opex = _metric(report, "operating_expenses")
    if cash is None or opex is None:
        return None
    common = _latest_common(cash, opex)
    if common is None:
        return None
    year, cash_value, opex_value = common
    if opex_value <= 0:
        return None
    # Liquid assets = cash + short-term investments for the same year. A
    # cash-only measure false-fires on companies that keep their liquidity
    # in marketable securities (MSFT: $21B cash, $64B short-term investments).
    investments = _metric(report, "short_term_investments")
    investments_value = 0.0
    if investments is not None and year in investments.series:
        investments_value = max(investments.series[year], 0.0)
    liquid = cash_value + investments_value
    runway = liquid / (opex_value / 12)
    if runway >= MIN_CASH_RUNWAY_MONTHS:
        return []
    evidence = {
        "Cash": format_metric_value(cash.kind, cash_value, abbreviate),
    }
    if investments_value:
        evidence["Short-term investments"] = format_metric_value(
            investments.kind, investments_value, abbreviate
        )
    evidence["Operating expenses"] = format_metric_value(
        opex.kind, opex_value, abbreviate
    )
    evidence["Runway"] = f"{runway:.1f} months"
    return [
        Alert(
            rule_id="low_cash_runway",
            severity="CRITICAL",
            title="Low cash runway",
            message=(
                f"Less than {MIN_CASH_RUNWAY_MONTHS:.0f} months of operating "
                "expenses covered by liquid assets."
            ),
            evidence=evidence,
            metric_hint="cash",
            period=_period(year, period),
        )
    ]


def _rule_margin_collapse(
    report: InsightsReport, period: str, abbreviate: bool
) -> list[Alert] | None:
    fired: list[Alert] = []
    evaluated = False
    for name in ("gross_margin", "net_margin"):
        margin = _metric(report, name)
        if margin is None or margin.latest_year is None or margin.yoy_pp is None:
            continue
        evaluated = True
        if margin.yoy_pp >= -MARGIN_COLLAPSE_PP:
            continue
        prior = margin.series.get(margin.latest_year - 1)
        fired.append(
            Alert(
                rule_id="margin_collapse",
                severity="WARNING",
                title=f"{margin.label} collapse",
                message=f"{margin.label} dropped {abs(margin.yoy_pp):.1f} pp YoY.",
                evidence={
                    "Current": format_metric_value(
                        margin.kind, margin.series.get(margin.latest_year), abbreviate
                    ),
                    "Prior": format_metric_value(margin.kind, prior, abbreviate),
                    "Change": f"{margin.yoy_pp:+.1f}pp",
                },
                metric_hint=name,
                period=_period(margin.latest_year, period),
            )
        )
    return fired if evaluated else None


def _rule_debt_spike(
    report: InsightsReport, period: str, abbreviate: bool
) -> list[Alert] | None:
    ratio = _metric(report, "debt_to_equity")
    if ratio is None:
        return None
    pair = _latest_two(ratio.series)
    if pair is None:
        return None
    (year, current), (_, prior) = pair
    if prior <= 0:
        return None
    change = (current - prior) / prior * 100
    if change > DEBT_SPIKE_PCT:
        return [
            Alert(
                rule_id="debt_spike",
                severity="WARNING",
                title="Debt spike",
                message=f"Total debt / equity increased {change:.1f}% YoY.",
                evidence={
                    "Current ratio": f"{current:.2f}",
                    "Prior ratio": f"{prior:.2f}",
                    "Change": f"{change:+.1f}%",
                },
                metric_hint="debt_to_equity",
                period=_period(year, period),
            )
        ]
    # Second branch: debt grew fast while equity stayed flat.
    debt = _metric(report, "total_debt")
    equity = _metric(report, "stockholders_equity")
    if debt is None or equity is None:
        return []
    debt_pair = _latest_two(debt.series)
    equity_pair = _latest_two(equity.series)
    if debt_pair is None or equity_pair is None:
        return []
    if debt_pair[0][0] != equity_pair[0][0]:
        return []
    debt_growth = _growth(debt_pair)
    equity_growth = _growth(equity_pair)
    if debt_growth is None or equity_growth is None:
        return []
    if debt_growth > DEBT_GROWTH_PCT and abs(equity_growth) <= EQUITY_FLAT_PCT:
        return [
            Alert(
                rule_id="debt_spike",
                severity="WARNING",
                title="Debt spike",
                message=(
                    f"Total debt grew {debt_growth:.1f}% YoY while equity stayed flat."
                ),
                evidence={
                    "Total debt growth": f"{debt_growth:+.1f}%",
                    "Equity change": f"{equity_growth:+.1f}%",
                },
                metric_hint="total_debt",
                period=_period(debt_pair[0][0], period),
            )
        ]
    return []


def _rule_inventory_buildup(
    report: InsightsReport, period: str, abbreviate: bool
) -> list[Alert] | None:
    inventory = _metric(report, "inventory")
    revenue = _metric(report, "revenue")
    if inventory is None or revenue is None:
        return None
    inventory_pair = _latest_two(inventory.series)
    revenue_pair = _latest_two(revenue.series)
    if inventory_pair is None or revenue_pair is None:
        return None
    if inventory_pair[0][0] != revenue_pair[0][0]:
        return None
    inventory_growth = _growth(inventory_pair)
    revenue_growth = _growth(revenue_pair)
    if inventory_growth is None or revenue_growth is None:
        return None
    # Only a real buildup: inventory must grow past the floor, and faster
    # than 2x revenue (the floor keeps a small tick vs a small dip quiet).
    if inventory_growth <= INVENTORY_GROWTH_FLOOR_PCT or inventory_growth <= (
        INVENTORY_VS_REVENUE_FACTOR * revenue_growth
    ):
        return []
    return [
        Alert(
            rule_id="inventory_buildup",
            severity="WARNING",
            title="Inventory buildup",
            message=(
                f"Inventory grew {inventory_growth:.1f}% vs revenue "
                f"{revenue_growth:+.1f}% YoY."
            ),
            evidence={
                "Inventory growth": f"{inventory_growth:+.1f}%",
                "Revenue growth": f"{revenue_growth:+.1f}%",
            },
            metric_hint="inventory",
            period=_period(inventory_pair[0][0], period),
        )
    ]


def _rule_negative_fcf_streak(
    report: InsightsReport, period: str, abbreviate: bool
) -> list[Alert] | None:
    fcf = _metric(report, "free_cash_flow")
    if fcf is None or not fcf.series:
        return None
    run = _consecutive_from_newest(fcf.series)
    streak = 0
    for _, value in run:
        if value < 0:
            streak += 1
        else:
            break
    if streak < FCF_NEGATIVE_YEARS:
        return []
    values = ", ".join(
        format_metric_value(fcf.kind, value, abbreviate) for _, value in run[:streak]
    )
    return [
        Alert(
            rule_id="negative_fcf_streak",
            severity="WARNING",
            title="Negative free cash flow streak",
            message=f"Free cash flow was negative for {streak} consecutive years.",
            evidence={"Free cash flow": values},
            metric_hint="free_cash_flow",
            period=_period(run[0][0], period),
        )
    ]


def _rule_revenue_decline(
    report: InsightsReport, period: str, abbreviate: bool
) -> list[Alert] | None:
    revenue = _metric(report, "revenue")
    if revenue is None or not revenue.series:
        return None
    run = _consecutive_from_newest(revenue.series)
    if len(run) < 2:
        return None
    declines: list[float] = []
    for index in range(len(run) - 1):
        growth = _growth((run[index], run[index + 1]))
        if growth is None or growth >= 0:
            break
        declines.append(growth)
    if len(declines) < REVENUE_DECLINE_YEARS:
        return []
    yoys = ", ".join(f"{growth:.1f}%" for growth in declines)
    values = ", ".join(
        format_metric_value(revenue.kind, value, abbreviate)
        for _, value in run[: len(declines) + 1]
    )
    return [
        Alert(
            rule_id="revenue_decline",
            severity="INFO",
            title="Revenue decline",
            message=f"Revenue declined {len(declines)} consecutive years: {yoys}.",
            evidence={"Revenue": values, "YoY": yoys},
            metric_hint="revenue",
            period=_period(run[0][0], period),
        )
    ]


def _rule_earnings_quality(
    report: InsightsReport, period: str, abbreviate: bool
) -> list[Alert] | None:
    net_income = _metric(report, "net_income")
    ocf = _metric(report, "operating_cash_flow")
    if net_income is None or ocf is None:
        return None
    common = _latest_common(net_income, ocf)
    if common is None:
        return None
    year, net_income_value, ocf_value = common
    if not (net_income_value > 0 and ocf_value < 0):
        return []
    return [
        Alert(
            rule_id="earnings_quality",
            severity="INFO",
            title="Earnings quality warning",
            message="Net income is positive but operating cash flow is negative.",
            evidence={
                "Net income": format_metric_value(
                    net_income.kind, net_income_value, abbreviate
                ),
                "Operating cash flow": format_metric_value(
                    ocf.kind, ocf_value, abbreviate
                ),
            },
            metric_hint="net_income",
            period=_period(year, period),
        )
    ]


def _rule_eps_dilution(
    report: InsightsReport, period: str, abbreviate: bool
) -> list[Alert] | None:
    shares = _metric(report, "diluted_shares")
    if shares is None:
        return None
    pair = _latest_two(shares.series)
    if pair is None:
        return None
    growth = _growth(pair)
    if growth is None:
        return None
    if growth <= DILUTION_PCT:
        return []
    return [
        Alert(
            rule_id="eps_dilution",
            severity="INFO",
            title="EPS dilution",
            message=f"Diluted shares outstanding grew {growth:.1f}% YoY.",
            evidence={
                "Current shares": format_metric_value(
                    shares.kind, pair[0][1], abbreviate
                ),
                "Prior shares": format_metric_value(
                    shares.kind, pair[1][1], abbreviate
                ),
                "Growth": f"{growth:+.1f}%",
            },
            metric_hint="diluted_shares",
            period=_period(pair[0][0], period),
        )
    ]


def _rule_dividend_cut(
    report: InsightsReport, period: str, abbreviate: bool
) -> list[Alert] | None:
    dividends = _metric(report, "dividends_paid")
    if dividends is None:
        return None
    pair = _latest_two(dividends.series)
    if pair is None:
        return None
    (year, current), (_, prior) = pair
    if current <= 0 or prior <= 0:
        return []  # not a payer in both years
    change = (current - prior) / prior * 100
    if change >= -DIVIDEND_CUT_PCT:
        return []
    return [
        Alert(
            rule_id="dividend_cut",
            severity="WARNING",
            title="Dividend cut",
            message=f"Dividends paid dropped {abs(change):.1f}% YoY.",
            evidence={
                "Current": format_metric_value(dividends.kind, current, abbreviate),
                "Prior": format_metric_value(dividends.kind, prior, abbreviate),
                "Change": f"{change:+.1f}%",
            },
            metric_hint="dividends_paid",
            period=_period(year, period),
        )
    ]


def _rule_strong_fcf_conversion(
    report: InsightsReport, period: str, abbreviate: bool
) -> list[Alert] | None:
    fcf = _metric(report, "free_cash_flow")
    net_income = _metric(report, "net_income")
    if fcf is None or net_income is None:
        return None
    common_years = sorted(set(fcf.series) & set(net_income.series), reverse=True)
    if not common_years:
        return None
    ratios: list[tuple[int, float]] = []
    for index, year in enumerate(common_years):
        if index and year != common_years[index - 1] - 1:
            break
        net_income_value = net_income.series[year]
        if net_income_value <= 0:
            break
        ratio = fcf.series[year] / net_income_value
        if ratio <= STRONG_FCF_RATIO:
            break
        ratios.append((year, ratio))
    if len(ratios) < STRONG_FCF_YEARS:
        return []
    ratio_text = ", ".join(f"{ratio:.2f}" for _, ratio in ratios)
    return [
        Alert(
            rule_id="strong_fcf_conversion",
            severity="INFO",
            title="Strong FCF conversion",
            message=f"FCF > net income for {len(ratios)} consecutive years.",
            evidence={"FCF / net income": ratio_text},
            metric_hint="free_cash_flow",
            period=_period(ratios[0][0], period),
        )
    ]


RULES: list[tuple[str, AlertRule]] = [
    ("low_cash_runway", _rule_low_cash_runway),
    ("margin_collapse", _rule_margin_collapse),
    ("debt_spike", _rule_debt_spike),
    ("inventory_buildup", _rule_inventory_buildup),
    ("negative_fcf_streak", _rule_negative_fcf_streak),
    ("revenue_decline", _rule_revenue_decline),
    ("earnings_quality", _rule_earnings_quality),
    ("eps_dilution", _rule_eps_dilution),
    ("dividend_cut", _rule_dividend_cut),
    ("strong_fcf_conversion", _rule_strong_fcf_conversion),
]


class AlertService:
    """Runs the deterministic rule registry over the insights report."""

    def __init__(self, facts: list[dict]) -> None:
        """``facts`` is the list returned by ``fetch_facts`` (same as the tab)."""
        self._facts = list(facts or [])

    def build(
        self,
        ticker: str,
        company_name: str,
        fiscal_period: str = "FY",
        abbreviate: bool = False,
    ) -> AlertsReport:
        report = FinancialInsightsService(self._facts, ticker, company_name).build(
            abbreviate
        )
        alerts: list[Alert] = []
        skipped = 0
        for _, rule in RULES:
            outcome = rule(report, fiscal_period, abbreviate)
            if outcome is None:
                skipped += 1
            else:
                alerts.extend(outcome)
        alerts.sort(
            key=lambda alert: (SEVERITY_ORDER.get(alert.severity, 99), alert.rule_id)
        )
        return AlertsReport(
            ticker=ticker,
            company_name=company_name,
            alerts=alerts,
            rules_evaluated=len(RULES),
            rules_skipped=skipped,
            warnings=list(report.warnings),
        )


def alerts_to_payload(report: AlertsReport) -> dict:
    """Serialize the report for the demo fixture."""
    return {
        "ticker": report.ticker,
        "company_name": report.company_name,
        "rules_evaluated": report.rules_evaluated,
        "rules_skipped": report.rules_skipped,
        "warnings": list(report.warnings),
        "alerts": [
            {
                "rule_id": alert.rule_id,
                "severity": alert.severity,
                "title": alert.title,
                "message": alert.message,
                "evidence": dict(alert.evidence),
                "metric_hint": alert.metric_hint,
                "period": alert.period,
            }
            for alert in report.alerts
        ],
    }


def alerts_from_payload(payload: dict) -> AlertsReport:
    """Rebuild the demo report from its pinned fixture."""
    alerts = [
        Alert(
            rule_id=str(row.get("rule_id") or ""),
            severity=str(row.get("severity") or "INFO"),
            title=str(row.get("title") or ""),
            message=str(row.get("message") or ""),
            evidence={
                str(key): str(value)
                for key, value in (row.get("evidence") or {}).items()
            },
            metric_hint=row.get("metric_hint"),
            period=str(row.get("period") or ""),
        )
        for row in payload.get("alerts", [])
    ]
    return AlertsReport(
        ticker=str(payload.get("ticker") or ""),
        company_name=str(payload.get("company_name") or ""),
        alerts=alerts,
        rules_evaluated=int(payload.get("rules_evaluated") or 0),
        rules_skipped=int(payload.get("rules_skipped") or 0),
        warnings=list(payload.get("warnings") or []),
    )


def load_demo_alerts(ticker: str) -> AlertsReport | None:
    """The pinned alerts fixture for demo mode, or None when absent."""
    path = DEMO_ROOT / "financials" / f"{ticker.upper().strip()}_alerts.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return alerts_from_payload(payload)
