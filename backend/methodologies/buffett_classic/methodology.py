"""``buffett_classic`` — wrap the existing deterministic Buffett filter.

This methodology does not re-implement anything: it calls the production
engine in ``backend/intelligence/buffett_engine.py`` (``buffett_filter``) with
metrics built by ``backend/intelligence/quality_metrics.py`` and maps the
engine's output onto the framework's :class:`MethodologyResult`. It is a
QUALITY screen: it rewards durable profitability, strong financials, cash
generation and stable earnings, without requiring the stock to be cheap.
"""

from __future__ import annotations

from typing import Any

from backend.intelligence.buffett_engine import buffett_filter
from backend.intelligence.moat_analysis import analyze_moat
from backend.intelligence.quality_metrics import compute_quality_metrics
from backend.methodologies.base import (
    Confidence,
    Methodology,
    MethodologyResult,
    Rule,
    SourceRef,
    Verdict,
)
from backend.methodologies.common.company_type import is_financial

# The engine (buffett_engine.py) defines per-pillar thresholds but no
# BUY/WATCH/HOLD/AVOID mapping, so the wrapper uses the framework's agreed
# numeric scale for wrapped score-based filters (docs/methodology_decisions.md).
SCORE_BUY = 75
SCORE_WATCH = 60
SCORE_HOLD = 40

_WEAK_PILLAR = 40.0

_SOURCE = SourceRef(
    book="backend/intelligence/buffett_engine.py",
    edition="internal",
    year=2026,
    page="buffett_filter",
    era="modern",
    us_caution="Not from a canonical book; implementation-defined",
)


def _verdict_for(score: float) -> Verdict:
    if score >= SCORE_BUY:
        return Verdict.BUY
    if score >= SCORE_WATCH:
        return Verdict.WATCH
    if score >= SCORE_HOLD:
        return Verdict.HOLD
    return Verdict.AVOID


class BuffettClassicMethodology(Methodology):
    """Buffett/Munger 4-pillar filter, wrapped from the existing engine."""

    name = "buffett_classic"
    version = "1.0.0"
    family = "QUALITY_COMPOUNDER"

    # -- Methodology -----------------------------------------------------
    def evaluate(
        self, ticker: str, fundamentals: Any, prices: Any
    ) -> MethodologyResult:
        rows = list(fundamentals or [])
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
                sources=[_SOURCE],
            )

        latest = rows[0]
        if is_financial(latest, getattr(latest, "sector", None)):
            return MethodologyResult(
                methodology=self.name,
                version=self.version,
                family=self.family,
                verdict=Verdict.INSUFFICIENT_DATA,
                score=None,
                metrics={
                    "financial_company": True,
                    "fiscal_years_analyzed": len(rows),
                },
                reasons=[
                    (
                        "buffett_classic does not apply to financial companies "
                        "(banks, insurers): the 4-pillar filter reads bank "
                        "leverage as weakness. See README for details."
                    ),
                    f"verdict: {Verdict.INSUFFICIENT_DATA.value}",
                ],
                red_flags=[],
                confidence=Confidence.HIGH,
                sources=[_SOURCE],
                passed_rules=[],
                failed_rules=[],
            )

        metrics = compute_quality_metrics(rows)
        filter_result = buffett_filter(metrics)
        score = float(filter_result["score"])
        pillars = filter_result.get("breakdown") or {}
        try:
            moat = analyze_moat(rows, metrics=metrics)
        except (AttributeError, KeyError, TypeError, ValueError):
            moat = None

        result_metrics: dict[str, Any] = dict(pillars)
        result_metrics["moat"] = moat

        reasons = [
            "composite Buffett score {:.1f} from 4 pillars "
            "(profitability {:.1f}, financial_strength {:.1f}, "
            "cash_generation {:.1f}, stability {:.1f})".format(
                score,
                pillars.get("profitability", 0.0),
                pillars.get("financial_strength", 0.0),
                pillars.get("cash_generation", 0.0),
                pillars.get("stability", 0.0),
            )
        ]
        reasons += [
            "{} pillar: {:.1f}/100".format(key.replace("_", " "), value)
            for key, value in sorted(pillars.items())
        ]
        red_flags = [
            "{} pillar weak ({:.1f}/100)".format(key.replace("_", " "), value)
            for key, value in pillars.items()
            if value < _WEAK_PILLAR
        ]

        return MethodologyResult(
            methodology=self.name,
            version=self.version,
            family=self.family,
            verdict=_verdict_for(score),
            score=score,
            metrics=result_metrics,
            reasons=reasons,
            red_flags=red_flags,
            confidence=Confidence.HIGH,
            sources=[_SOURCE],
        )

    def rules(self) -> list[Rule]:
        pillars = [
            (
                "profitability",
                "consistent high return on equity and invested capital",
            ),
            (
                "financial_strength",
                "conservative leverage with adequate interest coverage",
            ),
            (
                "cash_generation",
                "persistent positive free cash flow that grows",
            ),
            (
                "stability",
                "low earnings volatility with no deep drawdowns",
            ),
        ]
        return [
            Rule(
                id="buffett_classic." + key,
                name=key.replace("_", " "),
                description=description,
                kind="EXPLICIT",
                source=_SOURCE,
            )
            for key, description in pillars
        ]

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "family": self.family,
            "description": (
                "Buffett-style deterministic filter over normalized financials. "
                "Four pillars are scored 0-100 from explicit, published "
                "thresholds and combined with fixed weights. Every pillar "
                "answer can be traced back to a single rule, so the filter "
                "stays transparent and explainable."
            ),
            "source": {
                "book": _SOURCE.book,
                "edition": _SOURCE.edition,
                "year": _SOURCE.year,
                "page": _SOURCE.page,
            },
            "known_limitations": [
                (
                    "The wrapped engine is a quality screen, not a valuation: "
                    "it barely looks at the price paid, so a high score here "
                    "can coexist with a 'too expensive' verdict from the "
                    "value methodologies. That is intended."
                ),
                (
                    "Verdict thresholds (75/60/40) are framework conventions "
                    "because buffett_engine.py defines no verdict mapping."
                ),
                (
                    "Metrics are computed from as-reported SEC fundamentals; "
                    "stock-split adjustments only affect per-share metrics."
                ),
            ],
        }
