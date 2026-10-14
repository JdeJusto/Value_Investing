"""Scorecard: six decomposable dimensions over the existing analysis.

This is the aggregation layer behind the interactive/visual stock analysis
(the ``scorecard``). It is a **presentation layer**: every value comes from a
service that already exists — :class:`FinancialInsightsService`,
:class:`AlertService`, the DCF, ``backend/analytics`` ratio calculators and the
methodology registry. The only new number is a trivial roll-up.

Design rules (see ``docs/scorecard_design.md``):

- **No master score.** ``overall`` is a label; cross-dimension disagreement is
  surfaced, never averaged away.
- **Methodologies stay independent.** The eight book methodologies are carried
  through verbatim and are *never* folded into a dimension (``base.py``: "a
  methodology is an independent column, never a contributor to a composite").
- **Missing data is not failure.** A rule with no input is ``INSUFFICIENT``;
  a dimension with fewer than two evaluable rules is ``Insufficient``.
- **Deterministic.** No clock, no randomness. One fundamentals fetch and one
  price fetch; prices are never persisted.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from backend.analytics.ratios.leverage import InterestCoverageCalculator
from backend.analytics.ratios.margins import FcfYieldCalculator
from backend.analytics.ratios.per import PerCalculator
from backend.analytics.ratios.roic import RoicCalculator
from backend.analytics.service import effective_tax_rate
from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.registry import discover, registry
from backend.services.alert_service import AlertService, AlertsReport
from backend.services.financial_insights_service import (
    FinancialInsightsService,
    InsightsReport,
    MetricInsight,
)
from backend.services.financials_view_service import FinancialsViewService

__all__ = [
    "FAIL",
    "INSUFFICIENT",
    "PASS",
    "WATCH",
    "DimensionRule",
    "DimensionScore",
    "Scorecard",
    "ScorecardService",
]

# --- statuses and verdicts ------------------------------------------------
PASS = "PASS"
WATCH = "WATCH"
FAIL = "FAIL"
INSUFFICIENT = "INSUFFICIENT"

STRONG = "Strong"
MIXED = "Mixed"
WEAK = "Weak"
INSUFFICIENT_VERDICT = "Insufficient"

#: Fixed dimension order (the radar axes).
DIMENSION_ORDER = (
    "growth",
    "profitability",
    "financial_health",
    "valuation",
    "shareholder_returns",
    "management_moat",
)

#: Fundamentals window: enough for a 10-year CAGR plus a 5-rule trend.
HISTORY_YEARS = 10
#: History depth that counts as full data quality.
_FULL_HISTORY_YEARS = 8

_POINTS = {PASS: 2, WATCH: 1, FAIL: 0}


# ---------------------------------------------------------------------------
# domain objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DimensionRule:
    """One named, metric-backed rule behind a dimension score."""

    rule_id: str
    label: str
    status: str
    value: str
    threshold: str
    reason: str
    source_metric: str | None = None
    source_methodology: str | None = None
    source_book: str | None = None


@dataclass(frozen=True)
class DimensionScore:
    """One dimension: a 0-10 score, its verdict, and the rules behind it."""

    key: str
    label: str
    question: str
    score: int | None
    verdict: str
    evaluable_rules: int
    rules: tuple[DimensionRule, ...]
    trend: str
    summary: str


@dataclass(frozen=True)
class Scorecard:
    """The full scorecard payload for one ticker (JSON-friendly)."""

    ticker: str
    company: str
    sector: str | None
    industry: str | None
    period: str
    price: float | None
    market_cap: float | None
    generated: str
    dimensions: tuple[DimensionScore, ...]
    overall: str
    disagreements: tuple[str, ...]
    methodologies: tuple[dict[str, Any], ...]
    data_quality: str
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly dict (tuples serialize as arrays)."""
        return asdict(self)


# ---------------------------------------------------------------------------
# scoring helpers
# ---------------------------------------------------------------------------
def _verdict_for(score: int | None) -> str:
    if score is None:
        return INSUFFICIENT_VERDICT
    if score >= 8:
        return STRONG
    if score <= 4:
        return WEAK
    return MIXED


def score_rules(rules: list[DimensionRule]) -> tuple[int | None, str, int]:
    """``(score, verdict, evaluable)`` from the rule statuses.

    ``INSUFFICIENT`` rules are dropped; fewer than two evaluable rules means
    the dimension itself is ``Insufficient`` (never a 0).
    """
    evaluable = [rule for rule in rules if rule.status != INSUFFICIENT]
    if len(evaluable) < 2:
        return None, INSUFFICIENT_VERDICT, len(evaluable)
    points = sum(_POINTS[rule.status] for rule in evaluable)
    score = round(10 * points / (2 * len(evaluable)))
    return score, _verdict_for(score), len(evaluable)


def _band(value: float | None, pass_min: float, watch_min: float) -> str:
    """Higher-is-better band (``≥ pass_min`` / ``≥ watch_min`` / else FAIL)."""
    if value is None:
        return INSUFFICIENT
    if value >= pass_min:
        return PASS
    if value >= watch_min:
        return WATCH
    return FAIL


def _band_max(value: float | None, pass_max: float, watch_max: float) -> str:
    """Lower-is-better band (``≤ pass_max`` / ``≤ watch_max`` / else FAIL)."""
    if value is None:
        return INSUFFICIENT
    if value <= pass_max:
        return PASS
    if value <= watch_max:
        return WATCH
    return FAIL


def _pct(value: float | None) -> str:
    """A fraction (0.24) as a percentage string ("24.0%")."""
    return "—" if value is None else f"{value * 100:.1f}%"


def _pts(value: float | None) -> str:
    """A percent-unit number (12.4) as ``"12.3%"``."""
    return "—" if value is None else f"{value:.1f}%"


def _x(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}x"


def _rule(
    rule_id: str,
    label: str,
    status: str,
    value: str,
    threshold: str,
    reason: str,
    source_metric: str | None = None,
    source_methodology: str | None = None,
) -> DimensionRule:
    return DimensionRule(
        rule_id=rule_id,
        label=label,
        status=status,
        value=value,
        threshold=threshold,
        reason=reason,
        source_metric=source_metric,
        source_methodology=source_methodology,
    )


def _cagr_reason(label: str, value: float | None, target: float) -> str:
    if value is None:
        return f"{label} history is unavailable."
    return f"{label} compounded at {value:.1f}%/yr (target {target:.0f}%)."


def _margin_reason(label: str, value: float | None, target: float) -> str:
    if value is None:
        return f"{label} is unavailable."
    return f"{label} is {value * 100:.1f}% (target {target * 100:.0f}%)."


def _multiple_reason(label: str, value: float | None, target: float) -> str:
    if value is None:
        return f"{label} is unavailable."
    return f"{label} is {value:.1f}x (target {target:.0f}x)."


# ---------------------------------------------------------------------------
# read-only adapters over the existing reports
# ---------------------------------------------------------------------------
class _Metrics:
    """Typed access to one :class:`InsightsReport`."""

    def __init__(self, report: InsightsReport | None) -> None:
        self._by = {m.metric: m for m in report.metrics} if report else {}

    def get(self, *names: str) -> MetricInsight | None:
        for name in names:
            insight = self._by.get(name)
            if insight is not None:
                return insight
        return None

    def latest(self, *names: str) -> float | None:
        """The newest value in the metric's series (fraction for percent)."""
        insight = self.get(*names)
        if insight is None or not insight.series:
            return None
        return insight.series[max(insight.series)]

    def cagr(self, *names: str) -> float | None:
        """5-year CAGR as a percent number (``12.4`` = 12.4 %)."""
        insight = self.get(*names)
        return insight.cagr_5y if insight else None

    def trend(self, *names: str) -> str | None:
        insight = self.get(*names)
        return insight.trend if insight else None

    def stability(self, *names: str) -> str | None:
        insight = self.get(*names)
        return insight.stability if insight else None

    def has_series(self, *names: str) -> bool:
        insight = self.get(*names)
        return bool(insight and insight.series)


class _Alerts:
    """Rule-id membership over one :class:`AlertsReport`."""

    def __init__(self, report: AlertsReport | None) -> None:
        # ``rules_evaluated == 0`` means the alert layer had no facts to run
        # on, so rule presence/absence carries no signal.
        self._available = report is not None and report.rules_evaluated > 0
        self._ids = {a.rule_id for a in report.alerts} if report else set()

    @property
    def available(self) -> bool:
        return self._available

    def has(self, rule_id: str) -> bool:
        return rule_id in self._ids


# ---------------------------------------------------------------------------
# ratio bridges (existing calculators — nothing re-implemented here)
# ---------------------------------------------------------------------------
def _roic_of(row: NormalizedFinancials) -> float | None:
    return RoicCalculator().calculate(
        ebit=row.ebit,
        tax_rate=effective_tax_rate(row),
        total_debt=row.total_debt,
        equity=row.stockholders_equity,
        cash=row.cash_and_equivalents,
    )


def _interest_coverage_of(row: NormalizedFinancials) -> float | None:
    return InterestCoverageCalculator().calculate(
        ebit=row.ebit,
        interest_expense=row.interest_expense,
    )


# ---------------------------------------------------------------------------
# dimension builders
# ---------------------------------------------------------------------------
def _growth_rules(m: _Metrics, alerts: _Alerts) -> list[DimensionRule]:
    rules: list[DimensionRule] = []

    rev = m.cagr("revenue")
    rules.append(
        _rule(
            "revenue_cagr_5y",
            "Revenue CAGR (5y)",
            _band(rev, 10.0, 3.0),
            _pts(rev),
            "≥ 10%",
            _cagr_reason("Revenue", rev, 10.0),
            source_metric="revenue.cagr_5y",
        )
    )

    eps = m.cagr("eps_diluted", "net_income")
    rules.append(
        _rule(
            "eps_cagr_5y",
            "Earnings CAGR (5y)",
            _band(eps, 10.0, 3.0),
            _pts(eps),
            "≥ 10%",
            _cagr_reason("Earnings per share / net income", eps, 10.0),
            source_metric="eps_diluted.cagr_5y",
        )
    )

    fcf = m.cagr("free_cash_flow", "fcf")
    rules.append(
        _rule(
            "fcf_cagr_5y",
            "Free cash flow CAGR (5y)",
            _band(fcf, 8.0, 0.0),
            _pts(fcf),
            "≥ 8%",
            _cagr_reason("Free cash flow", fcf, 8.0),
            source_metric="free_cash_flow.cagr_5y",
        )
    )

    trend = m.trend("revenue")
    stability = m.stability("revenue")
    if not m.has_series("revenue"):
        status, reason = INSUFFICIENT, "Revenue history is unavailable."
    elif trend == "declining":
        status, reason = FAIL, "Revenue is declining."
    elif stability == "volatile":
        status, reason = WATCH, "Revenue is volatile."
    else:
        status = PASS
        reason = f"Revenue is {trend or 'stable'}."
    rules.append(
        _rule(
            "revenue_trend",
            "Revenue trend",
            status,
            trend or "—",
            "growing / stable",
            reason,
            source_metric="revenue.trend",
        )
    )

    if not alerts.available:
        status, reason, value = INSUFFICIENT, "Alert rules did not run.", "—"
    elif alerts.has("revenue_decline"):
        status, reason, value = FAIL, "The revenue-decline alert is firing.", "firing"
    else:
        status, reason, value = PASS, "No revenue-decline alert.", "none"
    rules.append(
        _rule(
            "revenue_decline_alert",
            "No revenue-decline alert",
            status,
            value,
            "no alert",
            reason,
            source_metric="alert.revenue_decline",
        )
    )
    return rules


def _roic_latest(rows: list[NormalizedFinancials]) -> float | None:
    return _roic_of(rows[0]) if rows else None


def _ic_latest(rows: list[NormalizedFinancials]) -> float | None:
    if not rows:
        return None
    return InterestCoverageCalculator().calculate(
        ebit=rows[0].ebit, interest_expense=rows[0].interest_expense
    )


def _profitability_rules(
    metrics: _Metrics, alerts: _Alerts, rows: list[NormalizedFinancials]
) -> list[DimensionRule]:
    rules: list[DimensionRule] = []

    net_margin = metrics.latest("net_margin")
    rules.append(
        _rule(
            "net_margin",
            "Net margin",
            _band(net_margin, 0.10, 0.03),
            _pct(net_margin),
            "≥ 10%",
            _margin_reason("Net margin", net_margin, 0.10),
            source_metric="net_margin",
        )
    )

    roe = metrics.latest("roe")
    rules.append(
        _rule(
            "roe",
            "Return on equity",
            _band(roe, 0.15, 0.08),
            _pct(roe),
            "≥ 15%",
            _margin_reason("Return on equity", roe, 0.15),
            source_metric="roe",
        )
    )

    roic = _roic_latest(rows)
    rules.append(
        _rule(
            "roic",
            "Return on invested capital",
            _band(roic, 0.10, 0.06),
            _pct(roic),
            "≥ 10%",
            _margin_reason("Return on invested capital", roic, 0.10),
            source_metric="roic",
        )
    )

    gross_margin = metrics.latest("gross_margin")
    rules.append(
        _rule(
            "gross_margin_level",
            "Gross margin",
            _band(gross_margin, 0.40, 0.20),
            _pct(gross_margin),
            "≥ 40%",
            _margin_reason("Gross margin", gross_margin, 0.40),
            source_metric="gross_margin",
        )
    )

    conversion = metrics.latest("fcf_conversion")
    rules.append(
        _rule(
            "fcf_conversion",
            "FCF conversion",
            _band(conversion, 0.80, 0.50),
            _pct(conversion),
            "≥ 80%",
            _margin_reason("Free-cash-flow conversion", conversion, 0.80),
            source_metric="fcf_conversion",
        )
    )

    if not alerts.available:
        status, reason, value = INSUFFICIENT, "Alert rules did not run.", "—"
    elif alerts.has("margin_collapse"):
        status, reason, value = FAIL, "The margin-collapse alert is firing.", "firing"
    elif alerts.has("earnings_quality"):
        status, reason, value = WATCH, "The earnings-quality alert is firing.", "firing"
    else:
        status, reason, value = PASS, "No margin or earnings-quality alert.", "none"
    rules.append(
        _rule(
            "margin_alerts",
            "No margin/earnings-quality alert",
            status,
            value,
            "no alert",
            reason,
            source_metric="alert.margin_collapse",
        )
    )
    return rules


def _financial_health_rules(
    metrics: _Metrics, alerts: _Alerts, rows: list[NormalizedFinancials]
) -> list[DimensionRule]:
    rules: list[DimensionRule] = []

    debt_to_equity = metrics.latest("debt_to_equity")
    rules.append(
        _rule(
            "debt_to_equity",
            "Debt-to-equity",
            _band_max(debt_to_equity, 0.5, 1.5),
            _x(debt_to_equity),
            "≤ 0.5x",
            "Debt-to-equity is "
            + ("unavailable." if debt_to_equity is None else f"{debt_to_equity:.2f}x."),
            source_metric="debt_to_equity",
        )
    )

    coverage = _ic_latest(rows)
    rules.append(
        _rule(
            "interest_coverage",
            "Interest coverage",
            _band(coverage, 6.0, 3.0),
            _x(coverage),
            "≥ 6x",
            "Interest coverage is "
            + ("unavailable." if coverage is None else f"{coverage:.1f}x."),
            source_metric="interest_coverage",
        )
    )

    rules.append(
        _rule(
            "current_ratio",
            "Current ratio",
            INSUFFICIENT,
            "—",
            "≥ 1.5x",
            "Current ratio is not computed by backend/analytics yet (see backlog).",
            source_metric="current_ratio",
        )
    )

    fcf = metrics.latest("free_cash_flow", "fcf")
    if fcf is None:
        status, reason, value = INSUFFICIENT, "Free cash flow is unavailable.", "—"
    elif fcf > 0:
        status, reason, value = PASS, "Free cash flow is positive.", "positive"
    else:
        status, reason, value = FAIL, "Free cash flow is negative.", "negative"
    rules.append(
        _rule(
            "fcf_positive",
            "Free cash flow positive",
            status,
            value,
            "> 0",
            reason,
            source_metric="free_cash_flow",
        )
    )

    if not alerts.available:
        status, reason, value = INSUFFICIENT, "Alert rules did not run.", "—"
    elif any(
        alerts.has(rule)
        for rule in ("low_cash_runway", "debt_spike", "negative_fcf_streak")
    ):
        status, reason, value = FAIL, "A liquidity/debt alert is firing.", "firing"
    elif alerts.has("inventory_buildup"):
        status, reason, value = (
            WATCH,
            "The inventory-build-up alert is firing.",
            "firing",
        )
    else:
        status, reason, value = PASS, "No liquidity or debt alert.", "none"
    rules.append(
        _rule(
            "liquidity_alerts",
            "No liquidity/debt alert",
            status,
            value,
            "no alert",
            reason,
            source_metric="alert.debt_spike",
        )
    )
    return rules


def _valuation_rules(
    metrics: _Metrics,
    dcf: Any,
    market_cap: float | None,
) -> list[DimensionRule]:
    rules: list[DimensionRule] = []

    mos = getattr(dcf, "margin_of_safety", None) if dcf is not None else None
    rules.append(
        _rule(
            "dcf_margin_of_safety",
            "DCF margin of safety",
            _band(mos, 0.20, 0.0),
            _pct(mos),
            "≥ 20%",
            "The DCF margin of safety is "
            + ("unavailable." if mos is None else f"{mos * 100:.1f}%."),
            source_metric="dcf.margin_of_safety",
        )
    )

    net_income = metrics.latest("net_income")
    per = PerCalculator().calculate(market_cap=market_cap, net_income=net_income)
    if per is None or per <= 0:
        status, reason = INSUFFICIENT, "A positive P/E could not be computed."
    else:
        status = _band_max(per, 15.0, 25.0)
        reason = _multiple_reason("P/E", per, 15.0)
    rules.append(
        _rule(
            "pe_absolute",
            "Price-to-earnings",
            status,
            _x(per) if (per is not None and per > 0) else "—",
            "≤ 15x",
            reason,
            source_metric="per",
        )
    )

    fcf = metrics.latest("free_cash_flow", "fcf")
    fcf_yield = FcfYieldCalculator().calculate(
        free_cash_flow=fcf, market_cap=market_cap
    )
    rules.append(
        _rule(
            "fcf_yield",
            "Free-cash-flow yield",
            _band(fcf_yield, 0.04, 0.02),
            _pct(fcf_yield),
            "≥ 4%",
            _margin_reason("Free-cash-flow yield", fcf_yield, 0.04),
            source_metric="fcf_yield",
        )
    )

    if net_income is None:
        status, reason, value = INSUFFICIENT, "Net income is unavailable.", "—"
    elif net_income > 0:
        status, reason, value = PASS, "The company is profitable.", "positive"
    else:
        status, reason, value = FAIL, "The company is loss-making.", "negative"
    rules.append(
        _rule(
            "earnings_sign",
            "Positive earnings",
            status,
            value,
            "> 0",
            reason,
            source_metric="net_income",
        )
    )
    return rules


def _shareholder_returns_rules(
    metrics: _Metrics, alerts: _Alerts
) -> list[DimensionRule]:
    rules: list[DimensionRule] = []

    dilution = metrics.cagr("diluted_shares")
    if dilution is None:
        status, reason = INSUFFICIENT, "Share-count history is unavailable."
    elif dilution <= 0:
        status, reason = (
            PASS,
            f"Share count changed {dilution:+.1f}%/yr (flat/buyback).",
        )
    elif dilution <= 1:
        status, reason = WATCH, f"Share count grew {dilution:.1f}%/yr."
    else:
        status, reason = FAIL, f"Share count grew {dilution:.1f}%/yr (dilution)."
    rules.append(
        _rule(
            "share_dilution",
            "Share dilution",
            status,
            _pts(dilution),
            "≤ 0%/yr",
            reason,
            source_metric="diluted_shares.cagr_5y",
        )
    )

    eps = metrics.cagr("eps_diluted", "net_income")
    if eps is None or dilution is None:
        status, reason, value = (
            INSUFFICIENT,
            "Per-share accretion needs both EPS and share-count history.",
            "—",
        )
    else:
        accretion = eps - dilution
        status = _band(accretion, 0.0, -1.0)
        value = _pts(accretion)
        reason = f"Per-share earnings changed {accretion:+.1f}%/yr."
    rules.append(
        _rule(
            "per_share_accretion",
            "Per-share earnings accretion",
            status,
            value,
            "≥ 0%/yr",
            reason,
            source_metric="eps_diluted.cagr_5y",
        )
    )

    dividends = metrics.latest("dividends_paid")
    payer = dividends is not None and abs(dividends) > 0
    if not payer:
        status, reason, value = (
            INSUFFICIENT,
            "The company pays no dividend.",
            "—",
        )
    elif alerts.available and alerts.has("dividend_cut"):
        status, reason, value = FAIL, "The dividend-cut alert is firing.", "firing"
    elif metrics.trend("dividends_paid") == "declining":
        status, reason, value = FAIL, "Dividends are declining.", "declining"
    elif metrics.trend("dividends_paid") == "growing":
        status, reason, value = PASS, "Dividends are growing.", "growing"
    else:
        status, reason, value = WATCH, "Dividends are stable.", "stable"
    rules.append(
        _rule(
            "dividend_growth",
            "Dividend growth",
            status,
            value,
            "growing / stable",
            reason,
            source_metric="dividends_paid.trend",
        )
    )

    fcf = metrics.latest("free_cash_flow", "fcf")
    if not payer or fcf is None:
        status, reason, value = (
            INSUFFICIENT,
            "Dividend cover needs a dividend and free cash flow.",
            "—",
        )
    else:
        cover = fcf / abs(dividends)
        status = _band(cover, 2.0, 1.0)
        value = _x(cover)
        reason = f"Free cash flow covers the dividend {cover:.1f}x."
    rules.append(
        _rule(
            "dividend_cover",
            "Dividend cover",
            status,
            value,
            "≥ 2x",
            reason,
            source_metric="dividends_paid",
        )
    )
    return rules


def _management_moat_rules(
    metrics: _Metrics, rows: list[NormalizedFinancials], red_flags: list[str] | None
) -> list[DimensionRule]:
    rules: list[DimensionRule] = []

    # ROIC persistence over the newest up-to-five years.
    yearly = [_roic_of(row) for row in rows[:5]]
    computable = [value for value in yearly if value is not None]
    if len(computable) < 3:
        status, reason, value = (
            INSUFFICIENT,
            "Fewer than three years of ROIC are computable.",
            "—",
        )
    else:
        hits = sum(1 for value in computable if value >= 0.10)
        share = hits / len(computable)
        if share == 1.0:
            status = PASS
        elif share >= 0.6:
            status = WATCH
        else:
            status = FAIL
        value = f"{hits}/{len(computable)} years"
        reason = f"ROIC was at or above 10% in {hits} of {len(computable)} years."
    rules.append(
        _rule(
            "roic_persistence",
            "ROIC persistence (≥ 10%)",
            status,
            value,
            "5 of 5 years",
            reason,
            source_metric="roic",
        )
    )

    stability = metrics.stability("gross_margin")
    trend = metrics.trend("gross_margin")
    if not metrics.has_series("gross_margin"):
        status, reason, value = (
            INSUFFICIENT,
            "Gross-margin history is unavailable.",
            "—",
        )
    elif trend == "declining":
        status, reason, value = FAIL, "Gross margin is declining.", "declining"
    elif stability == "stable":
        status, reason, value = PASS, "Gross margin is stable.", "stable"
    else:
        status, reason, value = WATCH, "Gross margin is volatile.", "volatile"
    rules.append(
        _rule(
            "gross_margin_stability",
            "Gross-margin stability",
            status,
            value,
            "stable",
            reason,
            source_metric="gross_margin.stability",
        )
    )

    if red_flags is None:
        status, reason, value = (
            INSUFFICIENT,
            "Buffett-Clark red flags were not evaluated.",
            "—",
        )
    elif not red_flags:
        status, reason, value = PASS, "No Buffett-Clark red flags.", "0"
    elif len(red_flags) == 1:
        status, reason, value = WATCH, "One Buffett-Clark red flag.", "1"
    else:
        status, reason, value = (
            FAIL,
            f"{len(red_flags)} Buffett-Clark red flags.",
            str(len(red_flags)),
        )
    rules.append(
        _rule(
            "management_red_flags",
            "Buffett-Clark red flags",
            status,
            value,
            "0 flags",
            reason,
            source_metric="methodology.buffett_clark",
            source_methodology="buffett_clark",
        )
    )
    return rules


# ---------------------------------------------------------------------------
# dimension assembly
# ---------------------------------------------------------------------------
_DIMENSION_META: dict[str, tuple[str, str]] = {
    "growth": ("Growth", "Is the business getting bigger?"),
    "profitability": ("Profitability", "Does it earn good returns on its money?"),
    "financial_health": ("Financial Health", "Can it service its debts?"),
    "valuation": ("Valuation", "Is the price reasonable?"),
    "shareholder_returns": ("Shareholder Returns", "Does the owner get paid?"),
    "management_moat": ("Management/Moat", "Will the returns last?"),
}


def _summary(score: int | None, verdict: str, evaluable: int) -> str:
    if score is None:
        return f"Insufficient data ({evaluable} evaluable rules)."
    return f"{score}/10 — {verdict} ({evaluable} rules)."


def _build_dimension(
    key: str,
    rules: list[DimensionRule],
    *,
    trend: str = "stable",
) -> DimensionScore:
    score, verdict, evaluable = score_rules(rules)
    label, question = _DIMENSION_META[key]
    return DimensionScore(
        key=key,
        label=label,
        question=question,
        score=score,
        verdict=verdict,
        evaluable_rules=evaluable,
        rules=tuple(rules),
        trend=trend,
        summary=_summary(score, verdict, evaluable),
    )


def _trend_from_metric(value: str | None) -> str:
    if value == "growing":
        return "improving"
    if value == "declining":
        return "deteriorating"
    return "stable"


def _median(values: list[int]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def _overall(dimensions: tuple[DimensionScore, ...]) -> str:
    """A label, never a mastered number (disagreement stays visible)."""
    scored = [d.score for d in dimensions if d.score is not None]
    insufficient = len(dimensions) - len(scored)
    if len(scored) < 2 or insufficient >= 4:
        return "Insufficient data"
    if len([score for score in scored if score <= 4]) >= 3:
        return WEAK
    if _median(scored) >= 8 and all(score > 3 for score in scored):
        return STRONG
    return MIXED


def _join_names(labels: list[str], *, cap: int = 3) -> str:
    """Deterministic list join, capped at ``cap`` names + "and N others"."""
    names = list(labels)
    if not names:
        return "no other dimension"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    if len(names) <= cap:
        return f"{', '.join(names[:-1])}, and {names[-1]}"
    others = len(names) - cap
    tail = "other" if others == 1 else "others"
    return f"{', '.join(names[:cap])}, and {others} {tail}"


#: Short noun for each dimension, used to summarize a strong set.
_THEME_NOUN = {
    "growth": "growth",
    "profitability": "profitability",
    "financial_health": "financial health",
    "valuation": "value",
    "shareholder_returns": "shareholder returns",
    "management_moat": "quality",
}


def _short_theme(keys: list[str]) -> str:
    """A short, deterministic theme for the strong dimensions.

    Ordered by ``DIMENSION_ORDER``; prefers a "… and quality" pair when the
    moat dimension is among them, otherwise the first two nouns.
    """
    ordered = [key for key in DIMENSION_ORDER if key in keys]
    nouns = [_THEME_NOUN[key] for key in ordered]
    if not nouns:
        return "strength"
    if len(nouns) == 1:
        return nouns[0]
    if "management_moat" in keys and ordered[0] != "management_moat":
        return f"{nouns[0]} and quality"
    return f"{nouns[0]} and {nouns[1]}"


def _disagreements(dimensions: tuple[DimensionScore, ...]) -> tuple[str, ...]:
    # A disagreement is a weak dimension (<=3) set against at least one
    # strong dimension (>=7). Messages are grouped by the **weak** dimension:
    # one weak side yields one message, not one per strong side, so "grows
    # fast but expensive" reads as a single sentence instead of five.
    # INSUFFICIENT dimensions score None, so they never participate.
    strong = [d for d in dimensions if d.score is not None and d.score >= 7]
    if not strong:
        return ()
    out: list[str] = []
    for weak in dimensions:
        if weak.score is None or weak.score > 3:
            continue
        peers = [d for d in strong if d.key != weak.key]
        if not peers:
            continue
        verb = "is" if len(peers) == 1 else "are"
        out.append(
            f"{weak.label} is weak ({weak.score}/10) while "
            f"{_join_names([d.label for d in peers])} {verb} strong "
            f"({_short_theme([d.key for d in peers])})."
        )
    return tuple(out)


def _data_quality(rows: list[NormalizedFinancials]) -> str:
    if not rows:
        return "LOW"
    years = len({row.fiscal_year for row in rows})
    latest = rows[0]
    covered = sum(
        1
        for field in ("revenue", "net_income", "total_assets", "free_cash_flow")
        if getattr(latest, field, None) is not None
    )
    if years >= _FULL_HISTORY_YEARS and covered >= 3:
        return "HIGH"
    if years >= 4 and covered >= 2:
        return "MEDIUM"
    return "LOW"


def _notes(
    dimensions: tuple[DimensionScore, ...], insights: InsightsReport | None
) -> tuple[str, ...]:
    notes: list[str] = []
    for dim in dimensions:
        skipped = sum(1 for rule in dim.rules if rule.status == INSUFFICIENT)
        if skipped:
            notes.append(f"{dim.label}: {skipped} rule(s) skipped for missing data.")
    notes.append(
        "Current ratio is not computed yet; Financial Health skips it (backlog)."
    )
    notes.append(
        "Peer comparison lands in Phase 5; Valuation uses absolute thresholds."
    )
    if insights is not None:
        notes.extend(insights.warnings)
    return tuple(notes)


# ---------------------------------------------------------------------------
# service
# ---------------------------------------------------------------------------
class ScorecardService:
    """Builds one :class:`Scorecard` from the existing analysis services."""

    def __init__(
        self,
        repository: Any = None,
        price_service: Any = None,
        *,
        max_years: int = HISTORY_YEARS,
    ) -> None:
        self._repository = repository
        self._price_service = price_service
        self._max_years = max(1, int(max_years))

    # -- lazy collaborators (mirrors FinancialsViewService) ---------------
    def _repo(self) -> Any:
        if self._repository is None:
            from backend.app.cli import build_financial_repository

            self._repository = build_financial_repository()
        return self._repository

    def _prices(self) -> Any:
        if self._price_service is None:
            from backend.services.price_service import PriceService

            self._price_service = PriceService()
        return self._price_service

    # -- public API -------------------------------------------------------
    def build(self, ticker: str, period: str = "FY") -> Scorecard | None:
        """Build the scorecard for ``ticker`` (``None`` when it has no data)."""
        symbol = str(ticker or "").strip().upper()
        if not symbol:
            return None
        repository = self._repo()
        rows = [
            row
            for row in (
                repository.get_best_available(symbol, max_years=self._max_years) or []
            )
            if row is not None
        ]
        if not rows:
            return None
        rows.sort(key=lambda row: row.fiscal_year, reverse=True)

        facts = FinancialsViewService(repository).fetch_facts(
            symbol, period, self._max_years
        )
        company = _company_name(repository, symbol) or symbol
        insights = FinancialInsightsService(facts, symbol, company).build()
        alerts = AlertService(facts).build(symbol, company, period)
        metrics = _Metrics(insights)
        alertset = _Alerts(alerts)

        prices = self._prices()
        price = _safe(lambda: prices.get_current_price(symbol))
        market_cap = _safe(lambda: prices.get_market_cap(symbol))
        dcf = _safe(lambda: _evaluate_dcf(symbol, rows, prices))

        methodology_results = _evaluate_methodologies(symbol, rows, prices)
        red_flags = next(
            (
                list(result.red_flags)
                for result in methodology_results
                if result.methodology == "buffett_clark"
            ),
            None,
        )

        dimensions = _build_dimensions(
            metrics, alertset, rows, dcf, market_cap, red_flags
        )
        overall = _overall(dimensions)
        disagreements = _disagreements(dimensions)
        notes = _notes(dimensions, insights)

        return Scorecard(
            ticker=symbol,
            company=company,
            sector=rows[0].sector,
            industry=rows[0].industry,
            period=(period or "FY").upper(),
            price=price,
            market_cap=market_cap,
            generated="",
            dimensions=dimensions,
            overall=overall,
            disagreements=disagreements,
            methodologies=tuple(
                {
                    "name": result.methodology,
                    "verdict": result.verdict.value,
                    "score": result.score,
                    "confidence": result.confidence.value,
                    "red_flags": len(result.red_flags),
                }
                for result in methodology_results
            ),
            data_quality=_data_quality(rows),
            notes=notes,
        )


def _build_dimensions(
    metrics: _Metrics,
    alertset: _Alerts,
    rows: list[NormalizedFinancials],
    dcf: Any,
    market_cap: float | None,
    red_flags: list[str] | None,
) -> tuple[DimensionScore, ...]:
    return (
        _build_dimension(
            "growth",
            _growth_rules(metrics, alertset),
            trend=_metric_trend(metrics.trend("revenue")),
        ),
        _build_dimension(
            "profitability",
            _profitability_rules(metrics, alertset, rows),
            trend=_metric_trend(metrics.trend("net_margin")),
        ),
        _build_dimension(
            "financial_health", _financial_health_rules(metrics, alertset, rows)
        ),
        _build_dimension("valuation", _valuation_rules(metrics, dcf, market_cap)),
        _build_dimension(
            "shareholder_returns", _shareholder_returns_rules(metrics, alertset)
        ),
        _build_dimension(
            "management_moat",
            _management_moat_rules(metrics, rows, red_flags),
        ),
    )


def _metric_trend(trend: str | None) -> str:
    """Map an insight trend to a dimension trend label."""
    if trend == "growing":
        return "improving"
    if trend == "declining":
        return "deteriorating"
    return "stable"


def _company_name(repository: Any, ticker: str) -> str | None:
    getter = getattr(repository, "get_company_name", None)
    if getter is None:
        return None
    return _safe(lambda: getter(ticker))


def _safe(fn: Callable[[], Any]) -> Any:
    """Run ``fn`` and return ``None`` on any failure (degrade, never crash)."""
    try:
        return fn()
    except Exception:  # noqa: BLE001 — one failing source must not break the card
        return None


def _evaluate_dcf(
    ticker: str, rows: list[NormalizedFinancials], price_service: Any
) -> Any:
    from backend.valuation.dcf import DCFValuation

    return DCFValuation().evaluate(ticker, rows, price_service)


def _evaluate_methodologies(
    ticker: str, rows: list[NormalizedFinancials], price_service: Any
) -> list[Any]:
    try:
        discover()
        results = []
        for name in registry.list():
            methodology = registry.get(name)
            if methodology is None:
                continue
            results.append(methodology.evaluate(ticker, rows, price_service))
        return results
    except Exception:  # noqa: BLE001 — methodology context is best-effort
        return []
