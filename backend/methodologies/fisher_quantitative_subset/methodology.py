"""``fisher_quantitative_subset`` — the quantifiable edge of Fisher's 15 points.

Decision 1 in docs/methodology_decisions.md: Fisher is only implemented as a
*quantitative subset*. The original four points (3, 5, 10, 13) are now
aggregated with thirteen deep checks in
:mod:`backend.methodologies.fisher_quantitative_subset.deep_checks` through the
shared weighted framework:

    weighted_score = sum(passed weight) / sum(evaluable weight)

Thresholds: BUY >= 0.85, WATCH >= 0.70, HOLD >= 0.50, else AVOID. More than
30% of the weighted rules missing data returns INSUFFICIENT_DATA. The legacy
rule statuses are converted conservatively: PASS -> passed, WATCH and FAIL ->
not passed, INSUFFICIENT_DATA -> not evaluable, NOT_APPLICABLE -> excluded.

The other eleven points still rest on the scuttlebutt method (interviews with
competitors, suppliers, customers and ex-employees) which this system does not
have. Building a 15-point checklist without that data would be a fake Fisher,
so this module stays named ``fisher_quantitative_subset`` — never ``fisher``.
"""

from __future__ import annotations

import statistics
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
from backend.methodologies.fisher_quantitative_subset.deep_checks import (
    CATEGORIES,
    run_checks,
)
from backend.methodologies.fisher_quantitative_subset.deep_checks import (
    CHECKS as DEEP_CHECKS,
)
from backend.methodologies.fisher_quantitative_subset.deep_checks import (
    rnd_not_applicable as _rnd_not_applicable,
)
from backend.methodologies.fisher_quantitative_subset.deep_checks import (
    rnd_thresholds_for as _rnd_thresholds_for,
)
from backend.methodologies.fisher_quantitative_subset.rules import (
    RULES,
    RULES_SOURCES,
)

# Point 5 — worthwhile profit margin.
_MARGIN_NET_PASS = 0.10
_MARGIN_OP_PASS = 0.15
_MARGIN_NET_FAIL = 0.05

# Point 10 — cost-control stability over 5 years.
_MARGIN_YEARS = 5
_GM_SD_PASS = 0.03
_GM_SD_WATCH = 0.05

# Point 13 — dilution over 10 years.
_DILUTION_YEARS = 10
_DILUTION_WATCH = 0.10

_SUBSET_DISCLAIMER = (
    "This is a quantitative subset of Fisher's 15 points, not Fisher. "
    "The 11 remaining points require scuttlebutt."
)

_RULE_IDS = {
    "rule_1_rnd_intensity": "fisher_quantitative_subset.rule_1_rnd_intensity",
    "rule_2_profit_margin_quality": (
        "fisher_quantitative_subset.rule_2_profit_margin_quality"
    ),
    "rule_3_cost_control_stability": (
        "fisher_quantitative_subset.rule_3_cost_control_stability"
    ),
    "rule_4_share_dilution": "fisher_quantitative_subset.rule_4_share_dilution",
}

#: Name, category and weight of the four original points. Point 5 (margins)
#: and point 13 (no dilutive financing) are critical for Fisher; R&D intensity
#: and cost control are normal.
_LEGACY_META: dict[str, tuple[str, str, int]] = {
    "rule_1_rnd_intensity": (
        "R&D intensity relative to size (point 3)",
        "growth_potential",
        1,
    ),
    "rule_2_profit_margin_quality": (
        "Worthwhile profit margin (point 5)",
        "profitability",
        2,
    ),
    "rule_3_cost_control_stability": (
        "Cost analysis and accounting controls (point 10)",
        "cost_efficiency",
        1,
    ),
    "rule_4_share_dilution": (
        "Growth without equity financing (point 13)",
        "capital_discipline",
        2,
    ),
}

#: Rule status for a metric that does not exist in the company's business
#: model (R&D in an E&P, gross margin in a REIT). Distinct from
#: ``INSUFFICIENT_DATA``: the data is not missing, the line item is not part of
#: how this company operates. N/A rules are excluded from the verdict
#: denominator and from ``score``.
_NOT_APPLICABLE = "NOT_APPLICABLE"

_STATUS_PASSED: dict[str, bool | None] = {
    "PASS": True,
    # WATCH is treated conservatively as not passed: the quantitative subset
    # has no scuttlebutt to justify a near-miss.
    "WATCH": False,
    "FAIL": False,
    "INSUFFICIENT_DATA": None,
    _NOT_APPLICABLE: None,
}

#: Sectors whose business model does not expose a gross-margin line (REITs
#: and other real-estate filers report rental income and property costs).
_GROSS_MARGIN_NA_KEYWORDS = ("real estate", "reit", "financial")

_DESCRIPTION = (
    "Quantitative subset of Fisher's 15 points: R&D intensity (3), "
    "worthwhile margin (5), cost control (10) and financing without "
    "dilution (13), expanded with growth, profitability, SG&A and "
    "capital-discipline checks. The 11 scuttlebutt points are out of scope "
    "(docs/methodology_decisions.md, decision 1)."
)


def _pct(ratio: float) -> str:
    """Compact percent text: ``0.08 -> '8%'``, ``0.005 -> '0.5%'``."""
    text = f"{ratio:.1%}"
    return text[:-3] + "%" if text.endswith(".0%") else text


class FisherQuantitativeSubsetMethodology(Methodology):
    """Philip Fisher's quantifiable points as a weighted screen."""

    name = "fisher_quantitative_subset"
    version = "2.0.0"
    family = "QUALITY_COMPOUNDER"

    # ------------------------------------------------------------------
    # Methodology interface
    # ------------------------------------------------------------------
    def evaluate(
        self, ticker: str, fundamentals: Any, prices: Any
    ) -> MethodologyResult:
        rows = sorted(
            (r for r in (fundamentals or []) if r is not None and r.fiscal_year),
            key=lambda r: r.fiscal_year,
            reverse=True,
        )
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
                sources=self._sources(),
            )

        latest = rows[0]
        if is_financial(latest, getattr(latest, "sector", None)):
            return MethodologyResult(
                methodology=self.name,
                version=self.version,
                family=self.family,
                verdict=Verdict.NOT_APPLICABLE,
                score=None,
                metrics={"financial_company": True},
                reasons=[
                    (
                        "Fisher's criteria assume a product company with "
                        "inventory, gross margin and R&D; financials (banks, "
                        "insurers) do not fit."
                    ),
                    financial_na_reason(
                        latest, rows, getattr(latest, "sector", None), ticker
                    ),
                    f"verdict: {Verdict.NOT_APPLICABLE.value}",
                ],
                red_flags=[],
                confidence=Confidence.HIGH,
                sources=self._sources(),
                passed_rules=[],
                failed_rules=[],
            )

        status = {
            "rule_1_rnd_intensity": self._rule_1(rows),
            "rule_2_profit_margin_quality": self._rule_2(rows),
            "rule_3_cost_control_stability": self._rule_3(rows),
            "rule_4_share_dilution": self._rule_4(rows),
        }

        # Preserve the original company-type guard: fewer than half of the four
        # Fisher points applicable means the screen does not apply.
        applicable = sum(1 for word, _ in status.values() if word != _NOT_APPLICABLE)
        if applicable / len(status) < 0.5:
            return MethodologyResult(
                methodology=self.name,
                version=self.version,
                family=self.family,
                verdict=Verdict.NOT_APPLICABLE,
                score=None,
                metrics=self._metrics(status, rows),
                reasons=[
                    (
                        "Fewer than half of Fisher's four quantifiable points "
                        "apply to this business model."
                    ),
                    f"verdict: {Verdict.NOT_APPLICABLE.value}",
                ],
                red_flags=[],
                confidence=Confidence.HIGH,
                sources=self._sources(),
                passed_rules=[],
                failed_rules=[],
            )

        legacy = self._legacy_results(status)
        deep = run_checks(rows, None, getattr(latest, "sector", None))
        results = legacy + deep
        verdict, score, confidence = weighted_verdict(results)

        reasons = [
            f"{status_word} {_RULE_IDS[rid]}: {detail}"
            for rid, (status_word, detail) in status.items()
        ]
        for item in deep:
            mark = (
                "PASS"
                if item.passed is True
                else "FAIL"
                if item.passed is False
                else "N/A"
            )
            reasons.append(f"{mark} {item.rule_id}: {item.detail}")
        passed = sum(1 for s, _ in status.values() if s == "PASS")
        insufficient = sum(1 for s, _ in status.values() if s == "INSUFFICIENT_DATA")
        not_applicable = sum(1 for s, _ in status.values() if s == _NOT_APPLICABLE)
        scored = applicable - insufficient
        reasons.append(
            f"{passed} of {applicable} applicable rules passed "
            f"({not_applicable} not applicable, {insufficient} insufficient, "
            f"{scored} scored; score based on all applicable rules)"
        )

        return MethodologyResult(
            methodology=self.name,
            version=self.version,
            family=self.family,
            verdict=verdict,
            score=score,
            metrics=self._metrics(status, rows, deep),
            reasons=reasons,
            red_flags=self._red_flags(status, rows, deep),
            confidence=confidence,
            sources=self._sources(),
            failed_rules=[
                _RULE_IDS[rid] for rid, (s, _) in status.items() if s == "FAIL"
            ]
            + [item.rule_id for item in deep if item.passed is False],
            passed_rules=[
                _RULE_IDS[rid] for rid, (s, _) in status.items() if s == "PASS"
            ]
            + [item.rule_id for item in deep if item.passed is True],
        )

    def rules(self) -> list[Rule]:
        return list(RULES) + [check.rule() for check in DEEP_CHECKS]

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "family": self.family,
            "description": _DESCRIPTION,
            "categories": list(CATEGORIES),
            "source": {
                "book": "Common Stocks and Uncommon Profits",
                "edition": "Wiley Investment Classics (reprint of 1996 revised ed.)",
                "year": 1958,
                "pages": {
                    "point1": "47-48",
                    "point3": "54-55",
                    "point5": "63-64",
                    "point6": "63",
                    "point10": "69",
                    "point13": "75",
                },
            },
            "thresholds": {
                "buy": 0.85,
                "watch": 0.70,
                "hold": 0.50,
                "max_missing_weight": 0.30,
            },
            "known_limitations": [
                "Subset only: the 11 scuttlebutt points are not implemented.",
                (
                    "WATCH is treated conservatively as not passed; the "
                    "quantitative subset has no scuttlebutt to justify a "
                    "near-miss."
                ),
                (
                    "R&D PASS/WATCH is sector-aware (Yahoo/GICS tier: "
                    "innovation-led 8/4%, industrials 4/2%, low-R&D 2/0.5%) "
                    "with an 8/2% fallback when the sector is unknown; FAIL "
                    "is any spend below the tier's floor."
                ),
                (
                    "R&D falls back to the ExcludingAcquiredInProcessCost tag "
                    "when a filer's plain tag only carries a residual (JNJ); "
                    "filers reporting neither read INSUFFICIENT_DATA."
                ),
                (
                    "A rule whose line item does not exist in the business "
                    "model (R&D in low-R&D sectors, gross margin in REITs) is "
                    "NOT_APPLICABLE and excluded from the verdict; fewer than "
                    "half of the four original points applicable returns N/A."
                ),
                "Cost control is proxied by gross-margin stability, not an audit.",
                "Dilution measured on split-restated share counts (XBRL ratio facts).",
                "Price is never consulted — a quality screen, not a valuation.",
                (
                    "Deferred qualitative points: sales organization (4), "
                    "labor relations (7), executive relations (8), management "
                    "depth (9), industry-specific factors (11), long-range "
                    "outlook (12), candor (14) and integrity (15). They need "
                    "scuttlebutt or governance data that FDB does not carry."
                ),
            ],
        }

    # ------------------------------------------------------------------
    # Weighted aggregation
    # ------------------------------------------------------------------
    def _legacy_results(self, status) -> list[WeightedResult]:
        converted: list[WeightedResult] = []
        for key, (status_word, detail) in status.items():
            name, category, weight = _LEGACY_META[key]
            passed = _STATUS_PASSED[status_word]
            converted.append(
                WeightedResult(
                    rule_id=_RULE_IDS[key],
                    name=name,
                    category=category,
                    weight=0 if status_word == _NOT_APPLICABLE else weight,
                    passed=passed,
                    detail=detail,
                )
            )
        return converted

    @staticmethod
    def _sources():
        return list(RULES_SOURCES) + [check.source for check in DEEP_CHECKS]

    # ------------------------------------------------------------------
    # Rules (return (status, detail))
    # ------------------------------------------------------------------
    def _rule_1(self, rows) -> tuple:
        latest = rows[0]
        revenue = latest.revenue
        rnd = latest.research_development
        label = latest.sector or "an unknown sector"
        if not revenue:
            return (
                "INSUFFICIENT_DATA",
                "revenue is missing for the latest fiscal year",
            )
        if rnd is None:
            if _rnd_not_applicable(latest.sector):
                return (
                    _NOT_APPLICABLE,
                    f"R&D is not a line item for {label} (low-R&D sector)",
                )
            return (
                "INSUFFICIENT_DATA",
                "R&D is not reported for the latest fiscal year",
            )
        ratio = rnd / revenue
        rnd_pass, rnd_watch = _rnd_thresholds_for(latest.sector)
        if ratio >= rnd_pass:
            return (
                "PASS",
                f"R&D {ratio:.1%} of revenue (>= {_pct(rnd_pass)} for {label})",
            )
        if ratio >= rnd_watch:
            return (
                "WATCH",
                f"R&D {ratio:.1%} of revenue (>= {_pct(rnd_watch)} for {label})",
            )
        return (
            "FAIL",
            f"R&D {ratio:.1%} of revenue (< {_pct(rnd_watch)} for {label})",
        )

    def _rule_2(self, rows) -> tuple:
        latest = rows[0]
        revenue = latest.revenue
        if not revenue or latest.net_income is None or latest.operating_income is None:
            return (
                "INSUFFICIENT_DATA",
                "net income or operating income missing for the latest year",
            )
        net = latest.net_income / revenue
        op = latest.operating_income / revenue
        if net < _MARGIN_NET_FAIL:
            return (
                "FAIL",
                f"net margin {net:.1%} (< {_MARGIN_NET_FAIL:.0%})",
            )
        if net >= _MARGIN_NET_PASS and op >= _MARGIN_OP_PASS:
            return (
                "PASS",
                f"net margin {net:.1%} >= 10% and operating margin {op:.1%} >= 15%",
            )
        if (net >= _MARGIN_NET_PASS) != (op >= _MARGIN_OP_PASS):
            return (
                "WATCH",
                f"one margin above target, the other below (net {net:.1%}, op {op:.1%})",
            )
        return (
            "FAIL",
            f"both margins below targets (net {net:.1%}, op {op:.1%})",
        )

    def _rule_3(self, rows) -> tuple:
        values = []
        for row in rows:
            if row.gross_profit is not None and row.revenue:
                values.append(row.gross_profit / row.revenue)
            if len(values) >= _MARGIN_YEARS:
                break
        if len(values) < _MARGIN_YEARS:
            if not values:
                label = (rows[0].sector or "").lower()
                if any(keyword in label for keyword in _GROSS_MARGIN_NA_KEYWORDS):
                    return (
                        _NOT_APPLICABLE,
                        "gross margin is not a line item for this business model",
                    )
            return (
                "INSUFFICIENT_DATA",
                f"only {len(values)} years of gross margin data (need {_MARGIN_YEARS})",
            )
        sd = statistics.stdev(values)
        if sd < _GM_SD_PASS:
            return (
                "PASS",
                f"gross margin stdev {sd:.3f} over 5 years (< {_GM_SD_PASS:.2f})",
            )
        if sd < _GM_SD_WATCH:
            return (
                "WATCH",
                f"gross margin stdev {sd:.3f} over 5 years (< {_GM_SD_WATCH:.2f})",
            )
        return (
            "FAIL",
            f"gross margin stdev {sd:.3f} over 5 years (>= {_GM_SD_WATCH:.2f})",
        )

    def _rule_4(self, rows) -> tuple:
        latest = rows[0]
        current = latest.shares_outstanding
        if current is None:
            return ("INSUFFICIENT_DATA", "current shares outstanding missing")
        target = latest.fiscal_year - _DILUTION_YEARS
        past_row = next(
            (
                r
                for r in rows
                if r.fiscal_year == target and r.shares_outstanding is not None
            ),
            None,
        )
        if past_row is None or not past_row.shares_outstanding:
            return (
                "INSUFFICIENT_DATA",
                f"no shares outstanding {_DILUTION_YEARS} years ago (fiscal {target})",
            )
        # Restate the 10y-ago count on today's post-split basis: a 4:1 split
        # after that year means each as-reported share is 4 shares now. The
        # factor comes from the XBRL split-ratio facts on the row (data, not
        # prices), so the methodology stays hermetic. 1.0 when unknown.
        past_raw = float(past_row.shares_outstanding)
        factor = past_row.split_adjustment_factor
        factor = 1.0 if not factor or factor <= 0 else float(factor)
        past = past_raw * factor
        if current <= past:
            note = ", split-adjusted" if factor != 1.0 else ""
            return (
                "PASS",
                f"shares {int(past)} -> {current} (no dilution{note})",
            )
        change = (float(current) - past) / past
        if change <= _DILUTION_WATCH:
            return (
                "WATCH",
                f"shares +{change:.1%} over {_DILUTION_YEARS} years (<= {_DILUTION_WATCH:.0%})",
            )
        return (
            "FAIL",
            f"shares +{change:.1%} over {_DILUTION_YEARS} years (> {_DILUTION_WATCH:.0%})",
        )

    # ------------------------------------------------------------------
    # Flags / metrics
    # ------------------------------------------------------------------
    def _red_flags(self, status, rows, deep) -> list:
        flags = []
        if status["rule_1_rnd_intensity"][0] == "FAIL":
            _, rnd_watch = _rnd_thresholds_for(rows[0].sector)
            flags.append(f"R&D below {_pct(rnd_watch)} of revenue without explanation")
        if status["rule_2_profit_margin_quality"][0] == "FAIL":
            flags.append("Net margin below 5%")
        if status["rule_3_cost_control_stability"][0] == "FAIL":
            flags.append("Gross margin standard deviation above 5% over 5 years")
        if status["rule_4_share_dilution"][0] == "FAIL":
            flags.append("Share count increased more than 10% over 10 years")
        flags.extend(
            f"{item.rule_id}: {item.detail}" for item in deep if item.passed is False
        )
        return flags

    def _metrics(self, status, rows, deep=None) -> dict:
        latest = rows[0]
        revenue = latest.revenue
        net_margin = (
            latest.net_income / revenue
            if revenue and latest.net_income is not None
            else None
        )
        op_margin = (
            latest.operating_income / revenue
            if revenue and latest.operating_income is not None
            else None
        )
        rnd_ratio = (
            latest.research_development / revenue
            if revenue and latest.research_development is not None
            else None
        )
        rnd_thresholds = _rnd_thresholds_for(latest.sector)
        gm_values = [
            row.gross_profit / row.revenue
            for row in rows
            if row.gross_profit is not None and row.revenue
        ][:_MARGIN_YEARS]
        gm_sd = statistics.stdev(gm_values) if len(gm_values) >= 5 else None
        current = latest.shares_outstanding
        target = (latest.fiscal_year or 0) - _DILUTION_YEARS
        past_row = next(
            (
                r
                for r in rows
                if r.fiscal_year == target and r.shares_outstanding is not None
            ),
            None,
        )
        share_change = None
        if current is not None and past_row is not None and past_row.shares_outstanding:
            factor = past_row.split_adjustment_factor
            factor = 1.0 if not factor or factor <= 0 else float(factor)
            past_adjusted = float(past_row.shares_outstanding) * factor
            share_change = (float(current) - past_adjusted) / past_adjusted
        metrics = {
            "rnd_ratio": rnd_ratio,
            "rnd_thresholds": {
                "pass": rnd_thresholds[0],
                "watch": rnd_thresholds[1],
            },
            "net_margin": net_margin,
            "operating_margin": op_margin,
            "gross_margin_sd_5y": gm_sd,
            "share_change_10y": share_change,
            "rules_passed": sum(1 for s, _ in status.values() if s == "PASS"),
            "rules_not_applicable": sum(
                1 for s, _ in status.values() if s == _NOT_APPLICABLE
            ),
            "rules_insufficient": sum(
                1 for s, _ in status.values() if s == "INSUFFICIENT_DATA"
            ),
            "rules_evaluable": sum(
                1
                for s, _ in status.values()
                if s not in (_NOT_APPLICABLE, "INSUFFICIENT_DATA")
            ),
        }
        for item in deep or []:
            key = item.rule_id.replace("fisher_quantitative_subset.deep_", "deep_")
            metrics[key] = item.value
        return metrics


DISCLAIMER = _SUBSET_DISCLAIMER

__all__ = ["DISCLAIMER", "FisherQuantitativeSubsetMethodology"]
