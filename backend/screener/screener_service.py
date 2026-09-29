"""Screening service: filter, rank, signal and surface opportunities.

Consumes only analytics/intelligence outputs (dicts produced by
``CompanyAnalysisService.analyze``) — provider calls happen upstream.
The same service can back the CLI, an API or a UI later.
"""

from dataclasses import dataclass
from typing import Optional
from collections.abc import Callable, Iterable

from backend.screener.filters import ScreenCriteria, from_kwargs, matches
from backend.screener.opportunity_engine import best_opportunity, detect_opportunities
from backend.screener.ranking_engine import calibrated_rank, rank_score, ranking_reasons
from backend.screener.signals import generate_signal

Analyzer = Callable[[str], dict | None]


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
    opportunity_type: str | None
    reasons: list[str]
    metrics: dict | None = None

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
            "metrics": self.metrics,
        }


class ScreenerService:
    """Runs the full screen: analyze -> filter -> rank -> signal."""

    def __init__(
        self,
        analyzer: Analyzer,
        universe: Iterable[str] | None = None,
        enrich: Callable[[str, dict], dict] | None = None,
        price_service=None,
        no_prices: bool = False,
        workers: int = 1,
    ):
        """``analyzer`` must return the analysis dict (or None when no data).

        ``universe`` provides tickers to screen; ``enrich`` may attach
        extra fields (e.g. sector / industry) to each result.

        ``price_service`` (PriceService) enriches every screened company with
        real-time valuation metrics (price, market cap, P/E, FCF yield,
        EV/EBIT) fetched only for the tickers in the current screen — never
        persisted. Pass ``no_prices=True`` to skip that entirely.

        ``workers`` > 1 runs the per-ticker analysis+enrichment step of the
        screen in a bounded thread pool (results keep their input order). The
        default of 1 preserves the historical sequential behavior. Workers
        must be safe for the injected analyzer/repository (the
        FinancialDatabaseRepository opens one PostgreSQL connection per
        thread).
        """
        self._analyzer = analyzer
        self._universe = list(universe) if universe is not None else None
        self._enrich = enrich
        self._price_service = price_service
        self._no_prices = no_prices
        self._workers = max(1, int(workers or 1))

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
    def _process(self, ticker: str, criteria: ScreenCriteria) -> dict | None:
        """Analyze, enrich, and filter one ticker; None when it fails or
        does not match the criteria."""
        result = self._analyzer(ticker)
        if result is None:
            return None
        result["ticker"] = result.get("ticker", ticker.upper())
        if self._enrich is not None:
            result = self._enrich(ticker, result)
        if not self._no_prices:
            self._enrich_realtime_price(ticker, result)
        if not matches(result, criteria):
            return None
        return result

    def _collect(self, criteria: ScreenCriteria) -> list[dict]:
        from concurrent.futures import ThreadPoolExecutor

        tickers = criteria.tickers or (self._universe or [])
        if self._workers > 1:
            with ThreadPoolExecutor(max_workers=self._workers) as pool:
                return [
                    item
                    for item in pool.map(
                        lambda t: self._process(t, criteria), tickers
                    )
                    if item is not None
                ]
        items: list[dict] = []
        for ticker in tickers:
            item = self._process(ticker, criteria)
            if item is not None:
                items.append(item)
        return items

    def _enrich_realtime_price(self, ticker: str, item: dict) -> None:
        """Attach real-time valuation metrics fetched only for this ticker.

        Prices come from PriceService (never persisted). Price-dependent
        metrics keep their analyzer values when present and are otherwise
        computed from the live price + fundamentals. On any failure the item
        keeps its original metrics and price-dependent values stay None, so
        the company still appears in the screen when it passes the other
        filters.
        """
        try:
            price = self._price_service.get_current_price(ticker)
            if price is None:
                item["price_metrics"] = {}
                return
            shares = item.get("shares_outstanding")
            if not shares:
                shares = self._price_service.get_shares_outstanding(ticker)
            market_cap = (
                price * float(shares) if shares else item.get("market_cap")
            )
            metrics: dict = {"price": price, "market_cap": market_cap}

            per = item.get("per")
            if per is None and market_cap:
                net_income = item.get("net_income")
                if net_income:
                    per = market_cap / net_income
            metrics["per"] = per

            fcf_yield = item.get("fcf_yield")
            if fcf_yield is None and market_cap:
                fcf = item.get("fcf")
                if fcf is not None:
                    fcf_yield = fcf / market_cap
            metrics["fcf_yield"] = fcf_yield

            ev_ebit = item.get("ev_ebit")
            if ev_ebit is None and market_cap:
                ebit = item.get("ebit")
                if ebit:
                    debt = item.get("total_debt") or 0
                    cash = item.get("cash_and_equivalents") or 0
                    ev_ebit = (market_cap + debt - cash) / ebit
            metrics["ev_ebit"] = ev_ebit

            item["price_metrics"] = metrics
        except Exception:
            item["price_metrics"] = {}

    def _screen(self, criteria: ScreenCriteria) -> list[ScreenedCompany]:
        items = self._collect(criteria)
        # Calibrate ranks across the analyzed (post-filter) universe so the
        # final scores spread across the 10-90 band and reflect relative
        # quality instead of absolute component compression.
        pool_scores = {id(it): calibrated_rank(it, items) for it in items}
        ranked = sorted(items, key=lambda it: pool_scores[id(it)], reverse=True)
        companies: list[ScreenedCompany] = []
        for position, item in enumerate(ranked, start=1):
            score = pool_scores[id(item)]
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
                    metrics=item.get("price_metrics"),
                )
            )
        return companies
