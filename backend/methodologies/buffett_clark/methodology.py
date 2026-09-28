"""Buffett/Clark methodology implementation.

Detects durable competitive advantage (DCA) from financial-statement
signatures per Mary Buffett & David Clark (2001).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.methodologies.base import (
    Confidence,
    Methodology,
    MethodologyResult,
    Verdict,
)

from .rules import ALL_RULES


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
    version = "1.0.0"
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
        results = [
            self._rule_1_gross_margin(rows),
            self._rule_2_interest_burden(rows),
            self._rule_3_margin_durability(rows),
            self._rule_4_debt(rows),
            self._rule_5_cash(rows),
            self._rule_6_capex(rows),
            self._rule_7_retained_earnings(rows),
        ]

        passed = [r for r in results if r.passed is True]
        failed = [r for r in results if r.passed is False]
        unknown = [r for r in results if r.passed is None]

        verdict = self._verdict(passed, failed, unknown)
        score = self._score(passed, failed, unknown)
        confidence = self._confidence(results)
        red_flags = self._red_flags(results)
        reasons = self._reasons(results, verdict)

        return MethodologyResult(
            methodology=self.name,
            version=self.version,
            family=self.family,
            verdict=verdict,
            score=score,
            metrics=self._metrics(results),
            reasons=reasons,
            red_flags=red_flags,
            confidence=confidence,
            sources=[rule.source for rule in ALL_RULES],
            passed_rules=[r.rule_id for r in passed],
            failed_rules=[r.rule_id for r in failed],
        )

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------
    def _rule_1_gross_margin(self, rows) -> _RuleResult:
        """Gross margin ≥ 40% = DCA; < 20% = competitive industry."""
        latest = self._latest(rows)
        if latest is None or latest.gross_profit is None or latest.revenue is None:
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
    # Verdict / score / confidence
    # ------------------------------------------------------------------
    def _verdict(self, passed, failed, unknown) -> Verdict:
        """BUY if ≥5 of 7 pass; WATCH if 4; HOLD if 3; AVOID if <3."""
        n_passed = len(passed)
        if n_passed >= 5:
            return Verdict.BUY
        if n_passed == 4:
            return Verdict.WATCH
        if n_passed == 3:
            return Verdict.HOLD
        return Verdict.AVOID

    def _score(self, passed, failed, unknown) -> float | None:
        """Score = passed / 7 × 100."""
        return round(len(passed) / 7 * 100, 2)

    def _confidence(self, results) -> Confidence:
        """HIGH if all 7 evaluated; MEDIUM if 1-2 unknown; LOW otherwise."""
        n_unknown = sum(1 for r in results if r.passed is None)
        if n_unknown == 0:
            return Confidence.HIGH
        if n_unknown <= 2:
            return Confidence.MEDIUM
        return Confidence.LOW

    def _red_flags(self, results) -> list[str]:
        flags = []
        for r in results:
            if r.passed is False:
                flags.append(f"{r.rule_id}: {r.detail}")
        return flags

    def _reasons(self, results, verdict) -> list[str]:
        reasons = []
        for r in results:
            if r.passed is True:
                reasons.append(f"✓ {r.rule_id}: {r.detail}")
            elif r.passed is False:
                reasons.append(f"✗ {r.rule_id}: {r.detail}")
            else:
                reasons.append(f"? {r.rule_id}: {r.detail}")
        return reasons

    def _metrics(self, results) -> dict[str, Any]:
        metrics: dict[str, Any] = {}
        for r in results:
            key = r.rule_id.replace("buffett_clark.", "")
            metrics[key] = r.value
        return metrics

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

    # ------------------------------------------------------------------
    # Methodology ABC
    # ------------------------------------------------------------------
    def rules(self):
        return ALL_RULES

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "family": self.family,
            "book": "Warren Buffett and the Interpretation of Financial Statements",
            "edition": "1st ed. (Spanish translation)",
            "year": "2001",
            "known_limitations": [
                "gross margin thresholds calibrated to US industrials; SaaS may structurally differ",
                "interest burden examples are US airlines/tires from 2001",
                "no valuation method — the book explains how to find DCA companies but not how to value them",
            ],
        }
