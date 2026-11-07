"""Demote-only buy tiers, weighting and consensus compatibility."""

from __future__ import annotations

import pytest

from backend.methodologies.base import Verdict, is_positive
from backend.methodologies.tiers import (
    absolute_label,
    compute_tiers_from_pairs,
    compute_year_return,
)
from backend.services.consensus_service import summarize_verdicts


def _pair(verdict: Verdict, score: float | None = None):
    return (verdict, score)


def test_is_positive_only_three_tiers():
    assert is_positive(Verdict.STRONG_BUY) is True
    assert is_positive(Verdict.BUY) is True
    assert is_positive(Verdict.WEAK_BUY) is True
    for verdict in (Verdict.WATCH, Verdict.HOLD, Verdict.AVOID, Verdict.NOT_APPLICABLE):
        assert is_positive(verdict) is False
    assert is_positive(None) is False


def test_demote_only_never_promotes():
    pairs = {
        "WATCHER": _pair(Verdict.WATCH, 99.0),
        "HOLDER": _pair(Verdict.HOLD, 98.0),
        "AVOIDER": _pair(Verdict.AVOID, 97.0),
        "BUYER": _pair(Verdict.BUY, 60.0),
    }
    tiers = compute_tiers_from_pairs(pairs)

    assert "WATCHER" not in tiers
    assert "HOLDER" not in tiers
    assert "AVOIDER" not in tiers
    assert "BUYER" in tiers


def test_relative_percentiles_with_100_buys():
    pairs = {f"T{index:03d}": _pair(Verdict.BUY, 100.0 - index) for index in range(100)}
    tiers = compute_tiers_from_pairs(pairs)
    labels = [tiers[f"T{index:03d}"][0] for index in range(100)]

    assert labels[:3] == [Verdict.STRONG_BUY] * 3
    assert labels[3:10] == [Verdict.BUY] * 7
    assert labels[10:15] == [Verdict.WEAK_BUY] * 5
    assert labels[15:30] == [Verdict.WATCH] * 15
    assert labels[30:50] == [Verdict.HOLD] * 20
    assert labels[50:] == [Verdict.AVOID] * 50


def test_buy_without_score_stays_buy_without_tier():
    tiers = compute_tiers_from_pairs({"A": _pair(Verdict.BUY, None)})
    assert tiers["A"] == (Verdict.BUY, None)


def test_absolute_fallback_below_50():
    assert absolute_label(85.0) == "STRONG_BUY"
    assert absolute_label(65.0) == "BUY"
    assert absolute_label(55.0) == "WEAK_BUY"
    assert absolute_label(45.0) == "WATCH"
    assert absolute_label(35.0) == "HOLD"
    assert absolute_label(10.0) == "AVOID"

    pairs = {f"T{index}": _pair(Verdict.BUY, 70.0) for index in range(30)}
    tiers = compute_tiers_from_pairs(pairs)
    assert {verdict for verdict, _tier in tiers.values()} == {Verdict.BUY}


def test_consensus_aggregates_tiers_as_buy():
    verdicts = {
        "a": "STRONG_BUY",
        "b": "BUY",
        "c": "WEAK_BUY",
        "d": "WATCH",
        "e": "AVOID",
        "f": "N/A",
    }
    counts = summarize_verdicts(verdicts)
    assert counts["buy_count"] == 3
    assert counts["avoid_count"] == 1
    assert counts["consensus_score"] == 2


def test_tier_weighting_with_all_tiers():
    returns = {"S": 0.10, "B1": 0.05, "B2": 0.05, "W1": 0.02, "W2": 0.02, "W3": 0.02}
    verdicts = {
        "S": Verdict.STRONG_BUY,
        "B1": Verdict.BUY,
        "B2": Verdict.BUY,
        "W1": Verdict.WEAK_BUY,
        "W2": Verdict.WEAK_BUY,
        "W3": Verdict.WEAK_BUY,
    }
    # 0.6*10 + 0.3*5 + 0.1*2 = 7.7%
    assert compute_year_return(returns, verdicts, "tier") == pytest.approx(0.077)


def test_tier_weighting_rescales_without_strong():
    returns = {"B": 0.10, "W": 0.02}
    verdicts = {"B": Verdict.BUY, "W": Verdict.WEAK_BUY}
    # 0.75*10 + 0.25*2 = 8%
    assert compute_year_return(returns, verdicts, "tier") == pytest.approx(0.08)


def test_cash_when_no_positive():
    assert compute_year_return({"A": 0.5}, {"A": Verdict.AVOID}, "tier") == 0.0
    assert compute_year_return({}, {}, "tier") == 0.0


def test_equal_weight_legacy():
    returns = {"S": 0.10, "W": 0.02}
    verdicts = {"S": Verdict.STRONG_BUY, "W": Verdict.WEAK_BUY}
    assert compute_year_return(returns, verdicts, "equal") == pytest.approx(0.06)
