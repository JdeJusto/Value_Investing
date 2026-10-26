"""Methodology ranking service.

Provides on-demand ranking by single methodology or by a combination of
methodologies over a universe of tickers. Reuses registry + run_methodologies
without duplicating the full offline batch logic from
scripts/compute_consensus_rankings.py.

See docs/methodology_ranking_design.md for design decisions.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Literal

from backend.methodologies.base import Verdict
from backend.methodologies.registry import discover, registry
from backend.services.ui_adapter import run_methodologies

logger = logging.getLogger(__name__)

VERDICT_ORDER = {
    Verdict.BUY: 4,
    Verdict.WATCH: 3,
    Verdict.HOLD: 2,
    Verdict.AVOID: 1,
    Verdict.NOT_APPLICABLE: 0,
    Verdict.INSUFFICIENT_DATA: -1,
}


@dataclass
class RankedTicker:
    ticker: str
    verdict: Verdict
    score: float | None
    family: str
    n_a_reason: str | None  # None if scored/evaluable, else why it's N/A


@dataclass
class CombinedRankedTicker:
    ticker: str
    per_methodology: dict[str, RankedTicker]
    combined_score: float | None
    combined_verdict: Verdict
    rationale: str  # human-readable explanation


def _is_na(verdict: Verdict) -> bool:
    return verdict in (Verdict.NOT_APPLICABLE, Verdict.INSUFFICIENT_DATA)


def _n_a_reason(verdict: Verdict, reasons: list[str] | None) -> str:
    if verdict == Verdict.NOT_APPLICABLE:
        if reasons and reasons:
            return reasons[0]
        return "Not applicable (financial/company type)"
    if verdict == Verdict.INSUFFICIENT_DATA:
        if reasons and reasons:
            return reasons[0]
        return "Insufficient data"
    return ""


def _get_universe_data(
    tickers: list[str],
) -> tuple[dict[str, list[Any]], dict[str, float | None], dict[str, float | None]]:
    """Load fundamentals and prices for tickers (minimal batch)."""
    from backend.app.cli import build_financial_repository
    from backend.services.price_service import get_price_service

    repository = build_financial_repository()
    price_service = get_price_service()

    fundamentals: dict[str, list[Any]] = {}
    prices: dict[str, float | None] = {}
    market_caps: dict[str, float | None] = {}

    for ticker in tickers:
        try:
            rows = repository.get_fundamentals(ticker, years=10) or []
            fundamentals[ticker] = rows
        except Exception:
            logger.debug("Failed to load fundamentals for %s", ticker, exc_info=True)
            fundamentals[ticker] = []

        try:
            price = price_service.get_current_price(ticker)
            prices[ticker] = price
        except Exception:
            logger.debug("Failed to get price for %s", ticker, exc_info=True)
            prices[ticker] = None

        try:
            market_cap = price_service.get_market_cap(ticker)
            market_caps[ticker] = market_cap
        except Exception:
            logger.debug("Failed to get market cap for %s", ticker, exc_info=True)
            market_caps[ticker] = None

    return fundamentals, prices, market_caps


def _rank_key_single(item: RankedTicker) -> tuple:
    """Sort key: score desc, verdict order desc, then ticker asc."""
    score_key = item.score if item.score is not None else -float("inf")
    verdict_key = VERDICT_ORDER.get(item.verdict, -10)
    return (-score_key, -verdict_key, item.ticker)


def _rank_key_combined(item: CombinedRankedTicker) -> tuple:
    """Sort key: combined_score desc, buy count desc, ticker asc."""
    score_key = (
        item.combined_score if item.combined_score is not None else -float("inf")
    )
    buy_count = sum(
        1 for rt in item.per_methodology.values() if rt.verdict == Verdict.BUY
    )
    return (-score_key, -buy_count, item.ticker)


def rank_by_methodology(
    methodology: str,
    universe: list[str],
    top_n: int = 20,
    *,
    include_na: bool = False,
    max_workers: int = 4,
) -> list[RankedTicker]:
    """Return top_n tickers by the given methodology."""
    if not universe:
        return []

    discover()
    methodology_obj = registry.get(methodology)
    if methodology_obj is None:
        raise ValueError(f"Unknown methodology: {methodology}")

    top_n = max(1, int(top_n))
    fundamentals, prices, market_caps = _get_universe_data(universe)
    results: list[RankedTicker] = []

    def _eval_one(ticker: str) -> RankedTicker | None:
        try:
            rows = fundamentals.get(ticker, [])
            price = prices.get(ticker)
            market_cap = market_caps.get(ticker)
            view = run_methodologies(ticker, rows, price, market_cap)
            # Find the result for this methodology
            for detail in view.details:
                if detail.get("methodology") == methodology:
                    verdict_str = detail.get("verdict", "INSUFFICIENT_DATA")
                    try:
                        verdict = Verdict(verdict_str)
                    except (ValueError, AttributeError):
                        verdict = Verdict.INSUFFICIENT_DATA
                    score = detail.get("score")
                    family = detail.get("family") or methodology_obj.family
                    na_reason = None
                    if _is_na(verdict):
                        reasons = detail.get("reasons") or []
                        na_reason = _n_a_reason(verdict, reasons)
                    return RankedTicker(
                        ticker=ticker,
                        verdict=verdict,
                        score=score if score is not None else None,
                        family=family,
                        n_a_reason=na_reason,
                    )
            # Not found in details - treat as insufficient
            return RankedTicker(
                ticker=ticker,
                verdict=Verdict.INSUFFICIENT_DATA,
                score=None,
                family=methodology_obj.family,
                n_a_reason="Insufficient data",
            )
        except Exception:
            logger.debug(
                "Failed to evaluate %s for %s", ticker, methodology, exc_info=True
            )
            return RankedTicker(
                ticker=ticker,
                verdict=Verdict.INSUFFICIENT_DATA,
                score=None,
                family=methodology_obj.family,
                n_a_reason="Evaluation error",
            )

    workers = max(1, min(int(max_workers), 4))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_eval_one, ticker): ticker for ticker in universe}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is None:
                    continue
                if _is_na(result.verdict) and not include_na:
                    continue
                results.append(result)
            except Exception:
                logger.debug("Future failed", exc_info=True)
                continue

    results.sort(key=_rank_key_single)
    return results[:top_n]


def rank_combined(
    methodologies: list[str],
    universe: list[str],
    strategy: Literal["and", "or", "weighted"],
    top_n: int = 20,
    *,
    weights: dict[str, float] | None = None,
    max_workers: int = 4,
) -> list[CombinedRankedTicker]:
    """Return top_n tickers matching the strategy."""
    if not universe or not methodologies:
        return []

    strategy = strategy.lower()
    if strategy not in ("and", "or", "weighted"):
        raise ValueError(f"Invalid strategy: {strategy}")

    discover()
    for m in methodologies:
        if registry.get(m) is None:
            raise ValueError(f"Unknown methodology: {m}")

    top_n = max(1, int(top_n))
    weights = weights or {}
    # Normalize weights
    weight_map = {m: float(weights.get(m, 1.0)) for m in methodologies}

    # Evaluate all methodologies for all tickers
    per_ticker_results: dict[str, dict[str, RankedTicker]] = {}
    for methodology in methodologies:
        ranked = rank_by_methodology(
            methodology,
            universe,
            top_n=len(universe),
            include_na=True,
            max_workers=max_workers,
        )
        for rt in ranked:
            if rt.ticker not in per_ticker_results:
                per_ticker_results[rt.ticker] = {}
            per_ticker_results[rt.ticker][methodology] = rt

    combined_results: list[CombinedRankedTicker] = []

    for ticker in universe:
        ticker_data = per_ticker_results.get(ticker, {})
        # Ensure all methodologies have data
        all_have = all(m in ticker_data for m in methodologies)
        if not all_have:
            continue

        rt_map = {m: ticker_data[m] for m in methodologies}

        if strategy == "and":
            # Require BUY or WATCH in ALL
            all_pass = all(
                rt_map[m].verdict in (Verdict.BUY, Verdict.WATCH) for m in methodologies
            )
            if not all_pass:
                continue
            # Compute combined score (average of available scores)
            scores = [
                rt_map[m].score for m in methodologies if rt_map[m].score is not None
            ]
            combined_score = sum(scores) / len(scores) if scores else None
            # Determine combined verdict
            buys = sum(1 for m in methodologies if rt_map[m].verdict == Verdict.BUY)
            if buys == len(methodologies):
                combined_verdict = Verdict.BUY
            else:
                combined_verdict = Verdict.WATCH
            rationale_parts = [
                f"{rt_map[m].verdict.value} in {m}" for m in methodologies
            ]
            rationale = " AND ".join(rationale_parts)
            combined_results.append(
                CombinedRankedTicker(
                    ticker=ticker,
                    per_methodology=rt_map,
                    combined_score=combined_score,
                    combined_verdict=combined_verdict,
                    rationale=rationale,
                )
            )

        elif strategy == "or":
            # Require BUY or WATCH in AT LEAST ONE
            any_pass = any(
                rt_map[m].verdict in (Verdict.BUY, Verdict.WATCH) for m in methodologies
            )
            if not any_pass:
                continue
            scores = [
                rt_map[m].score for m in methodologies if rt_map[m].score is not None
            ]
            combined_score = sum(scores) / len(scores) if scores else None
            # Combined verdict = best verdict among passing
            passing_verdicts = [
                rt_map[m].verdict
                for m in methodologies
                if rt_map[m].verdict in (Verdict.BUY, Verdict.WATCH)
            ]
            if Verdict.BUY in passing_verdicts:
                combined_verdict = Verdict.BUY
            else:
                combined_verdict = Verdict.WATCH
            rationale_parts = [
                f"{rt_map[m].verdict.value} in {m}" for m in methodologies
            ]
            rationale = " OR ".join(rationale_parts)
            combined_results.append(
                CombinedRankedTicker(
                    ticker=ticker,
                    per_methodology=rt_map,
                    combined_score=combined_score,
                    combined_verdict=combined_verdict,
                    rationale=rationale,
                )
            )

        elif strategy == "weighted":
            # Only tickers with numeric score in ALL
            all_scores = []
            for m in methodologies:
                s = rt_map[m].score
                if s is None:
                    break
                all_scores.append(s)
            else:
                # All have scores
                total_weight = sum(weight_map[m] for m in methodologies)
                if total_weight > 0:
                    combined_score = (
                        sum(
                            weight_map[m] * all_scores[i]
                            for i, m in enumerate(methodologies)
                        )
                        / total_weight
                    )
                else:
                    combined_score = sum(all_scores) / len(all_scores)
                # Verdict based on weighted score approximation or best
                if any(rt_map[m].verdict == Verdict.AVOID for m in methodologies):
                    combined_verdict = Verdict.WATCH  # Conservative
                elif all(
                    rt_map[m].verdict in (Verdict.BUY, Verdict.WATCH)
                    for m in methodologies
                ):
                    buys = sum(
                        1 for m in methodologies if rt_map[m].verdict == Verdict.BUY
                    )
                    combined_verdict = (
                        Verdict.BUY if buys >= len(methodologies) / 2 else Verdict.WATCH
                    )
                else:
                    combined_verdict = Verdict.HOLD
                rationale_parts = [
                    f"{rt_map[m].score:.2f} ({m})" for m in methodologies
                ]
                rationale = f"Weighted: {combined_score:.2f} | " + ", ".join(
                    rationale_parts
                )
                combined_results.append(
                    CombinedRankedTicker(
                        ticker=ticker,
                        per_methodology=rt_map,
                        combined_score=combined_score,
                        combined_verdict=combined_verdict,
                        rationale=rationale,
                    )
                )

    combined_results.sort(key=_rank_key_combined)
    return combined_results[:top_n]
