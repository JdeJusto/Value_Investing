"""Backtesting strategies: deterministic portfolio selection rules.

The fundamental momentum factor follows the documented formula with
cross-sectional normalization per snapshot:

    momentum = 0.4*revenue_growth_delta + 0.3*margin_delta
             + 0.2*roic_delta + 0.1*fcf_growth_delta

Every component is z-normalized against the snapshot universe (when
at least two companies are available) so scores are comparable.
"""

from collections.abc import Callable

from backend.screener.ranking_engine import rank_score

# Formula weights from the specification
REV_DELTA_WEIGHT = 0.4
MARGIN_DELTA_WEIGHT = 0.3
ROIC_DELTA_WEIGHT = 0.2
FCF_GROWTH_DELTA_WEIGHT = 0.1

Strategy = Callable[[dict, int], list[str]]


def _z_scores(values: dict[str, float | None]) -> dict[str, float | None]:
    """Cross-sectional z-score: (value - mean) / std over present values."""
    present = {k: v for k, v in values.items() if v is not None}
    if not present:
        return {k: None for k in values}
    z: dict[str, float | None] = {}
    if len(present) >= 2:
        mean = sum(present.values()) / len(present)
        variance = sum((v - mean) ** 2 for v in present.values()) / len(present)
        stddev = variance**0.5
        if stddev > 0:
            for key, value in values.items():
                z[key] = (value - mean) / stddev if value is not None else None
            return z
    return dict(values)


def fundamental_momentum_scores(analyses: dict) -> dict[str, float | None]:
    """Momentum per ticker, z-normalized across the snapshot universe."""
    deltas = {
        ticker: (analysis.get("delta_metrics") or {})
        for ticker, analysis in analyses.items()
    }
    components = {
        "revenue_growth_delta": {
            t: d.get("revenue_growth_delta") for t, d in deltas.items()
        },
        "gross_margin_delta": {
            t: d.get("gross_margin_delta") for t, d in deltas.items()
        },
        "roic_delta": {t: d.get("roic_delta") for t, d in deltas.items()},
        "fcf_growth_delta": {t: d.get("fcf_growth_delta") for t, d in deltas.items()},
    }
    z: dict[str, dict[str, float | None]] = {
        name: _z_scores(values) for name, values in components.items()
    }

    scores: dict[str, float | None] = {}
    for ticker in analyses:
        raw = []
        for weight, spec in (
            (REV_DELTA_WEIGHT, z["revenue_growth_delta"]),
            (MARGIN_DELTA_WEIGHT, z["gross_margin_delta"]),
            (ROIC_DELTA_WEIGHT, z["roic_delta"]),
            (FCF_GROWTH_DELTA_WEIGHT, z["fcf_growth_delta"]),
        ):
            value = spec[ticker]
            if value is not None:
                raw.append(weight * value)
        scores[ticker] = sum(raw) if raw else None
    return scores


def momentum_strategy(analyses: dict, top_n: int) -> list[str]:
    """Pick the ``top_n`` tickers with the strongest fundamental momentum."""
    ranked = fundamental_momentum_scores(analyses)
    ranked = {t: s for t, s in ranked.items() if s is not None}
    ordered = sorted(ranked.items(), key=lambda kv: kv[1], reverse=True)
    return [ticker for ticker, _ in ordered[:top_n]]


def buffett_strategy(analyses: dict, top_n: int) -> list[str]:
    """Pick the ``top_n`` tickers by the ranking engine (quality + value)."""
    ordered = sorted(analyses.items(), key=lambda kv: rank_score(kv[1]), reverse=True)
    return [ticker for ticker, _ in ordered[:top_n]]


STRATEGIES: dict[str, Strategy] = {
    "buffett": buffett_strategy,
    "momentum": momentum_strategy,
}


def get_strategy(name: str) -> Strategy:
    try:
        return STRATEGIES[name.lower()]
    except KeyError as exc:
        raise ValueError(
            f"unknown strategy '{name}'; use one of {sorted(STRATEGIES)}"
        ) from exc
