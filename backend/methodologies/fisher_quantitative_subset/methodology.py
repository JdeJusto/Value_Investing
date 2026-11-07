"""``fisher_quantitative_subset`` — 4 quantifiable points of Fisher's 15.

Decision 1 in docs/methodology_decisions.md: Fisher is only implemented as a
*quantitative subset* (points 3, 5, 10 and 13). The other 11 points rest on
the scuttlebutt method (interviews with competitors, suppliers, customers and
ex-employees) which this system does not have. Building a 15-point checklist
without that data would be a fake Fisher. This module is therefore named
``fisher_quantitative_subset`` — never ``fisher``.
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
from backend.methodologies.common.company_type import (
    financial_na_reason,
    is_financial,
)
from backend.methodologies.fisher_quantitative_subset.rules import (
    RULES,
    RULES_SOURCES,
)

# Point 3 — R&D intensity relative to size, with a sector-aware bar. R&D
# intensity is a *sector* property — 2% of revenue is generous for a consumer
# staples firm but a warning for software — so one bar for everyone would
# over-pass capital-goods firms and over-fail innovation-led ones. Tiers key
# on the sector label (Yahoo/GICS vocabulary) matched case-insensitively as
# substrings; an unrecognized or missing sector keeps the calibrated 2026-09
# large-cap bar (PASS 8%, FAIL < 2%). The subset has no scuttlebutt to soften
# a quantitative near-miss, so the top tier stays strict; the low tier's
# 0.5% FAIL floor is deliberately low so a staples flyer with a token spend
# reads WATCH, not AVOID.
_RND_THRESHOLDS: tuple[tuple[tuple[str, ...], tuple[float, float]], ...] = (
    # Innovation-led sectors: R&D is the moat, demand ~8% of revenue.
    (("technology", "healthcare", "communication services"), (0.08, 0.04)),
    # Capital-goods sectors: steady, moderate development spending.
    (
        (
            "industrials",
            "consumer cyclical",
            "consumer discretionary",
            "materials",
            "basic materials",
        ),
        (0.04, 0.02),
    ),
    # Low-R&D sectors: a 2% spend already earns PASS; below 0.5% is "no R&D".
    (
        (
            "consumer defensive",
            "consumer staples",
            "staples",
            "utilities",
            "utility",
            "energy",
            "real estate",
            "financial",
        ),
        (0.02, 0.005),
    ),
)
_RND_THRESHOLDS_UNKNOWN: tuple[float, float] = (0.08, 0.02)

#: Rule status for a metric that does not exist in the company's business
#: model (R&D in an E&P, gross margin in a REIT). Distinct from
#: ``INSUFFICIENT_DATA``: the data is not missing, the line item is not part of
#: how this company operates. N/A rules are excluded from the verdict
#: denominator and from ``score``.
_NOT_APPLICABLE = "NOT_APPLICABLE"


def _rnd_thresholds_for(sector: str | None) -> tuple[float, float]:
    """(PASS, WATCH) R&D bars for a sector label, first match wins.

    The tier whose keyword is a case-insensitive substring of the label
    (Yahoo/GICS vocabulary) applies. An unknown or missing sector keeps the
    calibrated large-cap bar, so missing metadata never silently relaxes the
    screen; ``is_financial`` returns INSUFFICIENT_DATA before the R&D rule
    runs, so the financial keyword here is purely documentary.
    """
    if sector:
        label = sector.lower()
        for keywords, thresholds in _RND_THRESHOLDS:
            if any(keyword in label for keyword in keywords):
                return thresholds
    return _RND_THRESHOLDS_UNKNOWN


def _pct(ratio: float) -> str:
    """Compact percent text: ``0.08 -> '8%'``, ``0.005 -> '0.5%'``."""
    text = f"{ratio:.1%}"
    return text[:-3] + "%" if text.endswith(".0%") else text


def _rnd_not_applicable(sector: str | None) -> bool:
    """True when the sector sits in the low-R&D tier (no R&D line expected).

    A missing R&D tag in an E&P, a utility or a consumer-staples filer is a
    business-model fact, not a data gap. Innovation-led, capital-goods and
    unknown sectors keep ``INSUFFICIENT_DATA`` so a genuinely missing line is
    not silently excused.
    """
    return bool(sector) and _rnd_thresholds_for(sector) == _RND_THRESHOLDS[2][1]


#: Sectors whose business model does not expose a gross-margin line (REITs
#: and other real-estate filers report rental income and property costs).
_GROSS_MARGIN_NA_KEYWORDS = ("real estate", "reit", "financial")


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

_DESCRIPTION = (
    "Quantitative subset of Fisher's 15 points: R&D intensity (3), "
    "worthwhile margin (5), cost control (10) and financing without "
    "dilution (13). The 11 scuttlebutt points are out of scope "
    "(docs/methodology_decisions.md, decision 1)."
)


class FisherQuantitativeSubsetMethodology(Methodology):
    """Philip Fisher's quantifiable points (3, 5, 10, 13) as a screen."""

    name = "fisher_quantitative_subset"
    version = "1.0.0"
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
                sources=RULES_SOURCES,
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
                sources=RULES_SOURCES,
                passed_rules=[],
                failed_rules=[],
            )

        status = {
            "rule_1_rnd_intensity": self._rule_1(rows),
            "rule_2_profit_margin_quality": self._rule_2(rows),
            "rule_3_cost_control_stability": self._rule_3(rows),
            "rule_4_share_dilution": self._rule_4(rows),
        }

        passed = sum(1 for s, _ in status.values() if s == "PASS")
        insufficient = sum(1 for s, _ in status.values() if s == "INSUFFICIENT_DATA")
        not_applicable = sum(1 for s, _ in status.values() if s == _NOT_APPLICABLE)
        applicable = len(status) - not_applicable
        scored = applicable - insufficient

        reasons = [
            f"{status_word} {_RULE_IDS[rid]}: {detail}"
            for rid, (status_word, detail) in status.items()
        ]
        reasons.append(
            f"{passed} of {applicable} applicable rules passed "
            f"({not_applicable} not applicable, {insufficient} insufficient, "
            f"{scored} scored; score based on all applicable rules)"
        )

        verdict = self._verdict(status)
        score = (
            (passed / applicable * 100.0)
            if applicable
            and verdict
            not in (
                Verdict.INSUFFICIENT_DATA,
                Verdict.NOT_APPLICABLE,
            )
            else None
        )

        return MethodologyResult(
            methodology=self.name,
            version=self.version,
            family=self.family,
            verdict=verdict,
            score=score,
            metrics=self._metrics(status, rows),
            reasons=reasons,
            red_flags=self._red_flags(status, rows),
            confidence=self._confidence(insufficient),
            sources=RULES_SOURCES,
            failed_rules=[
                _RULE_IDS[rid] for rid, (s, _) in status.items() if s == "FAIL"
            ],
            passed_rules=[
                _RULE_IDS[rid] for rid, (s, _) in status.items() if s == "PASS"
            ],
        )

    def rules(self) -> list:
        return list(RULES)

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "family": self.family,
            "description": _DESCRIPTION,
            "source": {
                "book": "Common Stocks and Uncommon Profits",
                "edition": "Wiley Investment Classics (reprint of 1996 revised ed.)",
                "year": 1958,
                "pages": {
                    "point3": "54-55",
                    "point5": "63-64",
                    "point10": "69",
                    "point13": "75",
                },
            },
            "known_limitations": [
                "Subset only: the 11 scuttlebutt points are not implemented.",
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
                    "half of the four points applicable returns N/A."
                ),
                "Cost control is proxied by gross-margin stability, not an audit.",
                "Dilution measured on split-restated share counts (XBRL ratio facts).",
                "Price is never consulted — a quality screen, not a valuation.",
            ],
        }

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
    # Verdict / score / confidence / flags / metrics
    # ------------------------------------------------------------------
    def _verdict(self, status) -> Verdict:
        """Aggregate on applicable rules (N/A excluded, missing data counted).

        - fewer than half of the four points applicable -> N/A;
        - nothing scorable left -> INSUFFICIENT_DATA;
        - any FAIL vetoes the verdict (Fisher's points are non-negotiable);
        - BUY only when every applicable rule passed and none is missing;
        - fewer than two scored rules -> INSUFFICIENT_DATA (one rule is not
          enough evidence);
        - otherwise 75% of applicable PASS -> WATCH, 50% -> HOLD, else AVOID.
        """
        rules = [verdict for verdict, _detail in status.values()]
        applicable = [verdict for verdict in rules if verdict != _NOT_APPLICABLE]
        if len(applicable) / len(rules) < 0.5:
            return Verdict.NOT_APPLICABLE
        scored = [
            verdict
            for verdict in applicable
            if verdict not in (_NOT_APPLICABLE, "INSUFFICIENT_DATA")
        ]
        if not scored:
            return Verdict.INSUFFICIENT_DATA
        passed = scored.count("PASS")
        failed = scored.count("FAIL")
        if failed:
            return Verdict.AVOID
        if passed == len(applicable) and len(scored) == len(applicable):
            return Verdict.BUY
        # A verdict from a single rule is not a verdict: too little evidence.
        if len(scored) < 2:
            return Verdict.INSUFFICIENT_DATA
        if passed >= 0.75 * len(applicable):
            return Verdict.WATCH
        if passed >= 0.5 * len(applicable):
            return Verdict.HOLD
        return Verdict.AVOID

    def _confidence(self, insufficient) -> Confidence:
        if insufficient == 0:
            return Confidence.HIGH
        if insufficient == 1:
            return Confidence.MEDIUM
        return Confidence.LOW

    def _red_flags(self, status, rows) -> list:
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
        return flags

    def _metrics(self, status, rows) -> dict:
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
        return {
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


DISCLAIMER = _SUBSET_DISCLAIMER

__all__ = ["DISCLAIMER", "FisherQuantitativeSubsetMethodology"]
