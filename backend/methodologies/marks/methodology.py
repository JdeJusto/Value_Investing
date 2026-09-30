"""``marks`` — Howard Marks' measurable rules (*The Most Important Thing*).

Marks is a qualitative investor: cycles, risk control, second-level
thinking. This methodology implements only the **measurable subset** (like
Fisher's quantitative subset) and says so in every result's sources:

- cycle position (own-history margins and ROIC),
- resilience (leverage, coverage, FCF),
- margin of safety (FCF yield / EV-EBIT),
- quality persistence (5-year ROIC).

Verdict: 25 points per passed rule, adjusted by the cycle reading
(-15 at a peak, +10 at a trough, clamped to 0-100). BUY needs >= 75 with
resilience, margin of safety and quality all passed and no peak reading;
high leverage (net debt/EBITDA > 4) is an automatic AVOID red flag.
Financials abstain (the shared company-type guard): leverage and EV/EBIT
do not mean the same thing for banks.
"""

from __future__ import annotations

import statistics
from typing import Any

from backend.methodologies.base import (
    Confidence,
    Methodology,
    MethodologyResult,
    Verdict,
)
from backend.methodologies.common.company_type import is_financial
from backend.methodologies.marks.rules import (
    ALL_RULES,
    RULE_1_CYCLE,
    RULE_2_RESILIENCE,
    RULE_3_MARGIN_OF_SAFETY,
    RULE_4_QUALITY,
)

#: Minimum years of history for a cycle reading.
MIN_HISTORY_YEARS = 3
#: Full confidence from this many years on.
FULL_HISTORY_YEARS = 5

#: Rule 2 thresholds.
MAX_NET_DEBT_TO_EBITDA = 2.5
MIN_INTEREST_COVERAGE = 4.0
#: Above this, the balance sheet is the risk -> automatic AVOID.
DANGER_NET_DEBT_TO_EBITDA = 4.0
#: Rule 3 thresholds.
MIN_FCF_YIELD = 0.04
MAX_EV_EBIT = 12.0
#: Rule 4 thresholds.
MIN_AVG_ROIC = 0.10
MIN_POSITIVE_ROIC_YEARS = 4
#: Cycle reading thresholds (percentage points vs the company's own mean).
PEAK_TREND_GAP_PP = 3.0
TROUGH_TREND_GAP_PP = -3.0


def _operating_margin(row: Any) -> float | None:
    revenue = getattr(row, "revenue", None)
    operating = getattr(row, "operating_income", None)
    if revenue is None or operating is None or revenue == 0:
        return None
    return operating / revenue


def _roic(row: Any) -> float | None:
    """EBIT / (total debt + equity - cash); None when inputs are missing."""
    ebit = getattr(row, "ebit", None)
    debt = getattr(row, "total_debt", None)
    equity = getattr(row, "stockholders_equity", None)
    cash = getattr(row, "cash_and_equivalents", None)
    if ebit is None or debt is None or equity is None:
        return None
    invested = debt + equity - (cash or 0.0)
    if invested <= 0:
        return None
    return ebit / invested


def _net_debt_to_ebitda(row: Any) -> float | None:
    ebitda = getattr(row, "ebitda", None)
    debt = getattr(row, "total_debt", None)
    cash = getattr(row, "cash_and_equivalents", None)
    if ebitda is None or ebitda <= 0 or debt is None:
        return None
    return (debt - (cash or 0.0)) / ebitda


def _interest_coverage(row: Any) -> float | None:
    ebit = getattr(row, "ebit", None)
    interest = getattr(row, "interest_expense", None)
    if ebit is None or interest is None or interest <= 0:
        return None
    return ebit / interest


def _free_cash_flow(row: Any) -> float | None:
    direct = getattr(row, "free_cash_flow", None)
    if direct is not None:
        return direct
    ocf = getattr(row, "operating_cash_flow", None)
    capex = getattr(row, "capital_expenditure", None)
    if ocf is None or capex is None:
        return None
    return ocf - abs(capex)


def _enterprise_value(row: Any, market_cap: float | None) -> float | None:
    if market_cap is None or market_cap <= 0:
        return None
    debt = getattr(row, "total_debt", None) or 0.0
    cash = getattr(row, "cash_and_equivalents", None) or 0.0
    return market_cap + debt - cash


def _cycle_reading(rows: list[Any], metric: Any) -> tuple[float | None, float | None]:
    """(current, historical mean excluding the current year) for a metric."""
    values = [metric(row) for row in rows]
    current = values[0] if values else None
    prior = [value for value in values[1:] if value is not None]
    if current is None or not prior:
        return current, None
    return current, statistics.fmean(prior)


class MarksMethodology(Methodology):
    """Marks' measurable subset: cycles, resilience, value, quality."""

    name = "marks"
    version = "1.0.0"
    family = "CYCLE_AWARE_VALUE"

    # ------------------------------------------------------------------
    def evaluate(
        self, ticker: str, fundamentals: Any, prices: Any
    ) -> MethodologyResult:
        rows = [row for row in (fundamentals or []) if row is not None]
        latest = rows[0] if rows else None

        if is_financial(latest, getattr(latest, "sector", None)):
            return self._insufficient(
                ticker,
                (
                    "Marks' measurable rules do not apply to financial "
                    "companies: leverage, coverage and EV/EBIT do not mean "
                    "the same thing for banks and insurers."
                ),
            )
        if latest is None or len(rows) < MIN_HISTORY_YEARS:
            return self._insufficient(
                ticker,
                (
                    "Marks' cycle framework needs history: at least "
                    f"{MIN_HISTORY_YEARS} fiscal years are required."
                ),
            )

        market_cap = None
        getter = getattr(prices, "get_market_cap", None)
        if callable(getter):
            try:
                market_cap = getter(ticker)
            except Exception:  # noqa: BLE001 — a missing quote is not an error
                market_cap = None

        # ---- metrics -------------------------------------------------
        margin, margin_mean = _cycle_reading(rows, _operating_margin)
        roic, roic_mean = _cycle_reading(rows, _roic)
        net_debt_ebitda = _net_debt_to_ebitda(latest)
        coverage = _interest_coverage(latest)
        fcf = _free_cash_flow(latest)
        fcf_yield = fcf / market_cap if fcf is not None and market_cap else None
        ev = _enterprise_value(latest, market_cap)
        ev_ebit = (
            ev / latest.ebit
            if ev is not None and getattr(latest, "ebit", None) not in (None, 0)
            else None
        )
        roic_history = [
            value for value in (_roic(row) for row in rows[:5]) if value is not None
        ]
        avg_roic = statistics.fmean(roic_history) if roic_history else None
        positive_roic_years = sum(1 for value in roic_history if value > 0)

        # ---- cycle position -----------------------------------------
        gaps = [
            (current - mean) * 100
            for current, mean in ((margin, margin_mean), (roic, roic_mean))
            if current is not None and mean is not None
        ]
        trend_gap = statistics.fmean(gaps) if gaps else None
        if trend_gap is None:
            cycle_position = "unknown"
        elif trend_gap >= PEAK_TREND_GAP_PP:
            cycle_position = "peak"
        elif trend_gap <= TROUGH_TREND_GAP_PP:
            cycle_position = "trough"
        else:
            cycle_position = "mid"

        # ---- rules ---------------------------------------------------
        resilience_pass = (
            net_debt_ebitda is not None
            and coverage is not None
            and fcf is not None
            and net_debt_ebitda <= MAX_NET_DEBT_TO_EBITDA
            and coverage >= MIN_INTEREST_COVERAGE
            and fcf > 0
        )
        leverage_danger = (
            net_debt_ebitda is not None and net_debt_ebitda > DANGER_NET_DEBT_TO_EBITDA
        )
        margin_of_safety_pass = (
            fcf_yield is not None and fcf_yield >= MIN_FCF_YIELD
        ) or (ev_ebit is not None and ev_ebit <= MAX_EV_EBIT)
        quality_pass = (
            avg_roic is not None
            and avg_roic >= MIN_AVG_ROIC
            and positive_roic_years >= MIN_POSITIVE_ROIC_YEARS
        )
        cycle_pass = cycle_position != "peak"

        passed = {
            RULE_1_CYCLE.id: cycle_pass,
            RULE_2_RESILIENCE.id: resilience_pass,
            RULE_3_MARGIN_OF_SAFETY.id: margin_of_safety_pass,
            RULE_4_QUALITY.id: quality_pass,
        }

        score = 25.0 * sum(1 for ok in passed.values() if ok)
        if cycle_position == "peak":
            score -= 15.0
        elif cycle_position == "trough":
            score += 10.0
        score = max(0.0, min(100.0, score))

        if leverage_danger:
            verdict = Verdict.AVOID
        elif (
            score >= 75.0
            and resilience_pass
            and margin_of_safety_pass
            and quality_pass
            and cycle_position != "peak"
        ):
            verdict = Verdict.BUY
        elif score >= 50.0:
            verdict = Verdict.WATCH
        elif score >= 25.0:
            verdict = Verdict.HOLD
        else:
            verdict = Verdict.AVOID

        confidence = (
            Confidence.HIGH
            if len(rows) >= FULL_HISTORY_YEARS and market_cap is not None
            else Confidence.MEDIUM
        )

        metrics = {
            "cycle_position": cycle_position,
            "margin_trend_pp": round((margin - margin_mean) * 100, 2)
            if margin is not None and margin_mean is not None
            else None,
            "roic_trend_pp": round((roic - roic_mean) * 100, 2)
            if roic is not None and roic_mean is not None
            else None,
            "operating_margin": round(margin, 4) if margin is not None else None,
            "roic": round(roic, 4) if roic is not None else None,
            "avg_roic_5y": round(avg_roic, 4) if avg_roic is not None else None,
            "net_debt_to_ebitda": round(net_debt_ebitda, 2)
            if net_debt_ebitda is not None
            else None,
            "interest_coverage": round(coverage, 2) if coverage is not None else None,
            "fcf_yield": round(fcf_yield, 4) if fcf_yield is not None else None,
            "ev_ebit": round(ev_ebit, 2) if ev_ebit is not None else None,
            "history_years": len(rows),
        }

        reasons = self._reasons(metrics, passed, leverage_danger, market_cap)
        red_flags = []
        if leverage_danger:
            red_flags.append(
                f"net debt/EBITDA {net_debt_ebitda:.1f}x > "
                f"{DANGER_NET_DEBT_TO_EBITDA:.0f}x: the balance sheet is the risk"
            )
        if cycle_position == "peak":
            red_flags.append(
                "returns above their own trend: mean reversion risk (Marks: "
                "the riskiest thing is the belief that there is no risk)"
            )
        reasons.append(f"verdict: {verdict.value}")

        return MethodologyResult(
            methodology=self.name,
            version=self.version,
            family=self.family,
            verdict=verdict,
            score=round(score, 2),
            metrics=metrics,
            reasons=reasons,
            red_flags=red_flags,
            confidence=confidence,
            sources=[rule.source for rule in ALL_RULES],
            passed_rules=[rid for rid, ok in passed.items() if ok],
            failed_rules=[rid for rid, ok in passed.items() if not ok],
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _reasons(
        metrics: dict, passed: dict, leverage_danger: bool, market_cap: float | None
    ) -> list[str]:
        reasons = [
            (
                f"Cycle: {metrics['cycle_position']} "
                f"(margin trend {metrics['margin_trend_pp']} pp, ROIC trend "
                f"{metrics['roic_trend_pp']} pp vs own history)."
            ),
            (
                f"Resilience: net debt/EBITDA {metrics['net_debt_to_ebitda']}x, "
                f"coverage {metrics['interest_coverage']}x, FCF yield "
                f"{metrics['fcf_yield']} -> "
                f"{'PASS' if passed[RULE_2_RESILIENCE.id] else 'FAIL'}."
            ),
            (
                f"Margin of safety: EV/EBIT {metrics['ev_ebit']} -> "
                f"{'PASS' if passed[RULE_3_MARGIN_OF_SAFETY.id] else 'FAIL'}."
            ),
            (
                f"Quality: 5y average ROIC {metrics['avg_roic_5y']} -> "
                f"{'PASS' if passed[RULE_4_QUALITY.id] else 'FAIL'}."
            ),
        ]
        if market_cap is None:
            reasons.append(
                "No market cap (price unavailable): the margin-of-safety rule "
                "could not use FCF yield / EV-EBIT."
            )
        return reasons

    def rules(self) -> list:
        return list(ALL_RULES)

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "label": self.name,
            "version": self.version,
            "family": self.family,
            "source": "The Most Important Thing (2011)",
            "known_limitations": [
                (
                    "qualitative subset: market-wide cycle temperature, the "
                    "pendulum of psychology and second-level thinking are not "
                    "measurable from filings"
                ),
                (
                    "needs at least 3 fiscal years of history for a cycle "
                    "reading; 5+ for HIGH confidence"
                ),
                (
                    "financials abstain (leverage, coverage and EV/EBIT are "
                    "not comparable for banks and insurers)"
                ),
            ],
        }

    # ------------------------------------------------------------------
    def _insufficient(self, ticker: str, reason: str) -> MethodologyResult:
        return MethodologyResult(
            methodology=self.name,
            version=self.version,
            family=self.family,
            verdict=Verdict.INSUFFICIENT_DATA,
            score=None,
            metrics={"financial_company": "financial" in reason},
            reasons=[reason, f"verdict: {Verdict.INSUFFICIENT_DATA.value}"],
            red_flags=[],
            confidence=Confidence.HIGH,
            sources=[rule.source for rule in ALL_RULES],
            passed_rules=[],
            failed_rules=[],
        )
