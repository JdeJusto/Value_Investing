import asyncio
from typing import Optional

from backend.domain.value_objects.filter_criteria import FilterCriteria, FilterOperator
from backend.domain.value_objects.screener_result import ScreenerRow
from backend.providers.cache.memory import MemoryCache
from backend.providers.edgar import EdgarProvider
from backend.providers.tickers import TICKERS
from backend.providers.yahoo import YahooFinanceProvider
from backend.services.screener_service import StockScreenerService
from backend.tasks import celery_app

_cached_service = None
_cache = MemoryCache()


def _get_screener_service() -> StockScreenerService:
    from backend.core.config import SEC_EMAIL, SEC_NAME
    return StockScreenerService(
        financial_providers=[
            YahooFinanceProvider(),
            EdgarProvider(email=SEC_EMAIL, name=SEC_NAME),
        ],
        market_provider=YahooFinanceProvider(),
    )


@celery_app.task(bind=True)
def run_screener_task(
    self,
    tickers: Optional[list[str]] = None,
    filters: Optional[list[dict]] = None,
    top_n: int = 25,
    job_id: str = "",
):
    from backend.api.deps import async_session_factory

    if tickers is None:
        tickers = TICKERS

    filter_criteria = []
    if filters:
        for f in filters:
            try:
                op = FilterOperator(f["operator"])
            except ValueError:
                continue
            filter_criteria.append(FilterCriteria(field=f["field"], operator=op, value=f.get("value")))

    service = _get_screener_service()
    total = len(tickers)

    results = []

    for idx, ticker in enumerate(tickers):
        self.update_state(state="PROGRESS", meta={"progress": idx / total, "current": ticker})

        cache_key = f"screener_analysis:{ticker}"
        cached = _cache.get(cache_key)

        if cached:
            row = ScreenerRow(**cached)
        else:
            try:
                analysis = service._analyze_ticker(ticker)
                if analysis and service._passes_filters(analysis, filter_criteria):
                    row_data = {
                        "ticker": analysis.ticker,
                        "name": analysis.name,
                        "price": analysis.price,
                        "market_cap": analysis.market_cap,
                        "per": analysis.per,
                        "pb": analysis.pb,
                        "roe": analysis.roe,
                        "roic": analysis.roic,
                        "fcf_yield": analysis.fcf_yield,
                        "ev_ebit": analysis.ev_ebit,
                        "debt_to_equity": analysis.debt_to_equity,
                        "score": analysis.score,
                        "extra": analysis.extra,
                    }
                    _cache.set(cache_key, row_data, ttl=3600)
                    row = analysis
                else:
                    row = None
            except Exception:
                row = None

        if row is not None:
            results.append(row)

    results.sort(key=lambda r: r.score or 0, reverse=True)

    if top_n:
        results = results[:top_n]

    serializable = [
        {
            "ticker": r.ticker,
            "name": r.name,
            "price": r.price,
            "market_cap": r.market_cap,
            "per": r.per,
            "pb": r.pb,
            "roe": r.roe,
            "roic": r.roic,
            "fcf_yield": r.fcf_yield,
            "ev_ebit": r.ev_ebit,
            "debt_to_equity": r.debt_to_equity,
            "score": r.score,
            "extra": r.extra,
        }
        for r in results
    ]

    return {"results": serializable, "count": len(serializable)}
