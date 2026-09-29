"""Watchlist service: tracks monitoring items and enriches them.

The analyzer is the analytics-layer entry point; the service never
touches providers directly. Exports are plain CSV-ready dicts.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from backend.screener.opportunity_engine import best_opportunity
from backend.screener.ranking_engine import rank_score
from backend.screener.signals import detect_trigger, generate_signal
from backend.watchlist.models import (
    MONITORING,
    STATUSES,
    Watchlist,
    WatchlistItem,
)
from backend.watchlist.watchlist_repository import WatchlistRepository

Analyzer = Callable[[str], dict | None]


class WatchlistService:
    def __init__(
        self,
        repository: WatchlistRepository,
        analyzer: Analyzer | None = None,
    ):
        self._repository = repository
        self._analyzer = analyzer

    # ------------------------------------------------------------------
    def add(self, ticker: str, note: str = "") -> WatchlistItem:
        watchlist = self._load()
        t = ticker.upper().strip()
        item = WatchlistItem(ticker=t, note=note, added_at=datetime.now(UTC))
        watchlist.add(item)
        self._save(watchlist)
        return item

    def remove(self, ticker: str) -> WatchlistItem | None:
        watchlist = self._load()
        removed = watchlist.remove(ticker)
        if removed is not None:
            self._save(watchlist)
        return removed

    def set_status(self, ticker: str, status: str) -> WatchlistItem | None:
        if status not in STATUSES:
            raise ValueError(f"unknown watchlist status '{status}'")
        watchlist = self._load()
        item = watchlist.set_status(ticker, status)
        if item is not None:
            self._save(watchlist)
        return item

    # ------------------------------------------------------------------
    def items(self) -> list[WatchlistItem]:
        return self._load().items

    def list_view(self) -> list[dict]:
        """Items enriched with scores, signal, trigger and opportunity."""
        enriched: list[dict] = []
        for item in self._load().items:
            analysis = self._analysis_for(item.ticker)
            enriched.append(
                {
                    "ticker": item.ticker,
                    "status": item.status,
                    "added_at": item.added_at.isoformat(),
                    "note": item.note,
                    **analysis,
                }
            )
        return enriched

    def export_rows(self, only_monitoring: bool = False) -> list[dict]:
        """CSV-ready rows for the current analysis of every item."""
        rows: list[dict] = []
        for item in self._load().items:
            if only_monitoring and item.status != MONITORING:
                continue
            analysis = self._analysis_for(item.ticker)
            deltas = analysis.get("delta_metrics") or {}
            rows.append(
                {
                    "ticker": item.ticker,
                    "status": item.status,
                    "note": item.note,
                    "buffett_score": analysis.get("buffett_score"),
                    "moat": analysis.get("moat"),
                    "total_score": (analysis.get("composite_score") or {}).get(
                        "total_score"
                    ),
                    "rating": (analysis.get("composite_score") or {}).get("rating"),
                    "confidence": (analysis.get("composite_score") or {}).get(
                        "confidence"
                    ),
                    "rank": analysis.get("rank"),
                    "signal": analysis.get("signal"),
                    "trigger": analysis.get("trigger"),
                    "opportunity": analysis.get("opportunity_type"),
                    "current_price": analysis.get("current_price"),
                    "revenue_growth_delta": deltas.get("revenue_growth_delta"),
                    "gross_margin_delta": deltas.get("gross_margin_delta"),
                    "roic_delta": deltas.get("roic_delta"),
                    "fcf_delta": deltas.get("fcf_delta"),
                }
            )
        return rows

    # ------------------------------------------------------------------
    def _load(self) -> Watchlist:
        return self._repository.load()

    def _save(self, watchlist: Watchlist) -> None:
        self._repository.save(watchlist)

    def _analysis_for(self, ticker: str) -> dict:
        empty = {
            "buffett_score": None,
            "moat": None,
            "composite_score": None,
            "rank": None,
            "signal": None,
            "trigger": None,
            "opportunity_type": None,
            "current_price": None,
            "delta_metrics": None,
        }
        if self._analyzer is None:
            return empty
        try:
            result = self._analyzer(ticker)
        except Exception:  # noqa: BLE001 — analysis must not break the watchlist
            result = None
        if not result:
            return empty
        opportunity = best_opportunity(result)
        signal = generate_signal(
            dict(result, opportunity=opportunity), rank_score(result)
        )
        return {
            "buffett_score": result.get("buffett_score"),
            "moat": (result.get("moat_analysis") or {}).get("moat_type"),
            "composite_score": result.get("composite_score"),
            "rank": round(rank_score(result), 2),
            "signal": signal["signal"],
            "trigger": detect_trigger(result),
            "opportunity_type": opportunity["type"] if opportunity else None,
            "current_price": result.get("current_price"),
            "delta_metrics": result.get("delta_metrics"),
        }
