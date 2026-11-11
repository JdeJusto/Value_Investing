"""Buffett/Clark methodology implementation.

Detects a durable competitive advantage (DCA) from financial-statement
signatures per Mary Buffett & David Clark (2001). The original seven rules
(gross margin, interest burden, margin durability, debt, cash, capex,
retained earnings) are aggregated together with sixteen deep checks from
:mod:`backend.methodologies.buffett_clark.deep_checks` — returns on capital,
owner earnings, valuation and growth — through the shared weighted framework
introduced for Graham in v0.26.0:

    weighted_score = sum(passed weight) / sum(evaluable weight)

Thresholds: BUY >= 0.85, WATCH >= 0.70, HOLD >= 0.50, else AVOID. More than
30% of the weighted rules missing data returns INSUFFICIENT_DATA. A WATCH on a
legacy rule is treated conservatively as not passed (``False``), never as a
pass.

Banks and insurers still abstain (N/A): the leverage and cash-flow rules read
their business model as weakness. REITs are evaluated and carry a visible
``[REIT]`` flag attached externally by the caller (v0.27.0 policy); their FFO
accounting means the score is a rough quality check, not a REIT-specific
valuation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.methodologies.base import (
    Confidence,
    Methodology,
    MethodologyResult,
    Rule,
    Verdict,
)
from backend.methodologies.buffett_clark.deep_checks import (
    CATEGORIES,
    run_checks,
)
from backend.methodologies.buffett_clark.deep_checks import (
    CHECKS as DEEP_CHECKS,
)
from backend.methodologies.buffett_clark.rules import ALL_RULES
from backend.methodologies.common.company_type import (
    financial_na_reason,
    is_financial,
)
from backend.methodologies.common.weighted import (
    WeightedResult,
    weighted_verdict,
)

#: Weighted-score thresholds (shared with Graham v0.26.0).
BUY_THRESHOLD = 0.85
WATCH_THRESHOLD = 0.70
HOLD_THRESHOLD = 0.50

#: Share of missing weight above which the verdict is INSUFFICIENT_DATA.
MAX_MISSING_WEIGHT = 0.30

#: Name, category and weight of the seven original DCA rules. The gross-margin
#: rule is critical (it is the book's central test); the rest are normal.
#: ``rule_5_cash`` keeps a weight of 1 because the book lists cash as a DCA
#: indicator, even though a high cash balance is a weak signal on its own.
_LEGACY_META: dict[str, tuple[str, str, int]] = {
    "buffett_clark.rule_1_gross_margin": (
        "Gross margin >= 40%",
        "durable_advantage",
        2,
    ),
    "buffett_clark.rule_2_interest_burden": (
        "Interest burden <= 10%",
        "durable_advantage",
        1,
    ),
    "buffett_clark.rule_3_margin_durability": (
        "Gross margin durability",
        "durable_advantage",
        1,
    ),
    "buffett_clark.rule_4_debt": ("Low long-term debt", "durable_advantage", 1),
    "buffett_clark.rule_5_cash": ("High cash", "durable_advantage", 1),
    "buffett_clark.rule_6_capex": ("Low capex", "durable_advantage", 1),
    "buffett_clark.rule_7_retained_earnings": (
        "Rising retained earnings",
        "owner_earnings",
        1,
    ),
}


@dataclass
class _RuleResult:
    rule_id: str
    passed: bool | None
    value: float | None
    threshold: float | None
    detail: str


class BuffettClarkMethodology(Methodology):
    """Evaluate a company against the Buffett/Clark DCA criteria."""

    name = "buffett_clark"
    version = "2.0.0"
    family = "QUALITY_COMPOUNDER"

    # ------------------------------------------------------------------
    # Thresholds (from the book)
    # ------------------------------------------------------------------
    _GROSS_MARGIN_PASS = 0.40
    _GROSS_MARGIN_FAIL = 0.20
    _INTEREST_BURDEN_PASS = 0.10
    _INTEREST_BURDEN_FAIL = 0.50
    _MARGIN_DURABILITY_YEARS = 5
    _DEBT_TO_EQUITY_PASS = 0.50
    _CAPEX_TO_FCF_PASS = 0.50

    # ------------------------------------------------------------------
    # Methodology ABC
    # ------------------------------------------------------------------
    def evaluate(
        self,
        ticker: str,
        fundamentals: Any,
        prices: Any,
    ) -> MethodologyResult:
        rows = self._clean_rows(fundamentals)
        latest = self._latest(rows)
        if latest is not None and is_financial(latest, latest.sector):
            return MethodologyResult(
                methodology=self.name,
                version=self.version,
                family=self.family,
                verdict=Verdict.NOT_APPLICABLE,
                score=None,
                metrics={
                    "financial_company": True,
                    "rule_outcomes": {},
                    "fiscal_years_analyzed": len(rows),
                },
                reasons=[
                    (
                        "Buffett/Clark DCA criteria do not apply to financial "
                        "companies (banks, insurers): gross margin, interest "
                        "burden and debt thresholds assume a product company."
                    ),
                    financial_na_reason(latest, rows, latest.sector, ticker),
                    f"verdict: {Verdict.NOT_APPLICABLE.value}",
                ],
                red_flags=[],
                confidence=Confidence.HIGH,
                sources=self._sources(),
                passed_rules=[],
                failed_rules=[],
            )

        price = self._current_price(ticker, prices)
        dcf = self._dcf(ticker, rows, prices, price)
        legacy = self._legacy_results(rows)
        deep = run_checks(rows, price, dcf, prices, ticker)
        results = legacy + deep

        verdict, score, confidence = weighted_verdict(results)

        passed = [result for result in results if result.passed is True]
        failed = [result for result in results if result.passed is False]
        red_flags = [f"{result.rule_id}: {result.detail}" for result in failed]
        reasons = self._reasons(results, verdict)

        metrics: dict[str, Any] = {
            "current_price": price,
            "fiscal_years_analyzed": len(rows),
        }
        for item in legacy:
            key = item.rule_id.replace("buffett_clark.", "")
            metrics[key] = item.value
        for item in deep:
            key = item.rule_id.replace("buffett_clark.deep_", "deep_")
            metrics[key] = item.value
        if dcf is not None:
            metrics["dcf_intrinsic_value"] = getattr(
                dcf, "intrinsic_value_per_share", None
            )
            metrics["dcf_margin_of_safety"] = getattr(dcf, "margin_of_safety", None)

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
            sources=self._sources(),
            passed_rules=[result.rule_id for result in passed],
            failed_rules=[result.rule_id for result in failed],
        )

    def rules(self) -> list[Rule]:
        return list(ALL_RULES) + [check.rule() for check in DEEP_CHECKS]

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "family": self.family,
            "book": "Warren Buffett and the Interpretation of Financial Statements",
            "edition": "1st ed. (Spanish translation)",
            "year": "2001",
            "description": (
                "Buffett/Clark durable-competitive-advantage screen: 23 "
                "explicit rules across durable advantage, owner earnings, "
                "valuation and growth. The verdict is a weighted pass ratio "
                "(critical rules x2, informational x0), not an all-pass gate."
            ),
            "categories": list(CATEGORIES),
            "thresholds": {
                "buy": BUY_THRESHOLD,
                "watch": WATCH_THRESHOLD,
                "hold": HOLD_THRESHOLD,
                "max_missing_weight": MAX_MISSING_WEIGHT,
            },
            "known_limitations": [
                "gross margin thresholds calibrated to US industrials; SaaS may structurally differ",
                "interest burden examples are US airlines/tires from 2001",
                "no valuation method in the book — the DCF and P/E rules are not-from-canon approximations",
                "owner earnings use total capex as a proxy for maintenance capex",
                "the historical-P/E rule needs fiscal-year-end prices and degrades to N/A without them",
                "the 10-year rules need a long history; younger filers lose coverage and may read INSUFFICIENT_DATA",
                "consumer-monopoly/brand qualitative rules are deferred: FDB has no brand/pricing-power evidence",
                (
                    "REITs are evaluated with industrial rules and flagged "
                    "[REIT]; FFO-specific analysis is deferred"
                ),
            ],
        }

    # ------------------------------------------------------------------
    # Weighted aggregation
    # ------------------------------------------------------------------
    def _legacy_results(self, rows) -> list[WeightedResult]:
        raw = [
            self._rule_1_gross_margin(rows),
            self._rule_2_interest_burden(rows),
            self._rule_3_margin_durability(rows),
            self._rule_4_debt(rows),
            self._rule_5_cash(rows),
            self._rule_6_capex(rows),
            self._rule_7_retained_earnings(rows),
        ]
        converted: list[WeightedResult] = []
        for item in raw:
            name, category, weight = _LEGACY_META[item.rule_id]
            converted.append(
                WeightedResult(
                    rule_id=item.rule_id,
                    name=name,
                    category=category,
                    weight=weight,
                    passed=item.passed,
                    detail=item.detail,
                    value=item.value,
                    threshold=item.threshold,
                )
            )
        return converted

    @staticmethod
    def _reasons(results: list[WeightedResult], verdict: Verdict) -> list[str]:
        parts: list[str] = []
        for category in CATEGORIES:
            group = [item for item in results if item.category == category]
            if not group:
                continue
            parts.append(f"{category}:")
            for item in group:
                mark = (
                    "PASS"
                    if item.passed is True
                    else "FAIL"
                    if item.passed is False
                    else "N/A"
                )
                weight = "" if item.weight == 0 else f" x{item.weight}"
                parts.append(f"  [{mark}]{weight} {item.detail}")
        parts.append(f"verdict: {verdict.value}")
        return parts

    @staticmethod
    def _sources():
        return [rule.source for rule in ALL_RULES] + [
            check.source for check in DEEP_CHECKS
        ]

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------
    def _rule_1_gross_margin(self, rows) -> _RuleResult:
        """Gross margin ≥ 40% = DCA; < 20% = competitive industry."""
        latest = self._latest(rows)
        if (
            latest is None
            or latest.gross_profit is None
            or latest.revenue is None
            or latest.revenue <= 0
        ):
            return _RuleResult(
                "buffett_clark.rule_1_gross_margin",
                None,
                None,
                None,
                "no gross margin data",
            )
        margin = latest.gross_profit / latest.revenue
        if margin >= self._GROSS_MARGIN_PASS:
            return _RuleResult(
                "buffett_clark.rule_1_gross_margin",
                True,
                margin,
                self._GROSS_MARGIN_PASS,
                f"gross margin {margin:.1%} ≥ {self._GROSS_MARGIN_PASS:.0%}",
            )
        if margin < self._GROSS_MARGIN_FAIL:
            return _RuleResult(
                "buffett_clark.rule_1_gross_margin",
                False,
                margin,
                self._GROSS_MARGIN_FAIL,
                f"gross margin {margin:.1%} < {self._GROSS_MARGIN_FAIL:.0%}",
            )
        return _RuleResult(
            "buffett_clark.rule_1_gross_margin",
            None,
            margin,
            self._GROSS_MARGIN_PASS,
            f"gross margin {margin:.1%} between thresholds",
        )

    def _rule_2_interest_burden(self, rows) -> _RuleResult:
        """Interest expense ≤ 10% of operating income = DCA."""
        latest = self._latest(rows)
        if (
            latest is None
            or latest.interest_expense is None
            or latest.operating_income is None
        ):
            return _RuleResult(
                "buffett_clark.rule_2_interest_burden",
                None,
                None,
                None,
                "no interest burden data",
            )
        if latest.operating_income <= 0:
            return _RuleResult(
                "buffett_clark.rule_2_interest_burden",
                None,
                None,
                None,
                "non-positive operating income",
            )
        burden = latest.interest_expense / latest.operating_income
        if burden <= self._INTEREST_BURDEN_PASS:
            return _RuleResult(
                "buffett_clark.rule_2_interest_burden",
                True,
                burden,
                self._INTEREST_BURDEN_PASS,
                f"interest burden {burden:.1%} ≤ {self._INTEREST_BURDEN_PASS:.0%}",
            )
        if burden >= self._INTEREST_BURDEN_FAIL:
            return _RuleResult(
                "buffett_clark.rule_2_interest_burden",
                False,
                burden,
                self._INTEREST_BURDEN_FAIL,
                f"interest burden {burden:.1%} ≥ {self._INTEREST_BURDEN_FAIL:.0%}",
            )
        return _RuleResult(
            "buffett_clark.rule_2_interest_burden",
            None,
            burden,
            self._INTEREST_BURDEN_PASS,
            f"interest burden {burden:.1%} between thresholds",
        )

    def _rule_3_margin_durability(self, rows) -> _RuleResult:
        """Gross margin stable or rising over many years."""
        if len(rows) < self._MARGIN_DURABILITY_YEARS:
            return _RuleResult(
                "buffett_clark.rule_3_margin_durability",
                None,
                None,
                None,
                f"needs {self._MARGIN_DURABILITY_YEARS} years of data",
            )
        margins = []
        for r in rows[: self._MARGIN_DURABILITY_YEARS]:
            if r.gross_profit is not None and r.revenue is not None and r.revenue > 0:
                margins.append(r.gross_profit / r.revenue)
        if len(margins) < self._MARGIN_DURABILITY_YEARS:
            return _RuleResult(
                "buffett_clark.rule_3_margin_durability",
                None,
                None,
                None,
                "insufficient margin data",
            )
        # Check if margins are stable or rising (last >= first)
        if margins[0] >= margins[-1] * 0.95:  # 5% tolerance
            return _RuleResult(
                "buffett_clark.rule_3_margin_durability",
                True,
                margins[0],
                margins[-1],
                f"margin stable: {margins[0]:.1%} → {margins[-1]:.1%}",
            )
        return _RuleResult(
            "buffett_clark.rule_3_margin_durability",
            False,
            margins[0],
            margins[-1],
            f"margin eroding: {margins[0]:.1%} → {margins[-1]:.1%}",
        )

    def _rule_4_debt(self, rows) -> _RuleResult:
        """Low long-term debt = DCA indicator."""
        latest = self._latest(rows)
        if (
            latest is None
            or latest.total_debt is None
            or latest.stockholders_equity is None
        ):
            return _RuleResult(
                "buffett_clark.rule_4_debt",
                None,
                None,
                None,
                "no debt data",
            )
        if latest.stockholders_equity <= 0:
            return _RuleResult(
                "buffett_clark.rule_4_debt",
                None,
                None,
                None,
                "non-positive equity",
            )
        ratio = latest.total_debt / latest.stockholders_equity
        if ratio <= self._DEBT_TO_EQUITY_PASS:
            return _RuleResult(
                "buffett_clark.rule_4_debt",
                True,
                ratio,
                self._DEBT_TO_EQUITY_PASS,
                f"debt/equity {ratio:.2f} ≤ {self._DEBT_TO_EQUITY_PASS}",
            )
        return _RuleResult(
            "buffett_clark.rule_4_debt",
            False,
            ratio,
            self._DEBT_TO_EQUITY_PASS,
            f"debt/equity {ratio:.2f} > {self._DEBT_TO_EQUITY_PASS}",
        )

    def _rule_5_cash(self, rows) -> _RuleResult:
        """High cash = DCA indicator."""
        latest = self._latest(rows)
        if (
            latest is None
            or latest.cash_and_equivalents is None
            or latest.total_assets is None
        ):
            return _RuleResult(
                "buffett_clark.rule_5_cash",
                None,
                None,
                None,
                "no cash data",
            )
        if latest.total_assets <= 0:
            return _RuleResult(
                "buffett_clark.rule_5_cash",
                None,
                None,
                None,
                "non-positive assets",
            )
        ratio = latest.cash_and_equivalents / latest.total_assets
        # Cash ≥ 10% of assets is a positive signal
        if ratio >= 0.10:
            return _RuleResult(
                "buffett_clark.rule_5_cash",
                True,
                ratio,
                0.10,
                f"cash/assets {ratio:.1%} ≥ 10%",
            )
        return _RuleResult(
            "buffett_clark.rule_5_cash",
            False,
            ratio,
            0.10,
            f"cash/assets {ratio:.1%} < 10%",
        )

    def _rule_6_capex(self, rows) -> _RuleResult:
        """Low capex relative to FCF = DCA indicator."""
        latest = self._latest(rows)
        if (
            latest is None
            or latest.capital_expenditure is None
            or latest.free_cash_flow is None
        ):
            return _RuleResult(
                "buffett_clark.rule_6_capex",
                None,
                None,
                None,
                "no capex/FCF data",
            )
        if latest.free_cash_flow <= 0:
            return _RuleResult(
                "buffett_clark.rule_6_capex",
                None,
                None,
                None,
                "non-positive FCF",
            )
        ratio = latest.capital_expenditure / latest.free_cash_flow
        if ratio <= self._CAPEX_TO_FCF_PASS:
            return _RuleResult(
                "buffett_clark.rule_6_capex",
                True,
                ratio,
                self._CAPEX_TO_FCF_PASS,
                f"capex/FCF {ratio:.1%} ≤ {self._CAPEX_TO_FCF_PASS:.0%}",
            )
        return _RuleResult(
            "buffett_clark.rule_6_capex",
            False,
            ratio,
            self._CAPEX_TO_FCF_PASS,
            f"capex/FCF {ratio:.1%} > {self._CAPEX_TO_FCF_PASS:.0%}",
        )

    def _rule_7_retained_earnings(self, rows) -> _RuleResult:
        """Rising retained earnings = compounding value."""
        if len(rows) < 2:
            return _RuleResult(
                "buffett_clark.rule_7_retained_earnings",
                None,
                None,
                None,
                "needs 2+ years of data",
            )
        latest = rows[0]
        prior = rows[1]
        if latest.retained_earnings is None or prior.retained_earnings is None:
            return _RuleResult(
                "buffett_clark.rule_7_retained_earnings",
                None,
                None,
                None,
                "no retained earnings data",
            )
        if latest.retained_earnings > prior.retained_earnings:
            return _RuleResult(
                "buffett_clark.rule_7_retained_earnings",
                True,
                latest.retained_earnings,
                prior.retained_earnings,
                f"retained earnings rising: {prior.retained_earnings:,.0f} → {latest.retained_earnings:,.0f}",
            )
        return _RuleResult(
            "buffett_clark.rule_7_retained_earnings",
            False,
            latest.retained_earnings,
            prior.retained_earnings,
            f"retained earnings declining: {prior.retained_earnings:,.0f} → {latest.retained_earnings:,.0f}",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_rows(fundamentals: Any) -> list:
        """Filter and sort rows by fiscal year descending."""
        if fundamentals is None:
            return []
        rows = [r for r in fundamentals if r is not None]
        return sorted(rows, key=lambda r: r.fiscal_year, reverse=True)

    @staticmethod
    def _latest(rows) -> Any | None:
        """Return the most recent row."""
        return rows[0] if rows else None

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
    def _dcf(ticker: str, rows: list, prices: Any, price):
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
