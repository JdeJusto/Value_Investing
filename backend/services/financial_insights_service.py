"""Computed insights (growth, stability) over a company's FDB facts.

Pure computation over ``financial_facts`` rows — the same list the Financials
view renders (no second data source, no network, no LLM). For each key metric
it finds the value per fiscal year, then derives the latest value, the YoY
change, 5/10-year CAGRs, a 5-year average, a trend label and a stability
label. Percent-kind metrics (margins, ROE/ROA, FCF conversion) report their
YoY in percentage points for display, per the panel's convention.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from backend.repositories.fdb_concept_mapping import (
    BALANCE_SHEET_CONCEPTS,
    CASH_FLOW_FIELD_PRIORITY,
    DEBT_CURRENT_PRIORITY,
    DEBT_NONCURRENT_PRIORITY,
    INCOME_FIELD_PRIORITY,
    INCOME_STATEMENT_CONCEPTS,
)
from backend.services.demo_mode import DEMO_ROOT
from backend.services.financials_view_service import dedupe_facts, format_fact_value

#: How many of the newest values the 5-year average/stability window uses.
_WINDOW = 5
#: CV threshold between a stable and a volatile series (B3.6).
_STABLE_CV = 0.2


@dataclass(frozen=True)
class MetricInsight:
    """One metric's derived statistics (all fields preformatted for display)."""

    metric: str  # "revenue", "net_income", ...
    label: str  # "Revenue"
    latest_value: str  # formatted like the source ("$391,035", "24.0%")
    latest_year: int | None
    yoy_change_pct: float | None  # relative % change per B3.2
    cagr_5y: float | None
    cagr_10y: float | None
    average_5y: str | None  # formatted
    trend: str  # "growing" | "stable" | "declining"
    stability: str  # "stable" | "volatile"
    direction_changed: bool  # sign changed YoY
    notes: list[str]
    #: Display kind ("currency" | "per_share" | "shares" | "percent" | "ratio").
    kind: str = "currency"
    #: Preformatted YoY ("+8.2%", "-1.3pp", "—").
    yoy_display: str = "—"
    cagr_5y_display: str = "—"
    cagr_10y_display: str = "—"
    #: Raw per-year values behind the statistics (fiscal_year -> value).
    series: dict[int, float] = field(default_factory=dict)
    #: Percentage-point change for percent-kind metrics (else None).
    yoy_pp: float | None = None


@dataclass
class InsightsReport:
    ticker: str
    company_name: str
    metrics: list[MetricInsight]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _MetricSpec:
    metric: str
    label: str
    kind: str
    concepts: tuple[str, ...] = ()
    #: ("numerator metric", "denominator metric") ratio of two level series.
    derived_ratio: tuple[str, str] | None = None
    #: Named special series computed in ``_series_for``.
    special: str | None = None


def _field_concepts(mapping: dict[str, str], field: str) -> tuple[str, ...]:
    """Concepts mapped to ``field``, in mapping (priority) order."""
    return tuple(concept for concept, mapped in mapping.items() if mapped == field)


_METRIC_SPECS: tuple[_MetricSpec, ...] = (
    # Income statement.
    _MetricSpec(
        "revenue",
        "Revenue",
        "currency",
        concepts=tuple(INCOME_FIELD_PRIORITY["revenue"]),
    ),
    _MetricSpec(
        "gross_profit",
        "Gross Profit",
        "currency",
        concepts=_field_concepts(INCOME_STATEMENT_CONCEPTS, "gross_profit"),
    ),
    _MetricSpec(
        "operating_income",
        "Operating Income",
        "currency",
        concepts=_field_concepts(INCOME_STATEMENT_CONCEPTS, "operating_income"),
    ),
    _MetricSpec(
        "operating_expenses",
        "Operating Expenses",
        "currency",
        concepts=_field_concepts(INCOME_STATEMENT_CONCEPTS, "operating_expense"),
    ),
    _MetricSpec(
        "net_income",
        "Net Income",
        "currency",
        concepts=tuple(INCOME_FIELD_PRIORITY["net_income"]),
    ),
    _MetricSpec(
        "eps_basic", "EPS (Basic)", "per_share", concepts=("EarningsPerShareBasic",)
    ),
    _MetricSpec(
        "eps_diluted",
        "EPS (Diluted)",
        "per_share",
        concepts=("EarningsPerShareDiluted",),
    ),
    # Balance sheet.
    _MetricSpec(
        "total_assets",
        "Total Assets",
        "currency",
        concepts=_field_concepts(BALANCE_SHEET_CONCEPTS, "total_assets"),
    ),
    _MetricSpec(
        "total_liabilities",
        "Total Liabilities",
        "currency",
        concepts=_field_concepts(BALANCE_SHEET_CONCEPTS, "total_liabilities"),
    ),
    _MetricSpec(
        "stockholders_equity",
        "Stockholders' Equity",
        "currency",
        concepts=_field_concepts(BALANCE_SHEET_CONCEPTS, "stockholders_equity"),
    ),
    _MetricSpec(
        "cash",
        "Cash and Cash Equivalents",
        "currency",
        concepts=_field_concepts(BALANCE_SHEET_CONCEPTS, "cash_and_equivalents"),
    ),
    _MetricSpec(
        "inventory",
        "Inventory",
        "currency",
        concepts=_field_concepts(BALANCE_SHEET_CONCEPTS, "inventory"),
    ),
    _MetricSpec(
        "short_term_investments",
        "Short-Term Investments",
        "currency",
        concepts=(
            "ShortTermInvestments",
            "MarketableSecuritiesCurrent",
            "AvailableForSaleSecuritiesCurrent",
        ),
    ),
    _MetricSpec(
        "long_term_debt",
        "Long-Term Debt",
        "currency",
        concepts=tuple(DEBT_NONCURRENT_PRIORITY),
    ),
    _MetricSpec("total_debt", "Total Debt", "currency", special="total_debt"),
    _MetricSpec(
        "diluted_shares",
        "Diluted Shares Outstanding",
        "shares",
        concepts=(
            "WeightedAverageNumberOfDilutedSharesOutstanding",
            "WeightedAverageNumberOfSharesOutstandingDiluted",
        ),
    ),
    # Cash flow.
    _MetricSpec(
        "operating_cash_flow",
        "Operating Cash Flow",
        "currency",
        concepts=tuple(CASH_FLOW_FIELD_PRIORITY["operating_cash_flow"]),
    ),
    _MetricSpec(
        "capital_expenditure",
        "Capital Expenditure",
        "currency",
        concepts=tuple(CASH_FLOW_FIELD_PRIORITY["capital_expenditure"]),
    ),
    _MetricSpec("free_cash_flow", "Free Cash Flow", "currency", special="fcf"),
    _MetricSpec(
        "dividends_paid",
        "Dividends Paid",
        "currency",
        concepts=tuple(CASH_FLOW_FIELD_PRIORITY["dividends_paid"]),
    ),
    # Derived ratios (components are defined above, so they resolve in order).
    _MetricSpec(
        "gross_margin",
        "Gross Margin",
        "percent",
        derived_ratio=("gross_profit", "revenue"),
    ),
    _MetricSpec(
        "operating_margin",
        "Operating Margin",
        "percent",
        derived_ratio=("operating_income", "revenue"),
    ),
    _MetricSpec(
        "net_margin", "Net Margin", "percent", derived_ratio=("net_income", "revenue")
    ),
    _MetricSpec(
        "roe",
        "Return on Equity",
        "percent",
        derived_ratio=("net_income", "stockholders_equity"),
    ),
    _MetricSpec(
        "roa",
        "Return on Assets",
        "percent",
        derived_ratio=("net_income", "total_assets"),
    ),
    _MetricSpec(
        "debt_to_equity",
        "Debt-to-Equity",
        "ratio",
        derived_ratio=("total_debt", "stockholders_equity"),
    ),
    _MetricSpec(
        "fcf_conversion",
        "FCF Conversion",
        "percent",
        derived_ratio=("free_cash_flow", "net_income"),
    ),
)


def format_metric_value(kind: str, value: float | None) -> str:
    """Statement-convention formatting, shared with the Financials tables."""
    if value is None:
        return "—"
    if kind == "currency":
        return format_fact_value(Decimal(str(value)), "USD")
    if kind == "per_share":
        return format_fact_value(Decimal(str(value)), "USD/shares")
    if kind == "shares":
        return format_fact_value(Decimal(str(value)), "shares")
    if kind == "percent":
        return f"{value * 100:.1f}%"
    return f"{value:.2f}"  # ratio


def _format_change(value: float | None, suffix: str) -> str:
    if value is None:
        return "—"
    return f"{value:+.1f}{suffix}"


def _yoy(latest: float | None, prior: float | None) -> float | None:
    """Relative change per B3.2; None when either side is missing/zero."""
    if latest is None or prior is None or prior == 0:
        return None
    return (latest - prior) / abs(prior) * 100


def _pp_change(latest: float | None, prior: float | None) -> float | None:
    if latest is None or prior is None:
        return None
    return (latest - prior) * 100


def _cagr(series: dict[int, float], window: int) -> float | None:
    """Compound annual growth over ``window`` years (B3.3).

    Uses the oldest value within the window; requires a span of at least
    ``window - 1`` years and **strictly positive** endpoints. A negative
    ratio would make ``ratio ** (1 / span)`` a complex number in Python 3
    (e.g. a loss year), so non-positive base/latest return ``None`` and the
    trend falls back to the YoY change.
    """
    if not series:
        return None
    latest_year = max(series)
    candidates = [year for year in series if year >= latest_year - window]
    if not candidates:
        return None
    base_year = min(candidates)
    span = latest_year - base_year
    if span < window - 1:
        return None
    base = series[base_year]
    latest = series[latest_year]
    if base <= 0 or latest <= 0:
        return None
    result = ((latest / base) ** (1 / span) - 1) * 100
    # Belt and braces: with positive endpoints the result is real, but a
    # complex value must never reach the trend comparisons.
    return result if isinstance(result, float) else None


def _average_5y(series: dict[int, float]) -> float | None:
    values = [value for _, value in sorted(series.items(), reverse=True)[:_WINDOW]]
    if not values:
        return None
    return sum(values) / len(values)


def _stability(series: dict[int, float]) -> str:
    """CV of the last five YoY changes (B3.6): stable when CV < 0.2."""
    ordered = [
        value for _, value in sorted(series.items(), reverse=True)[: _WINDOW + 1]
    ]
    changes = [_yoy(ordered[i], ordered[i + 1]) for i in range(len(ordered) - 1)]
    changes = [change for change in changes if change is not None]
    if len(changes) < 2:
        return "stable"
    mean = statistics.fmean(changes)
    if mean == 0:
        return "stable" if statistics.stdev(changes) == 0 else "volatile"
    cv = statistics.stdev(changes) / abs(mean)
    return "stable" if cv < _STABLE_CV else "volatile"


def _trend(
    kind: str, cagr_5y: float | None, yoy: float | None, series: dict[int, float]
) -> str:
    """B3.5 trend; percent-kind metrics fall back to their YoY (in pp)."""
    if cagr_5y is not None and not isinstance(cagr_5y, (int, float)):
        # Safety net: the _cagr guard never returns a complex, but a future
        # regression must not crash the comparisons below.
        cagr_5y = None
    if cagr_5y is not None:
        if cagr_5y > 5 or (
            cagr_5y > 0
            and all(
                value >= 0
                for _, value in sorted(series.items(), reverse=True)[:_WINDOW]
            )
        ):
            return "growing"
        if cagr_5y < -5:
            return "declining"
        return "stable"
    if yoy is not None:
        delta = yoy
        if kind == "percent":
            # The YoY of a percent metric is its pp change (no CAGR case).
            ordered = sorted(series.items(), reverse=True)
            if len(ordered) >= 2:
                delta = _pp_change(ordered[0][1], ordered[1][1]) or 0.0
        if delta > 5:
            return "growing"
        if delta < -5:
            return "declining"
    return "stable"


def _direction_changed(series: dict[int, float]) -> bool:
    ordered = [value for _, value in sorted(series.items(), reverse=True)[:3]]
    if len(ordered) < 3:
        return False
    latest = _yoy(ordered[0], ordered[1])
    previous = _yoy(ordered[1], ordered[2])
    if latest is None or previous is None:
        return False
    return (latest > 0) != (previous > 0)


def _notes(spec: _MetricSpec, latest: float | None, prior: float | None) -> list[str]:
    notes: list[str] = []
    if latest is None:
        notes.append("not reported")
        return notes
    if spec.metric == "net_income" and prior is not None:
        if prior < 0 < latest:
            notes.append("turnaround from loss to profit")
        elif latest < 0 < prior:
            notes.append("profit to loss")
    if latest < 0:
        notes.append("negative value")
    return notes


class FinancialInsightsService:
    """Derives growth/stability insights from one company's fact rows."""

    def __init__(
        self,
        facts: list[dict],
        ticker: str = "",
        company_name: str = "",
    ) -> None:
        self._facts = list(facts or [])
        self._ticker = ticker
        self._company_name = company_name

    def build(self) -> InsightsReport:
        by_concept: dict[str, dict[int, float]] = {}
        years: set[int] = set()
        for (concept, year), fact in dedupe_facts(
            self._facts, self._all_years()
        ).items():
            value = fact.get("value")
            if value is None:
                continue
            by_concept.setdefault(concept, {})[year] = float(Decimal(str(value)))
            years.add(year)

        series_by_metric: dict[str, dict[int, float]] = {}
        metrics: list[MetricInsight] = []
        for spec in _METRIC_SPECS:
            series = self._series_for(spec, by_concept, series_by_metric)
            series_by_metric[spec.metric] = series
            metrics.append(self._insight(spec, series))

        warnings: list[str] = []
        if not self._facts:
            warnings.append("no facts available for this company")
        return InsightsReport(
            ticker=self._ticker,
            company_name=self._company_name,
            metrics=metrics,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    def _all_years(self) -> set[int]:
        return {
            int(fact["fiscal_year"])
            for fact in self._facts
            if fact.get("fiscal_year") is not None
        }

    @staticmethod
    def _concept_series(
        concepts: tuple[str, ...], by_concept: dict[str, dict[int, float]]
    ) -> dict[int, float]:
        """First concept (priority order) with a value wins for each year."""
        series: dict[int, float] = {}
        for concept in concepts:
            for year, value in by_concept.get(concept, {}).items():
                series.setdefault(year, value)
        return series

    def _series_for(
        self,
        spec: _MetricSpec,
        by_concept: dict[str, dict[int, float]],
        series_by_metric: dict[str, dict[int, float]],
    ) -> dict[int, float]:
        if spec.special == "fcf":
            ocf = series_by_metric.get("operating_cash_flow", {})
            capex = series_by_metric.get("capital_expenditure", {})
            return {year: ocf[year] - capex[year] for year in ocf if year in capex}
        if spec.special == "total_debt":
            current = self._concept_series(tuple(DEBT_CURRENT_PRIORITY), by_concept)
            noncurrent = self._concept_series(
                tuple(DEBT_NONCURRENT_PRIORITY), by_concept
            )
            return {
                year: current.get(year, 0.0) + noncurrent.get(year, 0.0)
                for year in set(current) | set(noncurrent)
            }
        if spec.derived_ratio is not None:
            numerator = series_by_metric.get(spec.derived_ratio[0], {})
            denominator = series_by_metric.get(spec.derived_ratio[1], {})
            return {
                year: numerator[year] / denominator[year]
                for year in numerator
                if year in denominator and denominator[year] != 0
            }
        return self._concept_series(spec.concepts, by_concept)

    def _insight(self, spec: _MetricSpec, series: dict[int, float]) -> MetricInsight:
        ordered = sorted(series.items(), reverse=True)
        latest_year = ordered[0][0] if ordered else None
        latest = ordered[0][1] if ordered else None
        prior = ordered[1][1] if len(ordered) > 1 else None
        yoy = _yoy(latest, prior)
        pp = _pp_change(latest, prior)
        cagr_5y = _cagr(series, 5)
        cagr_10y = _cagr(series, 10)
        average = _average_5y(series)
        return MetricInsight(
            metric=spec.metric,
            label=spec.label,
            latest_value=format_metric_value(spec.kind, latest),
            latest_year=latest_year,
            yoy_change_pct=yoy,
            cagr_5y=cagr_5y,
            cagr_10y=cagr_10y,
            average_5y=format_metric_value(spec.kind, average),
            trend=_trend(spec.kind, cagr_5y, yoy, series),
            stability=_stability(series),
            direction_changed=_direction_changed(series),
            notes=_notes(spec, latest, prior),
            kind=spec.kind,
            yoy_display=(
                _format_change(pp, "pp")
                if spec.kind == "percent"
                else _format_change(yoy, "%")
            ),
            cagr_5y_display=_format_change(cagr_5y, "%"),
            cagr_10y_display=_format_change(cagr_10y, "%"),
            series=dict(series),
            yoy_pp=pp if spec.kind == "percent" else None,
        )


def insight_rows(report: InsightsReport) -> list[dict[str, str]]:
    """Dataframe-ready summary rows (the panel's table and its CSV export)."""
    return [
        {
            "Metric": insight.label,
            "Latest": insight.latest_value,
            "YoY": insight.yoy_display,
            "5y CAGR": insight.cagr_5y_display,
            "Trend": insight.trend,
            "Stability": insight.stability,
        }
        for insight in report.metrics
    ]


def report_to_payload(report: InsightsReport) -> dict[str, Any]:
    """Display subset for the demo fixture (~5 KB), see ``report_from_payload``."""
    return {
        "ticker": report.ticker,
        "company_name": report.company_name,
        "warnings": list(report.warnings),
        "metrics": [
            {
                "metric": insight.metric,
                "label": insight.label,
                "latest_value": insight.latest_value,
                "yoy_display": insight.yoy_display,
                "cagr_5y_display": insight.cagr_5y_display,
                "trend": insight.trend,
                "stability": insight.stability,
                "notes": list(insight.notes),
            }
            for insight in report.metrics
        ],
    }


def report_from_payload(payload: dict[str, Any]) -> InsightsReport:
    """Rebuild the demo report; raw floats are display-only in demo mode."""
    metrics = [
        MetricInsight(
            metric=str(row.get("metric") or ""),
            label=str(row.get("label") or ""),
            latest_value=str(row.get("latest_value") or "—"),
            latest_year=row.get("latest_year"),
            yoy_change_pct=None,
            cagr_5y=None,
            cagr_10y=None,
            average_5y=None,
            trend=str(row.get("trend") or "stable"),
            stability=str(row.get("stability") or "stable"),
            direction_changed=False,
            notes=list(row.get("notes") or []),
            yoy_display=str(row.get("yoy_display") or "—"),
            cagr_5y_display=str(row.get("cagr_5y_display") or "—"),
        )
        for row in payload.get("metrics", [])
    ]
    return InsightsReport(
        ticker=str(payload.get("ticker") or ""),
        company_name=str(payload.get("company_name") or ""),
        metrics=metrics,
        warnings=list(payload.get("warnings") or []),
    )


def load_demo_insights(ticker: str) -> InsightsReport | None:
    """The pinned insights fixture for demo mode, or None when absent."""
    path = DEMO_ROOT / "financials" / f"{ticker.upper().strip()}_insights.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return report_from_payload(payload)
