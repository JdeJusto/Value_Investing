"""Screening service: filter, rank, signal and surface opportunities.

Consumes only analytics/intelligence outputs (dicts produced by
``CompanyAnalysisService.analyze``) — provider calls happen upstream.
The same service can back the CLI, an API or a UI later.
"""

from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from backend.screener.filters import ScreenCriteria, from_kwargs, matches
from backend.screener.opportunity_engine import best_opportunity, detect_opportunities
from backend.screener.ranking_engine import rank_score, ranking_reasons
from backend.screener.signals import generate_signal

Analyzer = Callable[[str], Optional[dict]]


@dataclass
class ScreenedCompany:
    """One ranked, signaled, interpreted company from the screen."""

    ticker: str
    rank: int
    total_score: float
    rank_score: float
    moat: str
    rating: str
    confidence: str
    signal: str
    opportunity_type: Optional[str]
    reasons: list[str]

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "rank": self.rank,
            "total_score": self.total_score,
            "rank_score": self.rank_score,
            "moat": self.moat,
            "rating": self.rating,
            "confidence": self.confidence,
            "signal": self.signal,
            "opportunity_type": self.opportunity_type,
            "reasons": self.reasons,
        }


class ScreenerService:
    """Runs the full screen: analyze -> filter -> rank -> signal."""

    def __init__(
        self,
        analyzer: Analyzer,
        universe: Optional[Iterable[str]] = None,
        enrich: Optional[Callable[[str, dict], dict]] = None,
    ):
        """``analyzer`` must return the analysis dict (or None when no data).

        ``universe`` provides tickers to screen; ``enrich`` may attach
        extra fields (e.g. sector / industry) to each result.
        """
        self._analyzer = analyzer
        self._universe = list(universe) if universe is not None else None
        self._enrich = enrich

    # ------------------------------------------------------------------
    def run(self, **criteria) -> list[ScreenedCompany]:
        """Screen the universe and return companies sorted by rank."""
        return self._screen(from_kwargs(**criteria))

    def top_n(self, n: int = 20, **criteria) -> list[ScreenedCompany]:
        """The best ``n`` companies after filtering."""
        return self._screen(from_kwargs(**criteria))[: max(n, 0)]

    def opportunities(self, **criteria) -> list[dict]:
        """Every detected opportunity with its reasons."""
        results: list[dict] = []
        conditions = from_kwargs(**criteria)
        for item in self._collect(conditions):
            for opportunity in detect_opportunities(item):
                entry = dict(opportunity)
                entry["ticker"] = item["ticker"]
                entry["rank_score"] = rank_score(item)
                entry["signal"] = generate_signal(
                    dict(item, opportunity=opportunity), rank_score(item)
                )["signal"]
                results.append(entry)
        return sorted(results, key=lambda o: o["rank_score"], reverse=True)

    # ------------------------------------------------------------------
    def _collect(self, criteria: ScreenCriteria) -> list[dict]:
        tickers = criteria.tickers or (self._universe or [])
        items: list[dict] = []
        for ticker in tickers:
            result = self._analyzer(ticker)
            if result is None:
                continue
            result["ticker"] = result.get("ticker", ticker.upper())
            if self._enrich is not None:
                result = self._enrich(ticker, result)
            if matches(result, criteria):
                items.append(result)
        return items

    def _screen(self, criteria: ScreenCriteria) -> list[ScreenedCompany]:
        items = self._collect(criteria)
        ranked = sorted(items, key=lambda item: rank_score(item), reverse=True)
        companies: list[ScreenedCompany] = []
        for position, item in enumerate(ranked, start=1):
            score = rank_score(item)
            opportunity = best_opportunity(item)
            signal = generate_signal(dict(item, opportunity=opportunity), score)
            composite = item.get("composite_score") or {}
            reasons = list(signal["reason"])
            if opportunity:
                reasons = list(opportunity["reason"]) + reasons
            reasons = reasons + ranking_reasons(item)
            companies.append(
                ScreenedCompany(
                    ticker=item["ticker"],
                    rank=position,
                    total_score=composite.get("total_score", 0.0),
                    rank_score=score,
                    moat=(item.get("moat_analysis") or {}).get("moat_type", "NONE"),
                    rating=composite.get("rating", "D"),
                    confidence=composite.get("confidence", "LOW"),
                    signal=signal["signal"],
                    opportunity_type=opportunity["type"] if opportunity else None,
                    reasons=reasons,
                )
            )
        return companies
