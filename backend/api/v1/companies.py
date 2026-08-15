import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics.interpretation import (
    INTERPRETERS,
    METRICS_ORDER,
    format_metric_value,
)
from backend.analytics.service import CompanyAnalysisService
from backend.api.deps import get_current_active_user, get_db
from backend.app.cli import build_data_pipeline, build_financial_repository
from backend.core.config import ANALYSIS_CACHE_TTL
from backend.models import UserModel
from backend.providers.cache.memory import MemoryCache
from backend.providers.tickers import TICKERS
from backend.providers.yahoo import YahooFinanceProvider
from backend.schemas import (
    AnalysisResponse,
    CompanyResponse,
    CompanySearchResult,
    MetricInterpretation,
)

router = APIRouter(prefix="/companies", tags=["companies"])

_provider_cache = MemoryCache()
_yahoo = YahooFinanceProvider()


def _get_analysis_service() -> CompanyAnalysisService:
    return CompanyAnalysisService(
        repository=build_financial_repository(),
        market_provider=_yahoo,
        loader=build_data_pipeline(),
    )


async def _search_tickers(query: str, limit: int) -> list[CompanySearchResult]:
    def _run() -> list[CompanySearchResult]:
        q = query.lower()
        results: list[CompanySearchResult] = []
        for ticker in TICKERS:
            name = _yahoo.get_company_name(ticker)
            if q in ticker.lower() or (name and q in name.lower()):
                results.append(CompanySearchResult(ticker=ticker, name=name))
                if len(results) >= limit:
                    break
        return results

    return await asyncio.to_thread(_run)


@router.get("/search", response_model=list[CompanySearchResult])
async def search_companies(
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
):
    return await _search_tickers(q.lower(), limit)


@router.get("/{ticker}", response_model=CompanyResponse)
async def get_company(
    ticker: str,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    ticker = ticker.upper().strip()

    name = _yahoo.get_company_name(ticker)
    price = _yahoo.get_current_price(ticker)
    market_cap = _yahoo.get_market_cap(ticker)
    ev = _yahoo.get_enterprise_value(ticker)
    beta = _yahoo.get_beta(ticker)

    return CompanyResponse(
        ticker=ticker,
        name=name,
        price=price,
        market_cap=market_cap,
        enterprise_value=ev,
        beta=beta,
    )


@router.get("/{ticker}/analysis", response_model=AnalysisResponse)
async def get_company_analysis(
    ticker: str,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    ticker = ticker.upper().strip()

    cache_key = f"analysis:{ticker}"
    cached = _provider_cache.get(cache_key)
    if cached:
        return cached

    service = _get_analysis_service()
    result = service.analyze(ticker)

    if result is None:
        raise HTTPException(status_code=404, detail=f"No data available for {ticker}")

    name = _yahoo.get_company_name(ticker)
    price = _yahoo.get_current_price(ticker)
    ev = _yahoo.get_enterprise_value(ticker)

    metrics_dict: dict[str, MetricInterpretation] = {}
    for metric_key in METRICS_ORDER:
        val = result.get(metric_key)
        if val is not None:
            formatted = format_metric_value(val)
            interpret_fn = INTERPRETERS.get(metric_key)
            interpretation = interpret_fn(val) if interpret_fn else ""
            metrics_dict[metric_key] = MetricInterpretation(
                value=val,
                formatted=formatted,
                interpretation=interpretation,
            )

    response = AnalysisResponse(
        ticker=ticker,
        name=name,
        price=price,
        market_cap=result.get("market_cap"),
        enterprise_value=ev,
        score=result.get("score", 0.0),
        revenue=result.get("revenue"),
        net_income=result.get("net_income"),
        fcf=result.get("fcf"),
        metrics=metrics_dict,
    )

    _provider_cache.set(cache_key, response.model_dump(), ttl=ANALYSIS_CACHE_TTL)
    return response
