"""Unit tests for the methodology framework base and registry.

These tests never touch the network or the database: the registry is exercised
with a dummy methodology, which is also what proves the ABC is implementable.
"""

from __future__ import annotations

import pytest

from backend.methodologies.base import (
    Confidence,
    Methodology,
    MethodologyResult,
    Rule,
    SourceRef,
    Verdict,
)
from backend.methodologies.registry import MethodologyRegistry, discover, registry


# ----------------------------------------------------------------------
# enums
# ----------------------------------------------------------------------


def test_verdict_is_a_str_enum():
    """Verdicts must interpolate as plain strings in reports."""
    assert Verdict.BUY == "BUY"
    assert Verdict.WATCH == "WATCH"
    assert Verdict.HOLD == "HOLD"
    assert Verdict.AVOID == "AVOID"
    assert Verdict.INSUFFICIENT_DATA == "INSUFFICIENT_DATA"


def test_confidence_is_a_str_enum():
    assert Confidence.HIGH == "HIGH"
    assert Confidence.MEDIUM == "MEDIUM"
    assert Confidence.LOW == "LOW"


def test_verdicts_are_distinct():
    assert len(set(Verdict)) == 5
    assert len(set(Confidence)) == 3


# ----------------------------------------------------------------------
# SourceRef
# ----------------------------------------------------------------------


def test_source_ref_is_frozen():
    ref = SourceRef(
        book="The Intelligent Investor",
        edition="4th revised (Zweig)",
        year=1973,
        page="p. 112",
        era="1973",
    )
    with pytest.raises(Exception):
        ref.book = "other"  # type: ignore[misc]


def test_source_ref_requires_era():
    """Decision 6: a source without its era is not a valid reference."""
    ref = SourceRef(
        book="Security Analysis",
        edition="3rd",
        year=1934,
        page="p. 5",
        era="1934",
        us_caution="$ thresholds are 1934 dollars",
    )
    assert ref.era == "1934"
    assert ref.us_caution is not None


def test_source_ref_us_caution_is_optional():
    ref = SourceRef(book="B", edition="1st", year=2000, page="p. 1", era="2000")
    assert ref.us_caution is None


# ----------------------------------------------------------------------
# Rule
# ----------------------------------------------------------------------


def test_rule_carries_kind_and_source():
    ref = SourceRef(
        book="The Intelligent Investor",
        edition="4th revised",
        year=1973,
        page="Ch. 14",
        era="1973",
    )
    rule = Rule(
        id="graham.criterion_6_pe",
        name="Moderate P/E",
        description="Current P/E must not exceed 15",
        kind="EXPLICIT",
        source=ref,
    )
    assert rule.kind == "EXPLICIT"
    assert rule.source.page == "Ch. 14"


# ----------------------------------------------------------------------
# MethodologyResult
# ----------------------------------------------------------------------


def test_result_allows_score_none():
    """Decision 10: score=None is a valid result, not a zero."""
    result = MethodologyResult(
        methodology="dummy",
        version="1.0.0",
        family="OTHER",
        verdict=Verdict.BUY,
        score=None,
        metrics={},
        reasons=[],
        red_flags=[],
        confidence=Confidence.HIGH,
        sources=[],
    )
    assert result.score is None


def test_result_tracks_passed_and_failed_rules():
    result = MethodologyResult(
        methodology="dummy",
        version="1.0.0",
        family="OTHER",
        verdict=Verdict.AVOID,
        score=10.0,
        metrics={},
        reasons=[],
        red_flags=[],
        confidence=Confidence.LOW,
        sources=[],
        passed_rules=["a"],
        failed_rules=["b", "c"],
    )
    assert result.passed_rules == ["a"]
    assert result.failed_rules == ["b", "c"]


# ----------------------------------------------------------------------
# Methodology ABC
# ----------------------------------------------------------------------


class DummyMethodology(Methodology):
    """Minimal concrete methodology used to test the registry."""

    name = "dummy"
    version = "1.0.0"
    family = "OTHER"

    def evaluate(self, ticker, fundamentals, prices):
        return MethodologyResult(
            methodology=self.name,
            version=self.version,
            family=self.family,
            verdict=Verdict.HOLD,
            score=50.0,
            metrics={"dummy_metric": 1.0},
            reasons=["always holds"],
            red_flags=[],
            confidence=Confidence.MEDIUM,
            sources=[],
            passed_rules=["dummy.rule"],
        )

    def rules(self):
        ref = SourceRef(book="Dummy", edition="1st", year=2020, page="p. 1", era="2020")
        return [Rule(id="dummy.rule", name="Dummy rule", description="x",
                     kind="EXPLICIT", source=ref)]

    def metadata(self):
        return {"name": self.name, "version": self.version, "family": self.family}


def test_abc_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Methodology()  # type: ignore[abstract]


def test_dummy_methodology_evaluates_deterministically():
    m = DummyMethodology()
    first = m.evaluate("AAPL", fundamentals=None, prices=None)
    second = m.evaluate("AAPL", fundamentals=None, prices=None)

    assert first == second
    assert first.verdict == Verdict.HOLD
    assert first.score == 50.0


def test_dummy_methodology_exposes_rules_and_metadata():
    m = DummyMethodology()
    assert m.rules()[0].id == "dummy.rule"
    assert m.rules()[0].kind == "EXPLICIT"
    assert m.metadata()["name"] == "dummy"


# ----------------------------------------------------------------------
# registry
# ----------------------------------------------------------------------


def test_registry_registers_and_retrieves():
    r = MethodologyRegistry()
    m = DummyMethodology()

    r.register(m)

    assert r.get("dummy") is m
    assert r.get("missing") is None
    assert r.list() == ["dummy"]
    assert len(r) == 1
    assert "dummy" in r


def test_registry_list_is_sorted():
    r = MethodologyRegistry()

    class Zeta(DummyMethodology):
        name = "zeta"

    class Alpha(DummyMethodology):
        name = "alpha"

    r.register(Zeta())
    r.register(Alpha())

    assert r.list() == ["alpha", "zeta"]


def test_registry_replacing_a_name_is_not_duplicated():
    r = MethodologyRegistry()
    r.register(DummyMethodology())
    r.register(DummyMethodology())

    assert r.list() == ["dummy"]
    assert len(r) == 1


def test_discover_is_idempotent():
    """Running discovery twice must not duplicate or error."""
    discover()
    first = registry.list()
    count = discover()

    assert registry.list() == first
    assert count == 0  # nothing new to register on the second pass


def test_global_registry_is_the_same_object():
    from backend.methodologies import registry as imported

    assert imported is registry
