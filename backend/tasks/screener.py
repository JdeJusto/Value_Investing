from dataclasses import asdict

from backend.domain.value_objects.filter_criteria import FilterCriteria, FilterOperator
from backend.domain.value_objects.screener_result import ScreenerRow
from backend.providers.cache.memory import MemoryCache
from backend.providers.tickers import TICKERS
from backend.services.screener_service import StockScreenerService
from backend.tasks import celery_app

_cached_service = None
_cache = MemoryCache()


def _get_screener_service() -> StockScreenerService:
    from backend.app.cli import build_data_pipeline, build_financial_repository
    from backend.providers.yahoo import YahooFinanceProvider

    return StockScreenerService(
        repository=build_financial_repository(),
        market_provider=YahooFinanceProvider(),
        loader=build_data_pipeline(),
    )


@celery_app.task(bind=True)
def run_screener_task(
    self,
    tickers: list[str] | None = None,
    filters: list[dict] | None = None,
    top_n: int = 25,
    job_id: str = "",
):

    if tickers is None:
        tickers = TICKERS

    filter_criteria = []
    if filters:
        for f in filters:
            try:
                op = FilterOperator(f["operator"])
            except ValueError:
                continue
            filter_criteria.append(
                FilterCriteria(field=f["field"], operator=op, value=f.get("value"))
            )

    service = _get_screener_service()
    total = len(tickers)

    results = []

    for idx, ticker in enumerate(tickers):
        self.update_state(
            state="PROGRESS", meta={"progress": idx / total, "current": ticker}
        )

        cache_key = f"screener_analysis:{ticker}"
        cached = _cache.get(cache_key)

        if cached:
            row = ScreenerRow(**cached)
        else:
            try:
                analysis = service._analyze_ticker(ticker)
                if analysis is not None:
                    row_data = asdict(analysis)
                    _cache.set(cache_key, row_data, ttl=3600)
                    row = analysis
                else:
                    row = None
            except Exception:
                row = None

        if row is None:
            continue
        if filter_criteria and not service._passes_filters(row, filter_criteria):
            continue
        results.append(row)

    results.sort(key=lambda r: r.score or 0, reverse=True)

    if top_n is not None:
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
