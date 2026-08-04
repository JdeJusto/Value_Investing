from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_active_user, get_db
from backend.models import AlertModel, UserModel
from backend.schemas import AlertCreate, AlertResponse

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    result = await db.execute(
        select(AlertModel).where(AlertModel.user_id == user.id).order_by(AlertModel.created_at.desc())
    )
    return [AlertResponse.model_validate(a) for a in result.scalars().all()]


@router.post("", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    body: AlertCreate,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    alert = AlertModel(
        user_id=user.id,
        ticker=body.ticker.upper(),
        metric_name=body.metric_name,
        operator=body.operator,
        threshold=body.threshold,
        notify_email=body.notify_email,
        notify_push=body.notify_push,
    )
    db.add(alert)
    await db.flush()
    return AlertResponse.model_validate(alert)


@router.put("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: int,
    body: AlertCreate,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    result = await db.execute(
        select(AlertModel).where(AlertModel.id == alert_id, AlertModel.user_id == user.id)
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.ticker = body.ticker.upper()
    alert.metric_name = body.metric_name
    alert.operator = body.operator
    alert.threshold = body.threshold
    alert.notify_email = body.notify_email
    alert.notify_push = body.notify_push
    await db.flush()
    return AlertResponse.model_validate(alert)


@router.put("/{alert_id}/toggle", response_model=AlertResponse)
async def toggle_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    result = await db.execute(
        select(AlertModel).where(AlertModel.id == alert_id, AlertModel.user_id == user.id)
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_active = not alert.is_active
    await db.flush()
    return AlertResponse.model_validate(alert)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    result = await db.execute(
        select(AlertModel).where(AlertModel.id == alert_id, AlertModel.user_id == user.id)
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.delete(alert)
