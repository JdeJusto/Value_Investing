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
from backend.methodologies.fisher_quantitative_subset.rules import (
    RULES,
    RULES_SOURCES,
)

# Point 3 — R&D intensity relative to size (single threshold; no sector info
# is available, so the tech/pharma-specific bar is used for everyone).
# Calibrated 2026-09: PASS raised to 8%. The subset has no scuttlebutt to
# soften a quantitative near-miss, so the BUY gate must sit at the top of the
# large-cap range. FAIL stays at 2% ("no meaningful R&D") so consumer staples
# with a modest spend read WATCH, not AVOID.
_RND_PASS = 0.08
_RND_WATCH = 0.02
_RND_FAIL = 0.02

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

        status = {
            "rule_1_rnd_intensity": self._rule_1(rows),
            "rule_2_profit_margin_quality": self._rule_2(rows),
            "rule_3_cost_control_stability": self._rule_3(rows),
            "rule_4_share_dilution": self._rule_4(rows),
        }

        passed = sum(1 for s, _ in status.values() if s == "PASS")
        failed = sum(1 for s, _ in status.values() if s == "FAIL")
        insufficient = sum(1 for s, _ in status.values() if s == "INSUFFICIENT_DATA")
        evaluable = 4 - insufficient

        reasons = [
            f"{status_word} {_RULE_IDS[rid]}: {detail}"
            for rid, (status_word, detail) in status.items()
        ]
        reasons.append(
            f"{passed} of 4 rules passed ({evaluable} evaluable, "
            f"{insufficient} without data; score based on all 4)"
        )

        verdict = self._verdict(status, passed, failed, insufficient)
        score = (
            (passed / 4 * 100.0) if verdict is not Verdict.INSUFFICIENT_DATA else None
        )

        return MethodologyResult(
            methodology=self.name,
            version=self.version,
            family=self.family,
            verdict=verdict,
            score=score,
            metrics=self._metrics(status, rows),
            reasons=reasons,
            red_flags=self._red_flags(status),
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
                    "Single 8% R&D PASS threshold applied to every sector (no "
                    "industry data); FAIL stays at 2%."
                ),
                (
                    "R&D falls back to the ExcludingAcquiredInProcessCost tag "
                    "when a filer's plain tag only carries a residual (JNJ); "
                    "filers reporting neither read INSUFFICIENT_DATA."
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
        if not revenue or rnd is None:
            return (
                "INSUFFICIENT_DATA",
                "R&D is not reported for the latest fiscal year",
            )
        ratio = rnd / revenue
        if ratio >= _RND_PASS:
            return (
                "PASS",
                f"R&D {ratio:.1%} of revenue (>= {_RND_PASS:.0%})",
            )
        if ratio >= _RND_WATCH:
            return (
                "WATCH",
                f"R&D {ratio:.1%} of revenue (>= {_RND_WATCH:.0%})",
            )
        return ("FAIL", f"R&D {ratio:.1%} of revenue (< {_RND_FAIL:.0%})")

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
    def _verdict(self, status, passed, failed, insufficient) -> Verdict:
        if insufficient >= 3:
            return Verdict.INSUFFICIENT_DATA
        if failed > 0:
            return Verdict.AVOID
        if passed == 4:
            return Verdict.BUY
        if passed >= 3:
            return Verdict.WATCH
        if passed >= 2:
            return Verdict.HOLD
        return Verdict.AVOID

    def _confidence(self, insufficient) -> Confidence:
        if insufficient == 0:
            return Confidence.HIGH
        if insufficient == 1:
            return Confidence.MEDIUM
        return Confidence.LOW

    def _red_flags(self, status) -> list:
        flags = []
        if status["rule_1_rnd_intensity"][0] == "FAIL":
            flags.append(f"R&D below {_RND_FAIL:.0%} of revenue without explanation")
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
            "net_margin": net_margin,
            "operating_margin": op_margin,
            "gross_margin_sd_5y": gm_sd,
            "share_change_10y": share_change,
            "rules_passed": sum(1 for s, _ in status.values() if s == "PASS"),
            "rules_evaluable": 4
            - sum(1 for s, _ in status.values() if s == "INSUFFICIENT_DATA"),
        }


DISCLAIMER = _SUBSET_DISCLAIMER

__all__ = ["DISCLAIMER", "FisherQuantitativeSubsetMethodology"]
