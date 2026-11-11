"""Graham & Dodd methodology implementation.

v2.0.0 turns the original four quantitative rules (plus the qualitative
margin-of-safety summary) into weighted results and adds the 21 deep checks in
:mod:`backend.methodologies.graham_dodd.deep_checks`. The aggregation is the
shared weighted ratio introduced for Graham in v0.26.0:

    weighted_score = sum(passed weight) / sum(evaluable weight)

Thresholds: BUY >= 0.85, WATCH >= 0.70, HOLD >= 0.50, else AVOID. More than
30% of the weighted rules missing data returns INSUFFICIENT_DATA. The original
rules keep weight 2 (critical) and the qualitative rule 5 stays informational
(weight 0, it never enters the score).

The framework is taken from Graham & Dodd, *Security Analysis* (1934). It is
deliberately strict: the NCAV/net-net and asset-value tests rarely fire for
modern large caps, and the weighted score must not be read as "the company is
bad" — it is the distance from a 1934 bargain.
"""

from __future__ import annotations

from typing import Any

from backend.methodologies.base import (
    Confidence,
    Methodology,
    MethodologyResult,
    Rule,
    Verdict,
)
from backend.methodologies.common.company_type import (
    financial_na_reason,
    is_financial,
)
from backend.methodologies.common.weighted import (
    WeightedResult,
    weighted_verdict,
)

from .deep_checks import CATEGORIES, CHECKS, run_checks
from .rules import ALL_RULES

#: Weighted-score thresholds (shared with the other deep methodologies).
BUY_THRESHOLD = 0.85
WATCH_THRESHOLD = 0.70
HOLD_THRESHOLD = 0.50

#: Share of missing weight above which the verdict is INSUFFICIENT_DATA.
MAX_MISSING_WEIGHT = 0.30

#: The original rules keep their role: weight 2 for the core quantitative
#: tests, 0 for the qualitative margin-of-safety summary.
_OLD_SPECS: dict[str, tuple[str, str, int]] = {
    "graham_dodd.rule_1_nwc": ("Net Working Capital Test", "net_net", 2),
    "graham_dodd.rule_2_fixed_charge_coverage": (
        "Fixed-Charge Coverage",
        "earnings_power",
        2,
    ),
    "graham_dodd.rule_3_earnings_stability": (
        "Earnings Stability",
        "earnings_power",
        2,
    ),
    "graham_dodd.rule_4_balance_sheet_strength": (
        "Balance Sheet Strength",
        "balance_sheet",
        2,
    ),
    "graham_dodd.rule_5_margin_of_safety": (
        "Margin of Safety",
        "margin_of_safety",
        0,
    ),
}

#: Public weight map for docs/tests/diagnostics.
OLD_WEIGHTS: dict[str, int] = {rule_id: spec[2] for rule_id, spec in _OLD_SPECS.items()}


def _legacy(
    rule_id: str,
    passed: bool | None,
    detail: str,
    *,
    value: float | None = None,
    threshold: float | None = None,
) -> WeightedResult:
    """Build a weighted result for one of the original rules."""
    name, category, weight = _OLD_SPECS[rule_id]
    return WeightedResult(
        rule_id=rule_id,
        name=name,
        category=category,
        weight=weight,
        passed=passed,
        value=value,
        threshold=threshold,
        detail=detail,
    )


class GrahamDoddMethodology(Methodology):
    """Evaluate a company against the Graham & Dodd deep-value criteria."""

    name = "graham_dodd"
    version = "2.0.0"
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
                    financial_na_reason(latest, rows, latest.sector, ticker),
                    f"verdict: {Verdict.NOT_APPLICABLE.value}",
                ],
                red_flags=[],
                confidence=Confidence.HIGH,
                sources=self._sources(),
                passed_rules=[],
                failed_rules=[],
            )

        legacy = [
            self._rule_1_nwc(rows, price),
            self._rule_2_fixed_charge_coverage(rows),
            self._rule_3_earnings_stability(rows),
            self._rule_4_balance_sheet_strength(rows),
        ]
        # The qualitative rule is computed from the four quantitative ones and
        # stays informational (weight 0).
        legacy.append(self._rule_5_margin_of_safety(legacy))
        deep = run_checks(rows, price)
        results = legacy + deep

        verdict, score, confidence = weighted_verdict(results)
        reasons = self._reasons(results, verdict)
        red_flags = [
            f"{result.rule_id}: {result.detail}"
            for result in results
            if result.passed is False
        ]

        return MethodologyResult(
            methodology=self.name,
            version=self.version,
            family=self.family,
            verdict=verdict,
            score=score,
            metrics=self._metrics(results, price, len(rows)),
            reasons=reasons,
            red_flags=red_flags,
            confidence=confidence,
            sources=self._sources(),
            passed_rules=[
                result.rule_id for result in results if result.passed is True
            ],
            failed_rules=[
                result.rule_id for result in results if result.passed is False
            ],
        )

    # ------------------------------------------------------------------
    # Original rules (kept verbatim, now weighted)
    # ------------------------------------------------------------------
    def _rule_1_nwc(self, rows, price: float | None) -> WeightedResult:
        """Price < 2/3 of NWC per share."""
        rule_id = "graham_dodd.rule_1_nwc"
        latest = self._latest(rows)
        if latest is None:
            return _legacy(rule_id, None, "no data")
        if price is None:
            return _legacy(rule_id, None, "no price")
        if latest.current_assets is None or latest.current_liabilities is None:
            return _legacy(rule_id, None, "no current assets/liabilities")
        if latest.shares_outstanding is None or latest.shares_outstanding <= 0:
            return _legacy(rule_id, None, "no shares outstanding")
        nwc = latest.current_assets - latest.current_liabilities
        if nwc <= 0:
            return _legacy(rule_id, None, "negative NWC — cannot evaluate", value=nwc)
        nwc_per_share = nwc / latest.shares_outstanding
        threshold = self._NWC_PRICE_RATIO * nwc_per_share
        if price < threshold:
            return _legacy(
                rule_id,
                True,
                f"price ${price:.2f} < 2/3 NWC/share ${threshold:.2f}",
                value=price,
                threshold=threshold,
            )
        return _legacy(
            rule_id,
            False,
            f"price ${price:.2f} >= 2/3 NWC/share ${threshold:.2f}",
            value=price,
            threshold=threshold,
        )

    def _rule_2_fixed_charge_coverage(self, rows) -> WeightedResult:
        """Operating income / interest expense >= 1.5x in 5 of last 6 years."""
        rule_id = "graham_dodd.rule_2_fixed_charge_coverage"
        if len(rows) < self._COVERAGE_YEARS_TOTAL:
            return _legacy(
                rule_id,
                None,
                f"needs {self._COVERAGE_YEARS_TOTAL} years of data",
            )
        recent = rows[: self._COVERAGE_YEARS_TOTAL]
        years_passed = 0
        years_evaluated = 0
        for row in recent:
            if row.operating_income is None or row.interest_expense is None:
                continue
            years_evaluated += 1
            if row.interest_expense == 0:
                years_passed += 1  # infinite coverage
            elif row.operating_income / row.interest_expense >= self._COVERAGE_MIN:
                years_passed += 1
        if years_evaluated < self._COVERAGE_YEARS_TOTAL:
            return _legacy(rule_id, None, f"only {years_evaluated} years with data")
        passed = years_passed >= self._COVERAGE_YEARS_REQUIRED
        detail = (
            f"coverage >= 1.5x in {years_passed}/{self._COVERAGE_YEARS_TOTAL} years"
        )
        if not passed:
            detail = (
                f"coverage >= 1.5x in only {years_passed}/"
                f"{self._COVERAGE_YEARS_TOTAL} years"
            )
        return _legacy(
            rule_id,
            passed,
            detail,
            value=float(years_passed),
            threshold=float(self._COVERAGE_YEARS_REQUIRED),
        )

    def _rule_3_earnings_stability(self, rows) -> WeightedResult:
        """Net income positive in at least 7 of the last 10 years."""
        rule_id = "graham_dodd.rule_3_earnings_stability"
        if len(rows) < self._EARNINGS_YEARS_TOTAL:
            return _legacy(
                rule_id,
                None,
                f"needs {self._EARNINGS_YEARS_TOTAL} years of data",
            )
        recent = rows[: self._EARNINGS_YEARS_TOTAL]
        years_positive = sum(
            1 for row in recent if row.net_income is not None and row.net_income > 0
        )
        passed = years_positive >= self._EARNINGS_YEARS_REQUIRED
        detail = (
            f"positive earnings in {years_positive}/{self._EARNINGS_YEARS_TOTAL} years"
        )
        if not passed:
            detail = (
                f"positive earnings in only {years_positive}/"
                f"{self._EARNINGS_YEARS_TOTAL} years"
            )
        return _legacy(
            rule_id,
            passed,
            detail,
            value=float(years_positive),
            threshold=float(self._EARNINGS_YEARS_REQUIRED),
        )

    def _rule_4_balance_sheet_strength(self, rows) -> WeightedResult:
        """Total liabilities / total assets <= 0.5."""
        rule_id = "graham_dodd.rule_4_balance_sheet_strength"
        latest = self._latest(rows)
        if latest is None:
            return _legacy(rule_id, None, "no data")
        if latest.total_liabilities is None or latest.total_assets is None:
            return _legacy(rule_id, None, "no liabilities/assets data")
        if latest.total_assets <= 0:
            return _legacy(rule_id, None, "non-positive assets")
        ratio = latest.total_liabilities / latest.total_assets
        passed = ratio <= self._LIABILITIES_TO_ASSETS_MAX
        mark = "<=" if passed else ">"
        return _legacy(
            rule_id,
            passed,
            f"liabilities/assets {ratio:.2f} {mark} {self._LIABILITIES_TO_ASSETS_MAX}",
            value=ratio,
            threshold=self._LIABILITIES_TO_ASSETS_MAX,
        )

    def _rule_5_margin_of_safety(self, results) -> WeightedResult:
        """Qualitative margin of safety — weight 0, never scored.

        The middle branch (NWC fails but the company is otherwise strong) is
        mapped to FAIL rather than N/A: the book's margin of safety is absent,
        and the weighted framework treats an explicit WATCH as False
        (conservative).
        """
        rule_id = "graham_dodd.rule_5_margin_of_safety"
        nwc_pass = results[0].passed is True
        n_failed = sum(1 for result in results if result.passed is False)
        if nwc_pass:
            return _legacy(rule_id, True, "PASS: NWC test suggests deep discount")
        if n_failed >= 3:
            return _legacy(rule_id, False, "FAIL: multiple quantitative rules fail")
        return _legacy(
            rule_id,
            False,
            "WATCH: NWC test fails but company is otherwise strong",
        )

    # ------------------------------------------------------------------
    # Presentation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _reasons(results, verdict: Verdict) -> list[str]:
        reasons: list[str] = []
        for result in results:
            if result.passed is True:
                mark = "✓"
            elif result.passed is False:
                mark = "✗"
            else:
                mark = "?"
            weight = "" if result.weight == 0 else f" x{result.weight}"
            reasons.append(f"{mark}{weight} {result.rule_id}: {result.detail}")
        reasons.append(f"verdict: {verdict.value}")
        return reasons

    def _metrics(self, results, price: float | None, years: int) -> dict[str, Any]:
        metrics: dict[str, Any] = {
            "current_price": price,
            "fiscal_years_analyzed": years,
        }
        for result in results:
            key = result.rule_id.replace("graham_dodd.", "")
            metrics[key] = result.value
        return metrics

    @staticmethod
    def _sources():
        return [rule.source for rule in ALL_RULES] + [check.source for check in CHECKS]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_rows(fundamentals: Any) -> list:
        """Filter and sort rows by fiscal year descending."""
        if fundamentals is None:
            return []
        rows = [row for row in fundamentals if row is not None]
        return sorted(rows, key=lambda row: row.fiscal_year, reverse=True)

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
            value = getter(ticker)
        except Exception:  # noqa: BLE001 — no price is not an error
            return None
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Methodology ABC
    # ------------------------------------------------------------------
    def rules(self) -> list[Rule]:
        return list(ALL_RULES) + [check.rule() for check in CHECKS]

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "family": self.family,
            "book": "Security Analysis",
            "edition": "1st ed. (Spanish translation)",
            "year": "1934",
            "categories": list(CATEGORIES),
            "thresholds": {
                "buy": BUY_THRESHOLD,
                "watch": WATCH_THRESHOLD,
                "hold": HOLD_THRESHOLD,
                "max_missing_weight": MAX_MISSING_WEIGHT,
            },
            "known_limitations": [
                (
                    "NWC / net-net tests are calibrated to Depression-era "
                    "markets; they rarely trigger today for large caps"
                ),
                ("fixed-charge coverage examples are US railroads from 1934"),
                ("no definitive equity criteria — the book itself warns about this"),
                (
                    "tangible book value is approximated by book equity: FDB "
                    "has no intangible-assets field"
                ),
                (
                    "EPV uses a fixed 9% discount rate; a WACC-aware EPV is a "
                    "data-pipeline change"
                ),
                ("long-term debt is proxied by total_debt, which is stricter"),
                (
                    "the 10-year dividend record is a bond requirement in the "
                    "book; applying it to equities is an approximation"
                ),
                ("rule 5 is qualitative and weight 0; it never enters the score"),
            ],
        }
