"""Relative buy tiers with **demote-only** semantics.

The methodology's own verdict is the ceiling: only companies whose rules said
``BUY`` can receive a tier, and the relative ranking can demote them
(``WATCH``/``HOLD``/``AVOID``) but never promote a ``WATCH``/``HOLD``/``AVOID``
into a buy. This keeps Graham-like screens honest: a company that fails the
rules never becomes a buy because its score is high in a weak universe.

Bands are assigned by **exact position** in the ranked scored universe
(score descending, ticker ascending as the deterministic tie-break):

- top 3%  -> STRONG_BUY
- 3-10%   -> BUY
- 10-15%  -> WEAK_BUY
- 15-30%  -> WATCH
- 30-50%  -> HOLD
- bottom 50% -> AVOID

Universes with fewer than :data:`MIN_PERCENTILE_UNIVERSE` scored companies use
absolute score cut-offs instead (80/60/50/40/30), so a small demo universe
does not label mediocre scores as strong buys.
"""

from __future__ import annotations

import math

from backend.methodologies.base import MethodologyResult, Verdict, is_positive

#: Minimum scored universe for percentile bands; below it, absolute cut-offs.
MIN_PERCENTILE_UNIVERSE = 50
#: Upper bounds of the positive tiers (fractions of the scored universe).
TIER_PERCENTILES = (("STRONG_BUY", 0.03), ("BUY", 0.10), ("WEAK_BUY", 0.15))
#: Upper bounds of the demotion bands.
DEMOTE_PERCENTILES = (("WATCH", 0.30), ("HOLD", 0.50))
#: Absolute score cut-offs for universes < MIN_PERCENTILE_UNIVERSE (0-100).
ABSOLUTE_TIERS = (
    (80.0, "STRONG_BUY"),
    (60.0, "BUY"),
    (50.0, "WEAK_BUY"),
    (40.0, "WATCH"),
    (30.0, "HOLD"),
)
#: Reasons recorded alongside a tier (debug/audit, not shown to users).
_POSITIVE_LABELS = {"STRONG_BUY", "BUY", "WEAK_BUY"}


def absolute_label(score: float) -> str:
    """Band label from an absolute 0-100 score (small-universe fallback)."""
    for threshold, label in ABSOLUTE_TIERS:
        if score >= threshold:
            return label
    return "AVOID"


def _band_for_position(index: int, total: int) -> str:
    """Band label for the ``index``-th ranked company (0-based, descending)."""
    for label, percentile in TIER_PERCENTILES:
        if index < math.ceil(total * percentile):
            return label
    for label, percentile in DEMOTE_PERCENTILES:
        if index < math.ceil(total * percentile):
            return label
    return "AVOID"


def assign_demote_tiers(
    scores: dict[str, float],
) -> dict[str, tuple[Verdict, str | None]]:
    """Assign a band to every scored ticker (no verdict filtering here).

    The caller decides which tickers are eligible (only base ``BUY``).
    ``scores`` must contain numeric scores only.
    """
    if not scores:
        return {}
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    if len(ordered) < MIN_PERCENTILE_UNIVERSE:
        result: dict[str, tuple[Verdict, str | None]] = {}
        for ticker, score in ordered:
            label = absolute_label(score)
            result[ticker] = (
                Verdict(label),
                label if label in _POSITIVE_LABELS else None,
            )
        return result
    result: dict[str, tuple[Verdict, str | None]] = {}
    for index, (ticker, _score) in enumerate(ordered):
        label = _band_for_position(index, len(ordered))
        result[ticker] = (Verdict(label), label if label in _POSITIVE_LABELS else None)
    return result


def compute_tiers_from_pairs(
    pairs: dict[str, tuple[Verdict, float | None]],
) -> dict[str, tuple[Verdict, str | None]]:
    """Demote-only tier map from ``{ticker: (base_verdict, score)}``.

    Every scored pair (any verdict except N/A/INSUFFICIENT_DATA) takes part in
    the ranking so the percentile bands reflect the whole universe. Only base
    ``BUY`` pairs receive a map entry; a base BUY without a score stays BUY
    with ``tier=None``.
    """
    scored: dict[str, float] = {}
    for ticker, (verdict, score) in pairs.items():
        if verdict in (Verdict.NOT_APPLICABLE, Verdict.INSUFFICIENT_DATA):
            continue
        if score is not None:
            scored[ticker] = float(score)
    bands = assign_demote_tiers(scored)

    tier_map: dict[str, tuple[Verdict, str | None]] = {}
    for ticker, (verdict, score) in pairs.items():
        if verdict is not Verdict.BUY:
            continue
        if score is None:
            tier_map[ticker] = (Verdict.BUY, None)
        elif ticker in bands:
            tier_map[ticker] = bands[ticker]
    return tier_map


def compute_tiers_demote_only(
    results: dict[str, MethodologyResult],
) -> dict[str, tuple[Verdict, str | None]]:
    """Tier map for the base-BUY tickers only (demote-only)."""
    return compute_tiers_from_pairs(
        {ticker: (result.verdict, result.score) for ticker, result in results.items()}
    )


def apply_demote_tiers(
    results: dict[str, MethodologyResult],
) -> dict[str, tuple[Verdict, str | None]]:
    """Apply the demote-only map in place and return it.

    Non-BUY results keep their verdict and get ``tier=None``; N/A and
    INSUFFICIENT_DATA are untouched.
    """
    tier_map = compute_tiers_demote_only(results)
    for ticker, result in results.items():
        if ticker in tier_map:
            verdict, tier = tier_map[ticker]
            result.verdict = verdict
            result.tier = tier
        else:
            result.tier = None
    return tier_map


def apply_absolute_tiers(results: list[MethodologyResult]) -> None:
    """Apply the small-universe fallback to a single-ticker result list.

    Each methodology is independent here, so the "universe" size for the
    fallback is one and the absolute cut-offs apply (only to base BUYs).
    Non-BUY verdicts are never promoted.
    """
    for result in results:
        result.tier = None
        if result.verdict is not Verdict.BUY or result.score is None:
            continue
        label = absolute_label(float(result.score))
        result.verdict = Verdict(label)
        result.tier = label if label in _POSITIVE_LABELS else None


def tier_counts(results: dict[str, MethodologyResult]) -> dict[str, int]:
    """Count final verdicts per tier/label (used by backtest/output)."""
    counts = {
        label: 0
        for label in ("STRONG_BUY", "BUY", "WEAK_BUY", "WATCH", "HOLD", "AVOID")
    }
    for result in results.values():
        value = result.verdict.value
        if value in counts:
            counts[value] += 1
    return counts


#: Portfolio weight of each positive tier (normalized when a tier is empty).
TIER_WEIGHTS = {"STRONG_BUY": 0.60, "BUY": 0.30, "WEAK_BUY": 0.10}


def compute_year_return(
    ticker_returns: dict[str, float],
    ticker_verdicts: dict[str, Verdict | str | None],
    weighting: str = "tier",
) -> float:
    """Return one year's portfolio return for the positive signals.

    ``weighting="tier"`` uses 60/30/10 for STRONG_BUY/BUY/WEAK_BUY, normalized
    to the tiers actually present (e.g. BUY+WEAK -> 75/25). ``"equal"`` is the
    legacy equal-weight behaviour. No positive signal -> cash (0.0).
    """
    by_tier: dict[str, list[float]] = {}
    for ticker, value in ticker_returns.items():
        verdict = ticker_verdicts.get(ticker)
        if not is_positive(verdict):
            continue
        key = verdict.value if isinstance(verdict, Verdict) else str(verdict)
        by_tier.setdefault(key, []).append(float(value))
    if not by_tier:
        return 0.0
    if weighting == "equal":
        all_returns = [value for values in by_tier.values() for value in values]
        return sum(all_returns) / len(all_returns)
    weights = {key: TIER_WEIGHTS.get(key, 0.0) for key in by_tier}
    total_weight = sum(weights.values())
    if total_weight <= 0:
        return 0.0
    return sum(
        (weights[key] / total_weight) * (sum(values) / len(values))
        for key, values in by_tier.items()
    )
