"""Descriptive statistics behind the peer-comparison artifact.

The scorecard compares a company against its industry (falling back to its
sector) using a precomputed artifact — see ``docs/scorecard_design.md`` §5
and ``scripts/build_peer_stats.py``. This module holds the *only* two pieces
of new mathematics that artifact needs, so the generator and the reader
(:class:`backend.services.peer_stats_service.PeerStatsService`) can never
disagree about them:

- :func:`quantile` — the linear-interpolation quantile used for the stored
  ``p10``/``p25``/``median``/``p75``/``p90`` summary.
- :func:`percentile_rank` — where one company sits inside a peer
  distribution: the share of peers strictly below it, with ties counting ½.

Pure Python (no numpy) so the artifact is byte-identical across platforms.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any

#: A peer group with fewer members than this is not written (and therefore
#: never used for a comparison). See ``docs/scorecard_design.md`` §5.
MIN_GROUP_COMPANIES = 10

#: Upper bound on the per-metric ``values`` array kept in the artifact. Larger
#: groups store a deterministic, evenly spaced sample of the sorted
#: distribution (the quantiles are always computed on the full set).
MAX_VALUES = 500

#: Quantiles stored per metric (name -> probability).
_QUANTILES: tuple[tuple[str, float], ...] = (
    ("p10", 0.10),
    ("p25", 0.25),
    ("median", 0.50),
    ("p75", 0.75),
    ("p90", 0.90),
)


def quantile(ordered: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile of an already-sorted sequence.

    Matches numpy's default (``method="linear"``), so ``quantile(v, 0.5)`` is
    the median of an even-length sample rather than a middle element.
    """
    if not ordered:
        raise ValueError("quantile of an empty sample")
    if len(ordered) == 1:
        return float(ordered[0])
    position = q * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(ordered[int(position)])
    span = ordered[high] - ordered[low]
    return float(ordered[low] + span * (position - low))


def percentile_rank(values: Iterable[float], value: float) -> float | None:
    """Share of ``values`` strictly below ``value`` (ties count ½).

    Returns a number in ``[0, 1]``: a company at the median of its group
    reads ≈ 0.5. ``None`` for an empty sample.
    """
    sample = sorted(float(v) for v in values)
    if not sample:
        return None
    below = sum(1 for v in sample if v < value)
    ties = sum(1 for v in sample if v == value)
    return (below + 0.5 * ties) / len(sample)


def decimate(ordered: Sequence[float], cap: int = MAX_VALUES) -> list[float]:
    """Deterministic evenly spaced sample of ``ordered`` (includes both ends).

    Sampling (rather than truncating) keeps a large group's spread visible;
    the index arithmetic is fixed, so the same input yields the same sample.
    """
    if cap < 2 or len(ordered) <= cap:
        return list(ordered)
    step = (len(ordered) - 1) / (cap - 1)
    return [ordered[round(i * step)] for i in range(cap)]


def summarize(values: Iterable[float], *, cap: int = MAX_VALUES) -> dict[str, Any]:
    """One metric's artifact entry: ``n``, quantiles, and the sorted values."""
    ordered = sorted(float(v) for v in values)
    if not ordered:
        return {"n": 0, "values": []}
    entry: dict[str, Any] = {"n": len(ordered), "min": _round(ordered[0])}
    for name, probability in _QUANTILES:
        entry[name] = _round(quantile(ordered, probability))
    entry["max"] = _round(ordered[-1])
    entry["values"] = [_round(v) for v in decimate(ordered, cap)]
    return entry


def _round(value: float) -> float:
    """Six decimals: enough precision, stable across platforms."""
    return round(float(value), 6)


#: The metrics the scorecard can compare against a peer group, with the unit
#: the artifact stores them in. ``multiple`` is a ratio (``15.2`` = 15.2x),
#: ``fraction`` a rate (``0.11`` = 11%).
METRIC_UNITS: dict[str, str] = {
    "pe_ratio": "multiple",
    "pb_ratio": "multiple",
    "fcf_yield": "fraction",
    "roe": "fraction",
    "net_margin": "fraction",
    "revenue_cagr_5y": "fraction",
}
