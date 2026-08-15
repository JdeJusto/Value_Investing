import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_active_user, get_db
from backend.app.cli import build_data_pipeline, build_financial_repository
from backend.domain.value_objects.filter_criteria import FilterCriteria, FilterOperator
from backend.models import ScreenerJobModel, UserModel
from backend.providers.cache.memory import MemoryCache
from backend.providers.tickers import TICKERS
from backend.providers.yahoo import YahooFinanceProvider
from backend.schemas import (
    FilterSchema,
    ScreenerJobResponse,
    ScreenerJobStatus,
    ScreenerRequest,
)
from backend.services.screener_service import StockScreenerService

router = APIRouter(prefix="/screener", tags=["screener"])

_CACHE = MemoryCache()


def _py_scalar(value):
    if isinstance(value, dict):
        return {k: _py_scalar(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_py_scalar(v) for v in value]
    if value is None or type(value).__module__ == "builtins":
        return value
    return value.item() if hasattr(value, "item") else value


def _get_screener_service() -> StockScreenerService:
    yahoo = YahooFinanceProvider()
    return StockScreenerService(
        repository=build_financial_repository(),
        market_provider=yahoo,
        loader=build_data_pipeline(),
    )


def _filters_from_schema(schemas: list[FilterSchema]) -> list[FilterCriteria]:
    filters = []
    for s in schemas:
        try:
            op = FilterOperator(s.operator)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid operator: {s.operator}"
            )
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
            serializable.append(
                {
                    "ticker": _py_scalar(r.ticker),
                    "name": _py_scalar(r.name),
                    "price": _py_scalar(r.price),
                    "market_cap": _py_scalar(r.market_cap),
                    "per": _py_scalar(r.per),
                    "pb": _py_scalar(r.pb),
                    "roe": _py_scalar(r.roe),
                    "roic": _py_scalar(r.roic),
                    "fcf_yield": _py_scalar(r.fcf_yield),
                    "ev_ebit": _py_scalar(r.ev_ebit),
                    "debt_to_equity": _py_scalar(r.debt_to_equity),
                    "score": _py_scalar(r.score),
                    "extra": _py_scalar(r.extra),
                }
            )

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
