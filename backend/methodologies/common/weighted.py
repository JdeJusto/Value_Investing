"""Shared weighted-rule framework for the deep methodology expansions.

The v0.26.0 Graham and v0.27.0 Buffett expansions established the pattern:
each rule is an explicit check with a weight (2 critical, 1 normal, 0
informational), and the verdict is the weighted pass ratio:

    score = sum(weight for passed) / sum(weight for evaluable)
    BUY >= 0.85, WATCH >= 0.70, HOLD >= 0.50, else AVOID
    >30% of the weighted rules missing -> INSUFFICIENT_DATA

This module keeps that logic in one place so the six later methodologies do
not re-implement it with slightly different thresholds.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from backend.methodologies.base import (
    Confidence,
    Rule,
    SourceRef,
    Verdict,
)

BUY_THRESHOLD = 0.85
WATCH_THRESHOLD = 0.70
HOLD_THRESHOLD = 0.50
MAX_MISSING_WEIGHT = 0.30


@dataclass(frozen=True)
class WeightedResult:
    """Outcome of one weighted rule (``passed=None`` = not evaluable)."""

    rule_id: str
    name: str
    category: str
    weight: int
    passed: bool | None
    detail: str
    value: float | None = None
    threshold: float | None = None


@dataclass(frozen=True)
class WeightedCheck:
    """Definition of one weighted rule."""

    rule_id: str
    name: str
    category: str
    weight: int
    description: str
    source: SourceRef
    evaluate: Callable[..., WeightedResult]

    def rule(self) -> Rule:
        return Rule(
            id=self.rule_id,
            name=self.name,
            description=self.description,
            kind="INFERRED",
            source=self.source,
        )


def result(
    check: WeightedCheck,
    passed: bool | None,
    detail: str,
    *,
    value: float | None = None,
    threshold: float | None = None,
) -> WeightedResult:
    """Build a :class:`WeightedResult` from a check definition."""
    return WeightedResult(
        rule_id=check.rule_id,
        name=check.name,
        category=check.category,
        weight=check.weight,
        passed=passed,
        value=value,
        threshold=threshold,
        detail=detail,
    )


def weighted_verdict(
    results: Iterable[WeightedResult],
) -> tuple[Verdict, float | None, Confidence]:
    """Weighted pass ratio -> ``(verdict, score, confidence)``."""
    weighted = [(item.passed, item.weight) for item in results if item.weight > 0]
    total_all = sum(weight for _passed, weight in weighted)
    if total_all <= 0:
        return Verdict.INSUFFICIENT_DATA, None, Confidence.LOW
    missing = sum(weight for passed, weight in weighted if passed is None)
    if missing / total_all > MAX_MISSING_WEIGHT:
        return Verdict.INSUFFICIENT_DATA, None, Confidence.LOW
    evaluable = [(passed, weight) for passed, weight in weighted if passed is not None]
    total = sum(weight for _passed, weight in evaluable)
    if total <= 0:
        return Verdict.INSUFFICIENT_DATA, None, Confidence.LOW
    passed_weight = sum(weight for passed, weight in evaluable if passed)
    ratio = passed_weight / total
    if ratio >= BUY_THRESHOLD:
        verdict = Verdict.BUY
    elif ratio >= WATCH_THRESHOLD:
        verdict = Verdict.WATCH
    elif ratio >= HOLD_THRESHOLD:
        verdict = Verdict.HOLD
    else:
        verdict = Verdict.AVOID
    confidence = (
        Confidence.HIGH
        if missing == 0
        else Confidence.MEDIUM
        if missing / total_all <= 0.10
        else Confidence.LOW
    )
    return verdict, round(ratio * 100, 2), confidence


def rule_weights(results: Iterable[WeightedResult]) -> dict[str, int]:
    """Convenience mapping used by docs/diagnostics."""
    return {item.rule_id: item.weight for item in results}


def missing_ratio(results: Iterable[WeightedResult]) -> float:
    """Share of weighted rules that could not be evaluated (0.0-1.0)."""
    weighted = [(item.passed, item.weight) for item in results if item.weight > 0]
    total = sum(weight for _passed, weight in weighted)
    if total <= 0:
        return 1.0
    missing = sum(weight for passed, weight in weighted if passed is None)
    return missing / total


__all__ = [
    "BUY_THRESHOLD",
    "HOLD_THRESHOLD",
    "MAX_MISSING_WEIGHT",
    "WATCH_THRESHOLD",
    "WeightedCheck",
    "WeightedResult",
    "missing_ratio",
    "result",
    "rule_weights",
    "weighted_verdict",
]
