"""Sanity guards for valuation ratios.

A ratio rule must fail (never pass) when the ratio is not meaningful: a
negative P/E means the company lost money, and a four-digit P/E or a
triple-digit EV/EBIT is a near-zero-denominator artifact, not cheapness.
Every methodology that gates a rule on one of these ratios applies the
matching guard before comparing it with a threshold.

Thresholds are deliberately loose: the goal is to reject the obviously
nonsensical (losses, near-zero denominators), not to second-guess a
methodology's own stricter bound.
"""

from __future__ import annotations

#: Above this a P/E is a denominator artifact rather than a valuation.
MAX_MEANINGFUL_PE = 100.0
#: Above this a P/BV is a denominator artifact.
MAX_MEANINGFUL_PBV = 50.0
#: Above this an EV/EBIT is a denominator artifact.
MAX_MEANINGFUL_EV_EBIT = 100.0
#: Beyond +/-100% an FCF yield is a market-cap artifact, not generosity.
MAX_MEANINGFUL_FCF_YIELD = 1.0


def is_meaningful_pe(pe: float | None) -> bool:
    """True only for a strictly positive P/E within ``MAX_MEANINGFUL_PE``.

    A negative P/E (losses) and a near-zero-denominator P/E both return
    False, so a value rule fails instead of passing on a meaningless ratio.
    """
    return pe is not None and 0.0 < pe <= MAX_MEANINGFUL_PE


def is_meaningful_pbv(pbv: float | None) -> bool:
    """True only for a strictly positive P/BV within ``MAX_MEANINGFUL_PBV``."""
    return pbv is not None and 0.0 < pbv <= MAX_MEANINGFUL_PBV


def is_meaningful_ev_ebit(ev_ebit: float | None) -> bool:
    """True only for a strictly positive EV/EBIT within its bound.

    A negative EBIT (or negative enterprise value) is not a margin of
    safety, and a P/E-like extreme is an artifact.
    """
    return ev_ebit is not None and 0.0 < ev_ebit <= MAX_MEANINGFUL_EV_EBIT


def is_meaningful_fcf_yield(fcf_yield: float | None) -> bool:
    """True when an FCF yield sits in a plausible band.

    Beyond +/-100% the yield is driven by a tiny market cap, not by cash
    generation, so it must not count as a margin of safety.
    """
    return (
        fcf_yield is not None
        and -MAX_MEANINGFUL_FCF_YIELD <= fcf_yield <= MAX_MEANINGFUL_FCF_YIELD
    )
