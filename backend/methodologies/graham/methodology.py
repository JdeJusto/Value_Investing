"""Graham defensive-investor methodology.

The seven quantitative criteria from *The Intelligent Investor*, Chapter 14,
plus the combined P/E x P/BV <= 22.5 test from the same chapter. Thresholds
are verbatim; the only parameter is ``era_adjustment`` (Decision 4), which
rescales the *size* threshold and nothing else.

The methodology receives already-fetched fundamentals and prices and never
touches the network or the database, so it is deterministic and testable.

Known limitation: criterion 2 (current ratio >= 2:1) needs the split between
current assets and current liabilities. :class:`NormalizedFinancials` carries
``working_capital`` (their difference) but not the two components, so that
criterion returns INSUFFICIENT_DATA unless the caller supplies the split. See
``README.md`` for the full list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import (
    Confidence,
    Methodology,
    MethodologyResult,
    Verdict,
)
from backend.methodologies.common.company_type import is_financial
from backend.methodologies.graham.rules import (
    ALL_RULES,
    VERDICT_CRITERIA,
)

# Verbatim thresholds (Chapter 14).
_MIN_SALES = 100_000_000  # industrial companies, 1973 dollars
_MIN_UTILITY_ASSETS = 50_000_000  # public utilities, 1973 dollars
_MIN_CURRENT_RATIO = 2.0
_MIN_DIVIDEND_YEARS = 20
_MIN_EARNINGS_GROWTH = 1.0 / 3.0  # one third over a decade
_MAX_PE = 15.0
_MAX_PBV = 1.5
_MAX_PE_PBV_PRODUCT = 22.5  # 15 x 1.5

# Decision 4: the only era adjustment. $100M of 1973 sales scaled by the CPI
# ratio 2024/1973 (~5.6) so the *intent* (exclude small companies) survives.
_CPI_RATIO_2024_1973 = 5.6
_SIZE_ADJUSTMENT_NOTE = (
    "$100M of 1973 sales scaled by the CPI ratio 2024/1973 (~5.6); the "
    "valuation thresholds are deliberately left untouched"
)

_VERDICT_NAMES = {rule.id: rule.name for rule in VERDICT_CRITERIA}


@dataclass(frozen=True)
class CriterionResult:
    """Outcome of one criterion: pass, fail, or not evaluable."""

    rule_id: str
    passed: bool | None
    value: float | None
    threshold: float | None
    detail: str


class GrahamMethodology(Methodology):
    """The defensive-investor screen, as a self-contained methodology."""

    name = "graham"
    version = "1.0.0"
    family = "DEEP_VALUE"

    def __init__(self, era_adjustment: bool = False) -> None:
        self.era_adjustment = bool(era_adjustment)
        self._min_sales = (
            _MIN_SALES * _CPI_RATIO_2024_1973 if era_adjustment else _MIN_SALES
        )
        self._min_utility_assets = (
            _MIN_UTILITY_ASSETS * _CPI_RATIO_2024_1973
            if era_adjustment
            else _MIN_UTILITY_ASSETS
        )

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
                methodology=self.name + ("_modernized" if self.era_adjustment else ""),
                version=self.version,
                family=self.family,
                verdict=Verdict.INSUFFICIENT_DATA,
                score=None,
                metrics={
                    "financial_company": True,
                    "criteria_outcomes": {},
                    "current_price": price,
                    "fiscal_years_analyzed": len(rows),
                },
                reasons=[
                    (
                        "Graham defensive criteria do not apply to financial "
                        "companies (banks, insurers). The balance-sheet criteria "
                        "assume an industrial or utility."
                    ),
                    f"verdict: {Verdict.INSUFFICIENT_DATA.value}",
                ],
                red_flags=[],
                confidence=Confidence.HIGH,
                sources=[rule.source for rule in ALL_RULES],
                passed_rules=[],
                failed_rules=[],
            )

        results = [
            self._criterion_1_size(rows),
            self._criterion_2_current_ratio(rows),
            self._criterion_3_debt_vs_working_capital(rows),
            self._criterion_4_dividend_history(rows),
            self._criterion_5_earnings_growth(rows),
            self._criterion_6_pe(rows, price),
            self._criterion_7_pbv(rows, price),
        ]
        combined = self._combined_test(results)

        passed = [r for r in results if r.passed is True]
        failed = [r for r in results if r.passed is False]
        unknown = [r for r in results if r.passed is None]

        verdict, score, confidence = self._verdict(passed, failed, unknown, combined)
        red_flags = self._red_flags(results, combined)
        reasons = self._reasons(results, combined, verdict)

        return MethodologyResult(
            methodology=self.name + ("_modernized" if self.era_adjustment else ""),
            version=self.version,
            family=self.family,
            verdict=verdict,
            score=score,
            metrics=self._metrics(results, combined, price),
            reasons=reasons,
            red_flags=red_flags,
            confidence=confidence,
            sources=[rule.source for rule in ALL_RULES],
            passed_rules=[r.rule_id for r in passed],
            failed_rules=[r.rule_id for r in failed],
        )

    def rules(self):
        return list(ALL_RULES)

    def metadata(self) -> dict:
        label = "graham_modernized" if self.era_adjustment else "graham"
        return {
            "name": self.name,
            "label": label,
            "version": self.version,
            "family": self.family,
            "era_adjustment": self.era_adjustment,
            "size_threshold": self._min_sales,
            "utility_threshold": self._min_utility_assets,
            "source": "The Intelligent Investor, 4th revised (1973), Ch. 14",
            "known_limitations": [
                (
                    "criterion 2 (current ratio >= 2:1) needs the current-assets / "
                    "current-liabilities split, which NormalizedFinancials does not "
                    "carry; it returns INSUFFICIENT_DATA unless supplied"
                ),
                (
                    "criterion 3 uses total_debt as a conservative proxy for "
                    "long-term debt (stricter than the book)"
                ),
                (
                    "criterion 4 counts years with dividends_paid > 0; a missing "
                    "cash-flow statement reads as no dividend"
                ),
                (
                    "written for industrials and utilities; banks and financials do "
                    "not fit the balance-sheet criteria"
                ),
            ],
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_rows(fundamentals: Any) -> list[NormalizedFinancials]:
        rows = [r for r in (fundamentals or []) if r is not None]
        rows.sort(key=lambda r: r.fiscal_year, reverse=True)
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

    def _latest(self, rows: list[NormalizedFinancials]) -> NormalizedFinancials | None:
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    # the seven criteria
    # ------------------------------------------------------------------
    def _criterion_1_size(self, rows) -> CriterionResult:
        latest = self._latest(rows)
        if latest is None or latest.revenue is None:
            return CriterionResult(
                "graham.criterion_1_size",
                None,
                None,
                self._min_sales,
                "no revenue data",
            )
        passed = latest.revenue >= self._min_sales
        return CriterionResult(
            "graham.criterion_1_size",
            passed,
            latest.revenue,
            self._min_sales,
            f"revenue ${latest.revenue:,.0f} vs ${self._min_sales:,.0f}",
        )

    def _criterion_2_current_ratio(self, rows) -> CriterionResult:
        """Current ratio >= 2:1.

        Needs current assets and current liabilities separately. When either
        side is missing the criterion is INSUFFICIENT_DATA rather than
        guessing — see README.md.
        """
        latest = self._latest(rows)
        if (
            latest is None
            or latest.current_assets is None
            or latest.current_liabilities is None
        ):
            return CriterionResult(
                "graham.criterion_2_current_ratio",
                None,
                None,
                _MIN_CURRENT_RATIO,
                "NormalizedFinancials has no current-asset / current-liability split",
            )
        ratio = latest.current_assets / latest.current_liabilities
        passed = ratio >= _MIN_CURRENT_RATIO
        return CriterionResult(
            "graham.criterion_2_current_ratio",
            passed,
            ratio,
            _MIN_CURRENT_RATIO,
            f"current ratio {ratio:.2f} vs {_MIN_CURRENT_RATIO:.1f}",
        )

    def _criterion_3_debt_vs_working_capital(self, rows) -> CriterionResult:
        """Long-term debt <= net working capital.

        Working capital is derived from the balance-sheet split
        (``current_assets - current_liabilities``) so a missing statement never
        reads as zero. ``total_debt`` is used for the debt side, which is >=
        long-term debt, so the test stays stricter than the book's.
        """
        latest = self._latest(rows)
        if latest is None or latest.total_debt is None:
            return CriterionResult(
                "graham.criterion_3_debt_vs_working_capital",
                None,
                None,
                None,
                "no debt or working-capital data",
            )
        working_capital = (
            latest.current_assets - latest.current_liabilities
            if latest.current_assets is not None
            and latest.current_liabilities is not None
            else None
        )
        if working_capital is None:
            return CriterionResult(
                "graham.criterion_3_debt_vs_working_capital",
                None,
                None,
                None,
                "no working-capital data",
            )
        passed = latest.total_debt <= working_capital
        return CriterionResult(
            "graham.criterion_3_debt_vs_working_capital",
            passed,
            latest.total_debt,
            working_capital,
            f"total debt ${latest.total_debt:,.0f} vs working capital "
            f"${working_capital:,.0f}",
        )

    def _criterion_4_dividend_history(self, rows) -> CriterionResult:
        paying = [r for r in rows if (r.dividends_paid or 0) > 0]
        # Only fiscal years with a cash-flow statement can prove a dividend;
        # the count is capped by the history available.
        passed = len(paying) >= _MIN_DIVIDEND_YEARS
        return CriterionResult(
            "graham.criterion_4_dividend_history",
            passed,
            float(len(paying)),
            float(_MIN_DIVIDEND_YEARS),
            f"{len(paying)} years with dividends paid",
        )

    def _criterion_5_earnings_growth(self, rows) -> CriterionResult:
        """EPS growth of at least one third over ten years, 3-year averages."""
        if len(rows) < 10:
            return CriterionResult(
                "graham.criterion_5_earnings_growth",
                None,
                None,
                _MIN_EARNINGS_GROWTH,
                "needs 10 fiscal years",
            )
        recent = [r for r in rows[:3] if r.net_income is not None]
        base = [r for r in rows[-3:] if r.net_income is not None]
        if len(recent) < 3 or len(base) < 3:
            return CriterionResult(
                "graham.criterion_5_earnings_growth",
                None,
                None,
                _MIN_EARNINGS_GROWTH,
                "not enough earnings data",
            )
        recent_avg = sum(r.net_income for r in recent) / 3.0
        base_avg = sum(r.net_income for r in base) / 3.0
        if base_avg <= 0:
            return CriterionResult(
                "graham.criterion_5_earnings_growth",
                None,
                None,
                _MIN_EARNINGS_GROWTH,
                "base period not profitable",
            )
        growth = recent_avg / base_avg - 1.0
        passed = growth >= _MIN_EARNINGS_GROWTH
        return CriterionResult(
            "graham.criterion_5_earnings_growth",
            passed,
            growth,
            _MIN_EARNINGS_GROWTH,
            f"{growth:+.0%} over the decade (3-year averages)",
        )

    def _criterion_6_pe(self, rows, price: float | None) -> CriterionResult:
        if price is None:
            return CriterionResult(
                "graham.criterion_6_pe", None, None, _MAX_PE, "no live price available"
            )
        recent = [r for r in rows[:3] if r.net_income is not None]
        if len(recent) < 3:
            return CriterionResult(
                "graham.criterion_6_pe",
                None,
                None,
                _MAX_PE,
                "needs 3 years of earnings",
            )
        avg_earnings = sum(r.net_income for r in recent) / 3.0
        if avg_earnings <= 0:
            return CriterionResult(
                "graham.criterion_6_pe",
                False,
                None,
                _MAX_PE,
                "average earnings are not positive",
            )
        shares = rows[0].shares_outstanding or 0
        if shares <= 0:
            return CriterionResult(
                "graham.criterion_6_pe", None, None, _MAX_PE, "no share count"
            )
        eps = avg_earnings / shares
        pe = price / eps
        return CriterionResult(
            "graham.criterion_6_pe",
            pe <= _MAX_PE,
            pe,
            _MAX_PE,
            f"P/E {pe:.1f} on 3-year average EPS",
        )

    def _criterion_7_pbv(self, rows, price: float | None) -> CriterionResult:
        if price is None:
            return CriterionResult(
                "graham.criterion_7_pbv",
                None,
                None,
                _MAX_PBV,
                "no live price available",
            )
        latest = self._latest(rows)
        if (
            latest is None
            or latest.stockholders_equity is None
            or latest.stockholders_equity <= 0
        ):
            return CriterionResult(
                "graham.criterion_7_pbv", None, None, _MAX_PBV, "no equity data"
            )
        shares = latest.shares_outstanding or 0
        if shares <= 0:
            return CriterionResult(
                "graham.criterion_7_pbv", None, None, _MAX_PBV, "no share count"
            )
        pbv = price / (latest.stockholders_equity / shares)
        return CriterionResult(
            "graham.criterion_7_pbv",
            pbv <= _MAX_PBV,
            pbv,
            _MAX_PBV,
            f"P/BV {pbv:.2f} on latest book value",
        )

    @staticmethod
    def _combined_test(results: list[CriterionResult]) -> CriterionResult:
        """P/E x P/BV <= 22.5 (Decision 3: gate and metric)."""
        pe = next((r for r in results if r.rule_id == "graham.criterion_6_pe"), None)
        pbv = next((r for r in results if r.rule_id == "graham.criterion_7_pbv"), None)
        if pe is None or pe.value is None or pbv is None or pbv.value is None:
            return CriterionResult(
                "graham.criterion_8_pe_pbv_product",
                None,
                None,
                _MAX_PE_PBV_PRODUCT,
                "needs a live price",
            )
        product = pe.value * pbv.value
        return CriterionResult(
            "graham.criterion_8_pe_pbv_product",
            product <= _MAX_PE_PBV_PRODUCT,
            product,
            _MAX_PE_PBV_PRODUCT,
            f"P/E {pe.value:.1f} x P/BV {pbv.value:.2f}",
        )

    # ------------------------------------------------------------------
    # verdict, score, confidence, flags
    # ------------------------------------------------------------------
    @staticmethod
    def _verdict(
        passed, failed, unknown, combined
    ) -> tuple[Verdict, float | None, Confidence]:
        if len(unknown) > 2:
            return Verdict.INSUFFICIENT_DATA, None, Confidence.LOW
        score = round(len(passed) / len(VERDICT_CRITERIA) * 100, 2)
        if len(passed) >= 6 and combined.passed is True:
            return (
                Verdict.BUY,
                score,
                (Confidence.HIGH if not unknown else Confidence.MEDIUM),
            )
        if len(passed) >= 5:
            return (
                Verdict.WATCH,
                score,
                (Confidence.HIGH if not unknown else Confidence.MEDIUM),
            )
        return Verdict.AVOID, score, Confidence.LOW

    @staticmethod
    def _red_flags(results, combined) -> list[str]:
        flags = []
        for r in results:
            if r.passed is False:
                name = _VERDICT_NAMES.get(r.rule_id, r.rule_id)
                flags.append(f"{name}: {r.detail}")
        if combined.passed is False:
            flags.append(f"Combined P/E x P/BV: {combined.detail}")
        return flags

    @staticmethod
    def _reasons(results, combined, verdict) -> list[str]:
        parts = []
        for r in results:
            mark = (
                "PASS" if r.passed is True else "FAIL" if r.passed is False else "N/A"
            )
            parts.append(f"[{mark}] {r.detail}")
        mark = (
            "PASS"
            if combined.passed is True
            else "FAIL"
            if combined.passed is False
            else "N/A"
        )
        parts.append(f"[{mark}] {combined.detail}")
        parts.append(f"verdict: {verdict.value}")
        return parts

    def _metrics(self, results, combined, price) -> dict[str, Any]:
        metrics: dict[str, Any] = {
            "era_adjustment_applied": self.era_adjustment,
        }
        for r in results:
            key = r.rule_id.replace("graham.", "")
            metrics[key] = r.value
        metrics["pe_pbv_product"] = combined.value
        metrics["current_price"] = price
        return metrics
