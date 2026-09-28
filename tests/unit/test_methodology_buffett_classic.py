"""Tests for the buffett_classic wrapper methodology.

The wrapper must delegate to the existing engine (not re-implement it) and map
its output onto the framework's MethodologyResult.
"""

from __future__ import annotations

from backend.intelligence import buffett_engine
from backend.methodologies.base import Confidence, Verdict
from backend.methodologies.buffett_classic import BuffettClassicMethodology
from backend.methodologies.buffett_classic import methodology as wrapper_module


class _Prices:
    def get_current_price(self, ticker):
        return 100.0


def _metric_dict():
    """Minimal metric dict that buffett_filter consumes."""
    return {
        "roe_mean": 0.2,
        "roic_mean": 0.15,
        "gross_margin_cv": 0.05,
        "debt_to_equity": 0.4,
        "interest_coverage": 8.0,
        "retained_earnings_positive": True,
        "positive_fcf_ratio": 1.0,
        "fcf_growth": 0.1,
        "earnings_cv": 0.1,
        "max_yoy_decline": -0.05,
    }


def _patch(monkeypatch, score, breakdown=None):
    def _filter(metrics):
        # The wrapper must hand the real metric dict to the engine.
        assert metrics["roe_mean"] == 0.2
        return {
            "score": score,
            "breakdown": breakdown
            or {
                "profitability": score,
                "financial_strength": score,
                "cash_generation": score,
                "stability": score,
            },
        }

    monkeypatch.setattr(
        wrapper_module, "compute_quality_metrics", lambda rows: _metric_dict()
    )
    monkeypatch.setattr(wrapper_module, "buffett_filter", _filter)
    monkeypatch.setattr(
        wrapper_module, "analyze_moat", lambda rows, metrics=None: {"moat": "narrow"}
    )


def test_wrapper_delegates_to_existing_engine(monkeypatch):
    # Same function object as the production engine: not a re-implementation.
    assert wrapper_module.buffett_filter is buffett_engine.buffett_filter
    _patch(monkeypatch, 88.0)
    result = BuffettClassicMethodology().evaluate("TEST", ["row"], _Prices())
    assert result.score == 88.0
    assert result.metrics["profitability"] == 88.0
    assert result.metrics["moat"] == {"moat": "narrow"}


def test_verdict_thresholds(monkeypatch):
    cases = [
        (88.0, Verdict.BUY),
        (75.0, Verdict.BUY),
        (74.0, Verdict.WATCH),
        (60.0, Verdict.WATCH),
        (59.0, Verdict.HOLD),
        (40.0, Verdict.HOLD),
        (39.0, Verdict.AVOID),
        (0.0, Verdict.AVOID),
    ]
    for score, expected in cases:
        _patch(monkeypatch, score)
        result = BuffettClassicMethodology().evaluate("TEST", ["row"], _Prices())
        assert result.verdict == expected, f"score {score} -> {expected}"


def test_reasons_and_red_flags(monkeypatch):
    _patch(monkeypatch, 30.0)  # every pillar below the weak-pillar bar
    result = BuffettClassicMethodology().evaluate("TEST", ["row"], _Prices())
    assert result.reasons
    assert len(result.red_flags) == 4
    assert all("weak" in flag for flag in result.red_flags)
    _patch(monkeypatch, 90.0)
    result = BuffettClassicMethodology().evaluate("TEST", ["row"], _Prices())
    assert result.red_flags == []


def test_sources_point_to_the_engine(monkeypatch):
    _patch(monkeypatch, 70.0)
    result = BuffettClassicMethodology().evaluate("TEST", ["row"], _Prices())
    assert result.sources
    src = result.sources[0]
    assert "buffett_engine" in src.book
    assert src.era == "modern"
    assert src.us_caution is not None


def test_confidence_is_high(monkeypatch):
    _patch(monkeypatch, 70.0)
    result = BuffettClassicMethodology().evaluate("TEST", ["row"], _Prices())
    assert result.confidence == Confidence.HIGH


def test_insufficient_data():
    result = BuffettClassicMethodology().evaluate("TEST", [], _Prices())
    assert result.verdict == Verdict.INSUFFICIENT_DATA
    assert result.score is None


def test_rules_and_metadata(monkeypatch):
    methodology = BuffettClassicMethodology()
    rules = methodology.rules()
    assert len(rules) == 4
    assert all(rule.kind == "EXPLICIT" for rule in rules)
    assert all(rule.id.startswith("buffett_classic.") for rule in rules)
    meta = methodology.metadata()
    assert "Buffett" in meta["description"]
    assert "buffett_engine" in meta["source"]["book"]
