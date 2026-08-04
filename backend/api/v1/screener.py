import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics.interpretation import INTERPRETERS, METRICS_ORDER, format_metric_value
from backend.api.deps import get_current_active_user, get_db
from backend.core.config import SEC_EMAIL, SEC_NAME
from backend.domain.value_objects.filter_criteria import FilterCriteria, FilterOperator
from backend.models import ScreenerJobModel, UserModel
from backend.providers.cache.memory import MemoryCache
from backend.providers.edgar import EdgarProvider
from backend.providers.tickers import TICKERS
from backend.providers.yahoo import YahooFinanceProvider
from backend.schemas import (
    AnalysisResponse,
    FilterSchema,
    MetricInterpretation,
    ScreenerJobResponse,
    ScreenerJobStatus,
    ScreenerRequest,
)
from backend.services.screener_service import StockScreenerService

router = APIRouter(prefix="/screener", tags=["screener"])

_CACHE = MemoryCache()


def _get_screener_service() -> StockScreenerService:
    yahoo = YahooFinanceProvider()
    edgar = EdgarProvider(email=SEC_EMAIL, name=SEC_NAME)
    return StockScreenerService(
        financial_providers=[yahoo, edgar],
        market_provider=yahoo,
    )


def _filters_from_schema(schemas: list[FilterSchema]) -> list[FilterCriteria]:
    filters = []
    for s in schemas:
        try:
            op = FilterOperator(s.operator)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid operator: {s.operator}")
        filters.append(FilterCriteria(field=s.field, operator=op, value=s.value))
    return filters


@router.post("", response_model=ScreenerJobResponse)
async def run_screener(
    body: ScreenerRequest,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    job_id = str(uuid.uuid4())
    job = ScreenerJobModel(
        id=job_id,
        user_id=user.id,
        tickers=body.tickers if body.tickers else None,
        filters=[s.model_dump() for s in body.filters],
        top_n=body.top_n,
        status="pending",
    )
    db.add(job)
    await db.flush()

    service = _get_screener_service()
    filters = _filters_from_schema(body.filters)

    job.status = "running"
    await db.flush()

    try:
        tickers = body.tickers if body.tickers else TICKERS
        total = len(tickers)

        def progress_cb(current, total, ticker):
            pass

        results = await asyncio.to_thread(
            service.screen,
            tickers=tickers,
            filters=filters if filters else None,
            top_n=body.top_n,
            progress_callback=progress_cb,
        )

        serializable = []
        for r in results:
            serializable.append({
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
            })

        job.status = "completed"
        job.results = serializable
        job.progress = 1.0
        await db.flush()

    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        await db.flush()
        raise HTTPException(status_code=500, detail=str(e))

    return ScreenerJobResponse(job_id=job_id, status="completed")


@router.get("/{job_id}", response_model=ScreenerJobStatus)
async def get_screener_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    result = await db.execute(
        select(ScreenerJobModel).where(
            ScreenerJobModel.id == job_id,
            ScreenerJobModel.user_id == user.id,
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return ScreenerJobStatus(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        results=job.results,
        error_message=job.error_message,
    )
