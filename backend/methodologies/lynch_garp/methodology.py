"""Lynch GARP (Growth At a Reasonable Price) methodology.

Peter Lynch's core quantitative screen from *One Up on Wall Street* (1989)
and *Beating the Street* (1993): buy growth at a reasonable multiple, not
growth at any price. The central metric is the PEG ratio (P/E divided by the
earnings growth rate); the supporting rules keep the growth story honest
(consistency), the balance sheet conservative (debt), the operating story
coherent (inventory watching sales) and the valuation dividend-aware.

The methodology receives already-fetched fundamentals and prices and never
touches the network or the database, so it is deterministic and testable.

Known limitations (see ``README.md``):
- written for product companies; financials do not fit the inventory rule or
  the debt model;
- the growth rate is a geometric CAGR over the available earnings history and
  its precision depends on the source and span of the data;
- Lynch expects the investor to first categorize the company (fast grower,
  stalwart, slow grower, cyclical, turnaround, asset play); this
  implementation applies the same rules to every company.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from backend.domain.value_objects.financials_normalized import NormalizedFinancials
from backend.methodologies.base import (
    Confidence,
    Methodology,
    MethodologyResult,
    Verdict,
)
from backend.methodologies.lynch_garp.rules import (
    ALL_RULES,
    RULE_5_DIVIDEND_ADJUSTED_PEG,
    VERDICT_RULES,
)

# Verbatim thresholds from the books.
_PEG_PASS = 1.0
_PEG_WATCH = 1.5
_MIN_GROWTH_YEARS = 7
_WATCH_GROWTH_YEARS = 5
_DEBT_PASS = 2.0
_DEBT_WATCH = 4.0
_INVENTORY_WATCH_FACTOR = 1.5

_PASS = "PASS"
_WATCH = "WATCH"
_FAIL = "FAIL"
_INSUFFICIENT = "INSUFFICIENT_DATA"

_FLAG_BY_RULE = {
    "lynch_garp.rule_1_peg": "PEG above 1.5 (paying too much for growth)",
    "lynch_garp.rule_2_growth_consistency": (
        "Earnings declined in 4+ of the last 10 years"
    ),
    "lynch_garp.rule_3_debt_conservatism": "Long-term debt above 4x net income",
    "lynch_garp.rule_4_inventory_vs_sales": ("Inventory growing 50% faster than sales"),
    "lynch_garp.rule_5_dividend_adjusted_peg": ("Dividend-adjusted PEG above 1.5"),
}


@dataclass(frozen=True)
class RuleOutcome:
    """Outcome of one rule: PASS, WATCH, FAIL or INSUFFICIENT_DATA."""

    rule_id: str
    outcome: str
    value: Optional[float] = None
    threshold: Optional[float] = None
    detail: str = ""


class LynchGARPMethodology(Methodology):
    """The GARP screen, as a self-contained book methodology."""

    name = "lynch_garp"
    version = "1.0.0"
    family = "GARP"

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

        outcomes = [
            self._rule_1_peg(rows, price),
            self._rule_2_growth_consistency(rows),
            self._rule_3_debt_conservatism(rows),
            self._rule_4_inventory_vs_sales(rows),
            self._rule_5_dividend_adjusted_peg(rows, price),
        ]

        verdict, score, confidence = self._verdict(outcomes)
        red_flags = self._red_flags(outcomes)
        reasons = self._reasons(outcomes, verdict)

        return MethodologyResult(
            methodology=self.name,
            version=self.version,
            family=self.family,
            verdict=verdict,
            score=score,
            metrics=self._metrics(outcomes, price, rows),
            reasons=reasons,
            red_flags=red_flags,
            confidence=confidence,
            sources=[rule.source for rule in ALL_RULES],
            passed_rules=[o.rule_id for o in outcomes if o.outcome == _PASS],
            failed_rules=[o.rule_id for o in outcomes if o.outcome == _FAIL],
        )

    def rules(self) -> list:
        return list(ALL_RULES)

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "label": self.name,
            "version": self.version,
            "family": self.family,
            "source": ("One Up on Wall Street (1989); Beating the Street (1993)"),
            "known_limitations": [
                "does not apply to financials (no inventory line; different "
                "debt model)",
                "growth-rate estimation depends on the source and span of the "
                "earnings CAGR",
                "Lynch expects the investor to categorize companies (fast "
                "grower, stalwart, slow grower, cyclical, turnaround, asset "
                "play); this implementation treats all companies the same",
                "rule 3 prefers long_term_debt, falling back to total_debt "
                "(stricter than the book's long-term-debt-only comparison)",
                "rule 4 reads the optional inventory field; companies that "
                "report no inventory get a WATCH with a note",
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
    def _current_price(ticker: str, prices: Any) -> Optional[float]:
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
    def _earnings_cagr(rows: list[NormalizedFinancials]) -> Optional[float]:
        """Geometric CAGR of net income over the available profitable years."""
        profit = sorted(
            [r for r in rows if r.net_income is not None and r.net_income > 0],
            key=lambda r: r.fiscal_year,
        )
        if len(profit) < 2:
            return None
        start = profit[0].net_income
        end = profit[-1].net_income
        years = profit[-1].fiscal_year - profit[0].fiscal_year
        if start <= 0 or end <= 0 or years <= 0:
            return None
        return (end / start) ** (1.0 / years) - 1.0

    @staticmethod
    def _eps(row: NormalizedFinancials) -> Optional[float]:
        if row is None or row.net_income is None or (row.shares_outstanding or 0) <= 0:
            return None
        return row.net_income / row.shares_outstanding

    # ------------------------------------------------------------------
    # the five rules
    # ------------------------------------------------------------------
    def _rule_1_peg(self, rows, price: Optional[float]) -> RuleOutcome:
        if price is None:
            return RuleOutcome(
                "lynch_garp.rule_1_peg",
                _INSUFFICIENT,
                None,
                _PEG_PASS,
                "no live price available",
            )
        latest = rows[0] if rows else None
        eps = self._eps(latest)
        if eps is None or eps <= 0:
            return RuleOutcome(
                "lynch_garp.rule_1_peg",
                _INSUFFICIENT,
                None,
                _PEG_PASS,
                "no earnings or share count",
            )
        pe = price / eps
        growth = self._earnings_cagr(rows)
        if growth is None:
            return RuleOutcome(
                "lynch_garp.rule_1_peg",
                _INSUFFICIENT,
                None,
                _PEG_PASS,
                "no earnings-growth series (needs 2+ profitable years)",
            )
        if growth <= 0:
            return RuleOutcome(
                "lynch_garp.rule_1_peg",
                _FAIL,
                None,
                _PEG_PASS,
                f"PEG undefined: earnings growth {growth:+.1%}",
            )
        peg = pe / (growth * 100.0)
        detail = f"PEG {peg:.2f} (P/E {pe:.1f} / growth {growth:.1%})"
        if peg <= _PEG_PASS:
            return RuleOutcome("lynch_garp.rule_1_peg", _PASS, peg, _PEG_PASS, detail)
        if peg <= _PEG_WATCH:
            return RuleOutcome("lynch_garp.rule_1_peg", _WATCH, peg, _PEG_WATCH, detail)
        return RuleOutcome("lynch_garp.rule_1_peg", _FAIL, peg, _PEG_WATCH, detail)

    def _rule_2_growth_consistency(self, rows) -> RuleOutcome:
        if len(rows) < 10:
            return RuleOutcome(
                "lynch_garp.rule_2_growth_consistency",
                _INSUFFICIENT,
                None,
                float(_MIN_GROWTH_YEARS),
                "needs 10 fiscal years",
            )
        ordered = sorted(rows, key=lambda r: r.fiscal_year)[-10:]
        eps_list = [self._eps(r) for r in ordered]
        comparisons = [
            eps_list[i] > eps_list[i - 1]
            for i in range(1, len(eps_list))
            if eps_list[i] is not None and eps_list[i - 1] is not None
        ]
        if len(comparisons) < 9:
            return RuleOutcome(
                "lynch_garp.rule_2_growth_consistency",
                _INSUFFICIENT,
                None,
                float(_MIN_GROWTH_YEARS),
                "no year-over-year EPS comparisons available",
            )
        grew = sum(1 for c in comparisons if c)
        detail = f"EPS grew in {grew} of {len(comparisons)} year-over-year comparisons"
        if grew >= _MIN_GROWTH_YEARS:
            return RuleOutcome(
                "lynch_garp.rule_2_growth_consistency",
                _PASS,
                float(grew),
                float(_MIN_GROWTH_YEARS),
                detail,
            )
        if grew >= _WATCH_GROWTH_YEARS:
            return RuleOutcome(
                "lynch_garp.rule_2_growth_consistency",
                _WATCH,
                float(grew),
                float(_MIN_GROWTH_YEARS),
                detail,
            )
        return RuleOutcome(
            "lynch_garp.rule_2_growth_consistency",
            _FAIL,
            float(grew),
            float(_MIN_GROWTH_YEARS),
            detail,
        )

    def _rule_3_debt_conservatism(self, rows) -> RuleOutcome:
        latest = rows[0] if rows else None
        if latest is None or latest.net_income is None or latest.net_income <= 0:
            return RuleOutcome(
                "lynch_garp.rule_3_debt_conservatism",
                _INSUFFICIENT,
                None,
                _DEBT_PASS,
                "net income is not positive",
            )
        debt = latest.long_term_debt
        if debt is None:
            debt = latest.total_debt
        if debt is None:
            return RuleOutcome(
                "lynch_garp.rule_3_debt_conservatism",
                _INSUFFICIENT,
                None,
                _DEBT_PASS,
                "no debt data",
            )
        ratio = debt / latest.net_income
        detail = (
            f"debt / net income {ratio:.2f} (long-term debt, falling back "
            "to total_debt when it is not reported)"
        )
        if ratio <= _DEBT_PASS:
            return RuleOutcome(
                "lynch_garp.rule_3_debt_conservatism",
                _PASS,
                ratio,
                _DEBT_PASS,
                detail,
            )
        if ratio <= _DEBT_WATCH:
            return RuleOutcome(
                "lynch_garp.rule_3_debt_conservatism",
                _WATCH,
                ratio,
                _DEBT_WATCH,
                detail,
            )
        return RuleOutcome(
            "lynch_garp.rule_3_debt_conservatism",
            _FAIL,
            ratio,
            _DEBT_WATCH,
            detail,
        )

    def _rule_4_inventory_vs_sales(self, rows) -> RuleOutcome:
        if len(rows) < 2:
            return RuleOutcome(
                "lynch_garp.rule_4_inventory_vs_sales",
                _INSUFFICIENT,
                None,
                _INVENTORY_WATCH_FACTOR,
                "needs two fiscal years",
            )
        latest, prev = rows[0], rows[1]
        inv_l = getattr(latest, "inventory", None)
        inv_p = getattr(prev, "inventory", None)
        if inv_l is None and inv_p is None:
            return RuleOutcome(
                "lynch_garp.rule_4_inventory_vs_sales",
                _WATCH,
                None,
                _INVENTORY_WATCH_FACTOR,
                "no inventory reported — typical for service/asset-light "
                "companies; inventory watch not applicable",
            )
        if (
            inv_l is None
            or inv_p is None
            or inv_l == 0
            or inv_p == 0
            or latest.revenue is None
            or prev.revenue is None
            or prev.revenue == 0
        ):
            return RuleOutcome(
                "lynch_garp.rule_4_inventory_vs_sales",
                _INSUFFICIENT,
                None,
                _INVENTORY_WATCH_FACTOR,
                "inventory or revenue data incomplete",
            )
        inv_growth = inv_l / inv_p - 1.0
        sales_growth = latest.revenue / prev.revenue - 1.0
        detail = f"inventory growth {inv_growth:.1%} vs sales growth {sales_growth:.1%}"
        if inv_growth <= sales_growth:
            return RuleOutcome(
                "lynch_garp.rule_4_inventory_vs_sales",
                _PASS,
                inv_growth,
                sales_growth,
                detail,
            )
        if inv_growth <= _INVENTORY_WATCH_FACTOR * sales_growth:
            return RuleOutcome(
                "lynch_garp.rule_4_inventory_vs_sales",
                _WATCH,
                inv_growth,
                _INVENTORY_WATCH_FACTOR * sales_growth,
                detail,
            )
        return RuleOutcome(
            "lynch_garp.rule_4_inventory_vs_sales",
            _FAIL,
            inv_growth,
            _INVENTORY_WATCH_FACTOR * sales_growth,
            detail,
        )

    def _rule_5_dividend_adjusted_peg(
        self, rows, price: Optional[float]
    ) -> RuleOutcome:
        latest = rows[0] if rows else None
        dividends = (latest.dividends_paid or 0) if latest else 0
        if dividends <= 0:
            return RuleOutcome(
                RULE_5_DIVIDEND_ADJUSTED_PEG.id,
                _INSUFFICIENT,
                None,
                _PEG_PASS,
                "company pays no dividends",
            )
        eps = self._eps(latest)
        if price is None or eps is None or eps <= 0:
            return RuleOutcome(
                RULE_5_DIVIDEND_ADJUSTED_PEG.id,
                _INSUFFICIENT,
                None,
                _PEG_PASS,
                "no price or earnings for the dividend-adjusted PEG",
            )
        growth = self._earnings_cagr(rows)
        if growth is None or growth <= 0:
            return RuleOutcome(
                RULE_5_DIVIDEND_ADJUSTED_PEG.id,
                _INSUFFICIENT,
                None,
                _PEG_PASS,
                "no earnings-growth series for the dividend-adjusted PEG",
            )
        pe = price / eps
        yield_ = (dividends / latest.shares_outstanding) / price
        pegy = (pe / (growth * 100.0)) / (1.0 + yield_)
        detail = f"PEGY {pegy:.2f} (dividend yield {yield_:.2%})"
        if pegy <= _PEG_PASS:
            return RuleOutcome(
                RULE_5_DIVIDEND_ADJUSTED_PEG.id, _PASS, pegy, _PEG_PASS, detail
            )
        if pegy <= _PEG_WATCH:
            return RuleOutcome(
                RULE_5_DIVIDEND_ADJUSTED_PEG.id, _WATCH, pegy, _PEG_WATCH, detail
            )
        return RuleOutcome(
            RULE_5_DIVIDEND_ADJUSTED_PEG.id, _FAIL, pegy, _PEG_WATCH, detail
        )

    # ------------------------------------------------------------------
    # verdict, score, confidence, flags
    # ------------------------------------------------------------------
    @staticmethod
    def _verdict(outcomes) -> tuple[Verdict, Optional[float], Confidence]:
        core_ids = {r.id for r in VERDICT_RULES}
        core = [o for o in outcomes if o.rule_id in core_ids]
        insufficient = [o for o in core if o.outcome == _INSUFFICIENT]
        if len(insufficient) > 2:
            return Verdict.INSUFFICIENT_DATA, None, Confidence.LOW
        passed = [o for o in core if o.outcome == _PASS]
        failed = [o for o in core if o.outcome == _FAIL]
        score = LynchGARPMethodology._score(outcomes)
        confidence = LynchGARPMethodology._confidence(outcomes)
        if failed:
            return Verdict.AVOID, score, confidence
        if len(passed) == 3:
            return Verdict.BUY, score, confidence
        if len(passed) == 2:
            return Verdict.WATCH, score, confidence
        if len(passed) == 1:
            return Verdict.HOLD, score, confidence
        return Verdict.AVOID, score, confidence

    @staticmethod
    def _score(outcomes) -> Optional[float]:
        evaluable = [o for o in outcomes if o.outcome != _INSUFFICIENT]
        if len(evaluable) < 2:
            return None
        passed = sum(1 for o in evaluable if o.outcome == _PASS)
        return round(passed / len(evaluable) * 100.0, 2)

    @staticmethod
    def _confidence(outcomes) -> Confidence:
        insufficient = sum(1 for o in outcomes if o.outcome == _INSUFFICIENT)
        if insufficient == 0:
            return Confidence.HIGH
        if insufficient <= 2:
            return Confidence.MEDIUM
        return Confidence.LOW

    @staticmethod
    def _red_flags(outcomes) -> list[str]:
        flags = []
        for o in outcomes:
            if o.outcome == _FAIL:
                flags.append(f"{_FLAG_BY_RULE[o.rule_id]}: {o.detail}")
        return flags

    @staticmethod
    def _reasons(outcomes, verdict) -> list[str]:
        parts = []
        for o in outcomes:
            mark = {
                _PASS: "PASS",
                _WATCH: "WATCH",
                _FAIL: "FAIL",
                _INSUFFICIENT: "N/A",
            }[o.outcome]
            parts.append(f"[{mark}] {o.detail}")
        parts.append(f"verdict: {verdict.value}")
        return parts

    @staticmethod
    def _metrics(outcomes, price: Optional[float], rows) -> dict[str, Any]:
        metrics: dict[str, Any] = {
            o.rule_id.replace("lynch_garp.", ""): o.value for o in outcomes
        }
        metrics["rule_outcomes"] = {o.rule_id: o.outcome for o in outcomes}
        metrics["current_price"] = price
        metrics["fiscal_years_analyzed"] = len(rows)
        return metrics
