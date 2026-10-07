"""Graham & Dodd methodology implementation.

Detects deep value from balance-sheet signatures per Graham & Dodd,
Security Analysis (1934).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.methodologies.base import (
    FINANCIAL_NA_REASON,
    Confidence,
    Methodology,
    MethodologyResult,
    Verdict,
)
from backend.methodologies.common.company_type import is_financial

from .rules import ALL_RULES


@dataclass
class _RuleResult:
    rule_id: str
    passed: bool | None
    value: float | None
    threshold: float | None
    detail: str


class GrahamDoddMethodology(Methodology):
    """Evaluate a company against the Graham & Dodd deep-value criteria."""

    name = "graham_dodd"
    version = "1.0.0"
    family = "DEEP_VALUE"

    # ------------------------------------------------------------------
    # Thresholds (from the book)
    # ------------------------------------------------------------------
    _NWC_PRICE_RATIO = 2.0 / 3.0  # price < 2/3 of NWC per share
    _COVERAGE_MIN = 1.5
    _COVERAGE_YEARS_REQUIRED = 5
    _COVERAGE_YEARS_TOTAL = 6
    _EARNINGS_YEARS_REQUIRED = 7
    _EARNINGS_YEARS_TOTAL = 10
    _LIABILITIES_TO_ASSETS_MAX = 0.5

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
        price = self._current_price(ticker, prices)

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
                    "current_price": price,
                    "fiscal_years_analyzed": len(rows),
                },
                reasons=[
                    (
                        "Graham & Dodd deep-value criteria do not apply to "
                        "financial companies (banks, insurers): NWC, earnings "
                        "stability and balance-sheet strength assume a product "
                        "company."
                    ),
                    FINANCIAL_NA_REASON,
                    f"verdict: {Verdict.NOT_APPLICABLE.value}",
                ],
                red_flags=[],
                confidence=Confidence.HIGH,
                sources=[rule.source for rule in ALL_RULES],
                passed_rules=[],
                failed_rules=[],
            )

        results = [
            self._rule_1_nwc(rows, price),
            self._rule_2_fixed_charge_coverage(rows),
            self._rule_3_earnings_stability(rows),
            self._rule_4_balance_sheet_strength(rows),
        ]

        passed = [r for r in results if r.passed is True]
        failed = [r for r in results if r.passed is False]
        unknown = [r for r in results if r.passed is None]

        verdict = self._verdict(passed, failed, unknown)
        score = self._score(passed, failed, unknown)
        confidence = self._confidence(results)
        red_flags = self._red_flags(results)
        reasons = self._reasons(results, verdict)

        # Rule 5 (qualitative) — does NOT contribute to score
        rule5 = self._rule_5_margin_of_safety(results, verdict)
        reasons.append(rule5.detail)

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
    def _rule_1_nwc(self, rows, price: float | None) -> _RuleResult:
        """Price < 2/3 of NWC per share."""
        latest = self._latest(rows)
        if latest is None:
            return _RuleResult("graham_dodd.rule_1_nwc", None, None, None, "no data")
        if price is None:
            return _RuleResult("graham_dodd.rule_1_nwc", None, None, None, "no price")
        if latest.current_assets is None or latest.current_liabilities is None:
            return _RuleResult(
                "graham_dodd.rule_1_nwc",
                None,
                None,
                None,
                "no current assets/liabilities",
            )
        if latest.shares_outstanding is None or latest.shares_outstanding <= 0:
            return _RuleResult(
                "graham_dodd.rule_1_nwc",
                None,
                None,
                None,
                "no shares outstanding",
            )
        nwc = latest.current_assets - latest.current_liabilities
        if nwc <= 0:
            return _RuleResult(
                "graham_dodd.rule_1_nwc",
                None,
                nwc,
                None,
                "negative NWC — cannot evaluate",
            )
        nwc_per_share = nwc / latest.shares_outstanding
        threshold = self._NWC_PRICE_RATIO * nwc_per_share
        if price < threshold:
            return _RuleResult(
                "graham_dodd.rule_1_nwc",
                True,
                price,
                threshold,
                f"price ${price:.2f} < 2/3 NWC/share ${threshold:.2f}",
            )
        return _RuleResult(
            "graham_dodd.rule_1_nwc",
            False,
            price,
            threshold,
            f"price ${price:.2f} >= 2/3 NWC/share ${threshold:.2f}",
        )

    def _rule_2_fixed_charge_coverage(self, rows) -> _RuleResult:
        """Operating income / interest expense >= 1.5x in 5 of last 6 years."""
        if len(rows) < self._COVERAGE_YEARS_TOTAL:
            return _RuleResult(
                "graham_dodd.rule_2_fixed_charge_coverage",
                None,
                None,
                None,
                f"needs {self._COVERAGE_YEARS_TOTAL} years of data",
            )
        recent = rows[: self._COVERAGE_YEARS_TOTAL]
        years_passed = 0
        years_evaluated = 0
        for r in recent:
            if r.operating_income is None or r.interest_expense is None:
                continue
            years_evaluated += 1
            if r.interest_expense == 0:
                years_passed += 1  # infinite coverage
            elif r.operating_income / r.interest_expense >= self._COVERAGE_MIN:
                years_passed += 1
        if years_evaluated < self._COVERAGE_YEARS_TOTAL:
            return _RuleResult(
                "graham_dodd.rule_2_fixed_charge_coverage",
                None,
                None,
                None,
                f"only {years_evaluated} years with data",
            )
        if years_passed >= self._COVERAGE_YEARS_REQUIRED:
            return _RuleResult(
                "graham_dodd.rule_2_fixed_charge_coverage",
                True,
                years_passed,
                self._COVERAGE_YEARS_REQUIRED,
                f"coverage >= 1.5x in {years_passed}/{self._COVERAGE_YEARS_TOTAL} years",
            )
        return _RuleResult(
            "graham_dodd.rule_2_fixed_charge_coverage",
            False,
            years_passed,
            self._COVERAGE_YEARS_REQUIRED,
            f"coverage >= 1.5x in only {years_passed}/{self._COVERAGE_YEARS_TOTAL} years",
        )

    def _rule_3_earnings_stability(self, rows) -> _RuleResult:
        """Net income positive in at least 7 of the last 10 years."""
        if len(rows) < self._EARNINGS_YEARS_TOTAL:
            return _RuleResult(
                "graham_dodd.rule_3_earnings_stability",
                None,
                None,
                None,
                f"needs {self._EARNINGS_YEARS_TOTAL} years of data",
            )
        recent = rows[: self._EARNINGS_YEARS_TOTAL]
        years_positive = sum(
            1 for r in recent if r.net_income is not None and r.net_income > 0
        )
        if years_positive >= self._EARNINGS_YEARS_REQUIRED:
            return _RuleResult(
                "graham_dodd.rule_3_earnings_stability",
                True,
                years_positive,
                self._EARNINGS_YEARS_REQUIRED,
                f"positive earnings in {years_positive}/{self._EARNINGS_YEARS_TOTAL} years",
            )
        return _RuleResult(
            "graham_dodd.rule_3_earnings_stability",
            False,
            years_positive,
            self._EARNINGS_YEARS_REQUIRED,
            f"positive earnings in only {years_positive}/{self._EARNINGS_YEARS_TOTAL} years",
        )

    def _rule_4_balance_sheet_strength(self, rows) -> _RuleResult:
        """Total liabilities / total assets <= 0.5."""
        latest = self._latest(rows)
        if latest is None:
            return _RuleResult(
                "graham_dodd.rule_4_balance_sheet_strength",
                None,
                None,
                None,
                "no data",
            )
        if latest.total_liabilities is None or latest.total_assets is None:
            return _RuleResult(
                "graham_dodd.rule_4_balance_sheet_strength",
                None,
                None,
                None,
                "no liabilities/assets data",
            )
        if latest.total_assets <= 0:
            return _RuleResult(
                "graham_dodd.rule_4_balance_sheet_strength",
                None,
                None,
                None,
                "non-positive assets",
            )
        ratio = latest.total_liabilities / latest.total_assets
        if ratio <= self._LIABILITIES_TO_ASSETS_MAX:
            return _RuleResult(
                "graham_dodd.rule_4_balance_sheet_strength",
                True,
                ratio,
                self._LIABILITIES_TO_ASSETS_MAX,
                f"liabilities/assets {ratio:.2f} <= {self._LIABILITIES_TO_ASSETS_MAX}",
            )
        return _RuleResult(
            "graham_dodd.rule_4_balance_sheet_strength",
            False,
            ratio,
            self._LIABILITIES_TO_ASSETS_MAX,
            f"liabilities/assets {ratio:.2f} > {self._LIABILITIES_TO_ASSETS_MAX}",
        )

    def _rule_5_margin_of_safety(self, results, verdict) -> _RuleResult:
        """Qualitative margin of safety — does NOT contribute to score."""
        r1 = results[0]
        n_failed = sum(1 for r in results if r.passed is False)

        if r1.passed:
            return _RuleResult(
                "graham_dodd.rule_5_margin_of_safety",
                True,
                None,
                None,
                "PASS: NWC test suggests deep discount",
            )
        if n_failed >= 3:
            return _RuleResult(
                "graham_dodd.rule_5_margin_of_safety",
                False,
                None,
                None,
                "FAIL: multiple quantitative rules fail",
            )
        return _RuleResult(
            "graham_dodd.rule_5_margin_of_safety",
            None,
            None,
            None,
            "WATCH: NWC test fails but company is otherwise strong",
        )

    # ------------------------------------------------------------------
    # Verdict / score / confidence
    # ------------------------------------------------------------------
    def _verdict(self, passed, failed, unknown) -> Verdict:
        """BUY if rule 1 PASS AND rule 2 PASS AND (rule 3 PASS OR WATCH)."""
        n_passed = len(passed)
        n_unknown = len(unknown)

        if n_unknown > 2:
            return Verdict.INSUFFICIENT_DATA

        # Check specific conditions
        r1_pass = any(
            r.rule_id == "graham_dodd.rule_1_nwc" and r.passed for r in passed
        )
        r2_pass = any(
            r.rule_id == "graham_dodd.rule_2_fixed_charge_coverage" and r.passed
            for r in passed
        )
        r3_pass = any(
            r.rule_id == "graham_dodd.rule_3_earnings_stability" and r.passed
            for r in passed
        )
        r4_fail = any(
            r.rule_id == "graham_dodd.rule_4_balance_sheet_strength"
            and r.passed is False
            for r in failed
        )

        if r4_fail:
            return Verdict.AVOID

        if r1_pass and r2_pass and r3_pass:
            return Verdict.BUY

        if r1_pass and not r2_pass:
            return Verdict.WATCH
        if not r1_pass and r2_pass:
            return Verdict.WATCH

        if n_passed >= 2:
            return Verdict.HOLD

        return Verdict.AVOID

    def _score(self, passed, failed, unknown) -> float | None:
        """Score = (quantitative_passed / 4) * 100."""
        if len(unknown) > 2:
            return None
        return round(len(passed) / 4 * 100, 2)

    def _confidence(self, results) -> Confidence:
        """HIGH if all 4 quantitative rules evaluable."""
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
            key = r.rule_id.replace("graham_dodd.", "")
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

    @staticmethod
    def _current_price(ticker: str, prices: Any) -> float | None:
        """Get current price from the price service."""
        if prices is None:
            return None
        getter = getattr(prices, "get_current_price", None)
        if getter is None:
            return None
        try:
            return getter(ticker)
        except Exception:  # noqa: BLE001 — no price is not an error
            return None

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
            "book": "Security Analysis",
            "edition": "1st ed. (Spanish translation)",
            "year": "1934",
            "known_limitations": [
                "NWC test calibrated to Depression-era markets; rarely triggers today for large caps",
                "fixed-charge coverage examples are US railroads from 1934",
                "no definitive equity criteria — the book itself warns about this",
            ],
        }
