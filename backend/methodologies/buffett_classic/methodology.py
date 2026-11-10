"""``buffett_classic`` — Buffett/Munger quality compounder screen.

v0.27.0 replaces the wrapped 4-pillar score with an explicit 20-rule
framework (see :mod:`backend.methodologies.buffett_classic.rules`). The
philosophy is unchanged: durable high returns on capital, conservative
finances, honest owner earnings and a sensible price. The aggregation is the
same weighted score introduced for Graham in v0.26.0, so the two deep
methodologies stay comparable:

    weighted_score = sum(passed weight) / sum(evaluable weight)

Thresholds: BUY >= 0.85, WATCH >= 0.70, HOLD >= 0.50, else AVOID. More than
30% of the weighted rules missing data returns INSUFFICIENT_DATA. The base
verdict feeds the v0.24 demote-only tiers unchanged.

Banks and insurers still abstain (N/A): the leverage and cash-flow rules read
their business model as weakness. REITs are evaluated and carry a visible
``[REIT]`` flag (v0.27.0 policy); their FFO accounting means the score is a
rough quality check, not a REIT-specific valuation.
"""

from __future__ import annotations

from typing import Any

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import (
    Confidence,
    Methodology,
    MethodologyResult,
    Rule,
    Verdict,
)
from backend.methodologies.buffett_classic.rules import (
    CATEGORIES,
    CHECKS,
    run_checks,
)
from backend.methodologies.common.company_type import (
    financial_na_reason,
    is_financial,
)

#: Weighted-score thresholds (shared with Graham v0.26.0).
BUY_THRESHOLD = 0.85
WATCH_THRESHOLD = 0.70
HOLD_THRESHOLD = 0.50

#: Share of missing weight above which the verdict is INSUFFICIENT_DATA.
MAX_MISSING_WEIGHT = 0.30


class BuffettClassicMethodology(Methodology):
    """Buffett/Munger quality screen with weighted, explicit rules."""

    name = "buffett_classic"
    version = "2.0.0"
    family = "QUALITY_COMPOUNDER"

    # -- Methodology -----------------------------------------------------
    def evaluate(
        self, ticker: str, fundamentals: Any, prices: Any
    ) -> MethodologyResult:
        rows = self._clean_rows(fundamentals)
        if not rows:
            return MethodologyResult(
                methodology=self.name,
                version=self.version,
                family=self.family,
                verdict=Verdict.INSUFFICIENT_DATA,
                score=None,
                metrics={},
                reasons=["No fundamentals available for " + str(ticker)],
                red_flags=[],
                confidence=Confidence.LOW,
                sources=[check.source for check in CHECKS],
            )

        latest = rows[0]
        if is_financial(latest, getattr(latest, "sector", None)):
            return MethodologyResult(
                methodology=self.name,
                version=self.version,
                family=self.family,
                verdict=Verdict.NOT_APPLICABLE,
                score=None,
                metrics={
                    "financial_company": True,
                    "fiscal_years_analyzed": len(rows),
                },
                reasons=[
                    (
                        "buffett_classic does not apply to financial companies "
                        "(banks, insurers): the leverage and owner-earnings "
                        "rules read their business model as weakness."
                    ),
                    financial_na_reason(
                        latest, rows, getattr(latest, "sector", None), ticker
                    ),
                    f"verdict: {Verdict.NOT_APPLICABLE.value}",
                ],
                red_flags=[],
                confidence=Confidence.HIGH,
                sources=[check.source for check in CHECKS],
                passed_rules=[],
                failed_rules=[],
            )

        price = self._current_price(ticker, prices)
        dcf = self._dcf(ticker, rows, prices, price)
        results = run_checks(rows, price, dcf)
        verdict, score, confidence = self._weighted_verdict(results)

        metrics: dict[str, Any] = {
            "current_price": price,
            "fiscal_years_analyzed": len(rows),
        }
        for result in results:
            key = result.rule_id.replace("buffett.", "")
            metrics[key] = result.value
        if dcf is not None:
            metrics["dcf_intrinsic_value"] = getattr(
                dcf, "intrinsic_value_per_share", None
            )
            metrics["dcf_margin_of_safety"] = getattr(dcf, "margin_of_safety", None)

        passed = [result for result in results if result.passed is True]
        failed = [result for result in results if result.passed is False]
        reasons = self._reasons(results, verdict)
        red_flags = [f"{result.name}: {result.detail}" for result in failed]

        return MethodologyResult(
            methodology=self.name,
            version=self.version,
            family=self.family,
            verdict=verdict,
            score=score,
            metrics=metrics,
            reasons=reasons,
            red_flags=red_flags,
            confidence=confidence,
            sources=[check.source for check in CHECKS],
            passed_rules=[result.rule_id for result in passed],
            failed_rules=[result.rule_id for result in failed],
        )

    def rules(self) -> list[Rule]:
        return [check.rule() for check in CHECKS]

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "family": self.family,
            "description": (
                "Buffett-style quality compounder: 20 explicit rules across "
                "moat, financial strength, earnings quality, capital "
                "allocation, valuation and management. The verdict is a "
                "weighted pass ratio (critical rules x2, informational x0), "
                "not an all-pass gate."
            ),
            "categories": list(CATEGORIES),
            "source": {
                "book": "Berkshire Hathaway shareholder letters",
                "edition": "1977-2023 (selected letters)",
                "year": 1977,
            },
            "thresholds": {
                "buy": BUY_THRESHOLD,
                "watch": WATCH_THRESHOLD,
                "hold": HOLD_THRESHOLD,
                "max_missing_weight": MAX_MISSING_WEIGHT,
            },
            "known_limitations": [
                (
                    "Owner earnings use capex as a proxy for maintenance "
                    "capex; FDB has no maintenance-capex line."
                ),
                (
                    "DCF margin of safety is the not-from-canon two-stage "
                    "valuation and is N/A when the price service cannot "
                    "provide beta or the model lacks inputs."
                ),
                (
                    "Insider ownership and qualitative moat evidence are not "
                    "in FDB; they are informational (weight 0)."
                ),
                (
                    "REITs are evaluated with industrial rules and flagged "
                    "[REIT]; FFO-specific analysis is a v0.28+ backlog item."
                ),
            ],
        }

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _clean_rows(fundamentals: Any) -> list[NormalizedFinancials]:
        rows = [row for row in (fundamentals or []) if row is not None]
        # Drop all-empty fiscal years (a row with no income and no balance).
        rows = [
            row
            for row in rows
            if any(
                value is not None
                for value in (row.revenue, row.net_income, row.total_assets)
            )
        ]
        rows.sort(key=lambda row: row.fiscal_year, reverse=True)
        return rows

    @staticmethod
    def _current_price(ticker: str, prices: Any) -> float | None:
        getter = getattr(prices, "get_current_price", None)
        if not callable(getter):
            return None
        try:
            value = getter(ticker)
        except Exception:  # noqa: BLE001 — no price is not an error
            return None
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _dcf(ticker: str, rows: list[NormalizedFinancials], prices: Any, price):
        """Best-effort DCF; missing beta/inputs degrade the rule to N/A."""
        if price is None or not rows:
            return None
        try:
            from backend.valuation.dcf import DCFValuation

            result = DCFValuation().evaluate(ticker, rows, prices)
        except Exception:  # noqa: BLE001 — DCF is an optional rule input
            return None
        if getattr(result, "margin_of_safety", None) is None:
            return None
        return result

    @staticmethod
    def _weighted_verdict(
        results,
    ) -> tuple[Verdict, float | None, Confidence]:
        weighted = [
            (result.passed, result.weight) for result in results if result.weight > 0
        ]
        total_all = sum(weight for _passed, weight in weighted)
        insufficient = sum(weight for passed, weight in weighted if passed is None)
        if total_all <= 0 or insufficient / total_all > MAX_MISSING_WEIGHT:
            return Verdict.INSUFFICIENT_DATA, None, Confidence.LOW
        evaluable = [
            (passed, weight) for passed, weight in weighted if passed is not None
        ]
        total = sum(weight for _passed, weight in evaluable)
        if total <= 0:
            return Verdict.INSUFFICIENT_DATA, None, Confidence.LOW
        passed_weight = sum(weight for passed, weight in evaluable if passed)
        ratio = passed_weight / total
        if ratio >= BUY_THRESHOLD:
            verdict = Verdict.BUY
        elif ratio >= WATCH_THRESHOLD:
            verdict = Verdict.WATCH
        elif ratio >= HOLD_THRESHOLD:
            verdict = Verdict.HOLD
        else:
            verdict = Verdict.AVOID
        confidence = (
            Confidence.HIGH
            if insufficient == 0
            else Confidence.MEDIUM
            if insufficient / total_all <= 0.10
            else Confidence.LOW
        )
        return verdict, round(ratio * 100, 2), confidence

    @staticmethod
    def _reasons(results, verdict: Verdict) -> list[str]:
        parts: list[str] = []
        for category in CATEGORIES:
            group = [result for result in results if result.category == category]
            if not group:
                continue
            parts.append(f"{category}:")
            for result in group:
                mark = (
                    "PASS"
                    if result.passed is True
                    else "FAIL"
                    if result.passed is False
                    else "N/A"
                )
                weight = "" if result.weight == 0 else f" x{result.weight}"
                parts.append(f"  [{mark}]{weight} {result.detail}")
        parts.append(f"verdict: {verdict.value}")
        return parts
