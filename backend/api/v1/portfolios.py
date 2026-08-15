from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.deps import get_current_active_user, get_db
from backend.models import PortfolioItemModel, PortfolioModel, UserModel
from backend.schemas import (
    PortfolioCreate,
    PortfolioItemCreate,
    PortfolioItemUpdate,
    PortfolioResponse,
    PortfolioUpdate,
)

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@router.get("", response_model=list[PortfolioResponse])
async def list_portfolios(
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    result = await db.execute(
        select(PortfolioModel)
        .where(PortfolioModel.user_id == user.id)
        .options(selectinload(PortfolioModel.items))
        .order_by(PortfolioModel.created_at.desc())
    )
    portfolios = result.scalars().all()
    return [
        PortfolioResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            is_public=p.is_public,
            created_at=p.created_at,
            updated_at=p.updated_at,
            ticker_count=len(p.items),
            items=[
                {
                    "id": i.id,
                    "ticker": i.ticker,
                    "shares": i.shares,
                    "avg_cost": i.avg_cost,
                    "notes": i.notes,
                }
                for i in p.items
            ],
        )
        for p in portfolios
    ]


@router.post("", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    body: PortfolioCreate,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    portfolio = PortfolioModel(
        user_id=user.id, name=body.name, description=body.description
    )
    db.add(portfolio)
    await db.flush()
    return PortfolioResponse(
        id=portfolio.id,
        name=portfolio.name,
        description=portfolio.description,
        is_public=portfolio.is_public,
        created_at=portfolio.created_at,
        updated_at=portfolio.updated_at,
        ticker_count=0,
        items=[],
    )


@router.get("/{portfolio_id}", response_model=PortfolioResponse)
async def get_portfolio(
    portfolio_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    result = await db.execute(
        select(PortfolioModel)
        .where(PortfolioModel.id == portfolio_id, PortfolioModel.user_id == user.id)
        .options(selectinload(PortfolioModel.items))
    )
    portfolio = result.scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return PortfolioResponse(
        id=portfolio.id,
        name=portfolio.name,
        description=portfolio.description,
        is_public=portfolio.is_public,
        created_at=portfolio.created_at,
        updated_at=portfolio.updated_at,
        ticker_count=len(portfolio.items),
        items=[
            {
                "id": i.id,
                "ticker": i.ticker,
                "shares": i.shares,
                "avg_cost": i.avg_cost,
                "notes": i.notes,
            }
            for i in portfolio.items
        ],
    )


@router.put("/{portfolio_id}", response_model=PortfolioResponse)
async def update_portfolio(
    portfolio_id: int,
    body: PortfolioUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    result = await db.execute(
        select(PortfolioModel)
        .where(PortfolioModel.id == portfolio_id, PortfolioModel.user_id == user.id)
        .options(selectinload(PortfolioModel.items))
    )
    portfolio = result.scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    if body.name is not None:
        portfolio.name = body.name
    if body.description is not None:
        portfolio.description = body.description
    if body.is_public is not None:
        portfolio.is_public = body.is_public
    await db.flush()
    return PortfolioResponse(
        id=portfolio.id,
        name=portfolio.name,
        description=portfolio.description,
        is_public=portfolio.is_public,
        created_at=portfolio.created_at,
        updated_at=portfolio.updated_at,
        ticker_count=len(portfolio.items),
        items=[
            {
                "id": i.id,
                "ticker": i.ticker,
                "shares": i.shares,
                "avg_cost": i.avg_cost,
                "notes": i.notes,
            }
            for i in portfolio.items
        ],
    )


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(
    portfolio_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    result = await db.execute(
        select(PortfolioModel).where(
            PortfolioModel.id == portfolio_id, PortfolioModel.user_id == user.id
        )
    )
    portfolio = result.scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    await db.delete(portfolio)


@router.post("/{portfolio_id}/items", status_code=status.HTTP_201_CREATED)
async def add_portfolio_item(
    portfolio_id: int,
    body: PortfolioItemCreate,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    result = await db.execute(
        select(PortfolioModel).where(
            PortfolioModel.id == portfolio_id, PortfolioModel.user_id == user.id
        )
    )
    portfolio = result.scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    item = PortfolioItemModel(
        portfolio_id=portfolio_id,
        ticker=body.ticker.upper(),
        shares=body.shares,
        avg_cost=body.avg_cost,
        notes=body.notes,
    )
    db.add(item)
    await db.flush()
    return {"id": item.id, "ticker": item.ticker}


@router.put("/{portfolio_id}/items/{item_id}")
async def update_portfolio_item(
    portfolio_id: int,
    item_id: int,
    body: PortfolioItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    result = await db.execute(
        select(PortfolioItemModel)
        .join(PortfolioModel, PortfolioModel.id == PortfolioItemModel.portfolio_id)
        .where(
            PortfolioItemModel.id == item_id,
            PortfolioItemModel.portfolio_id == portfolio_id,
            PortfolioModel.user_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    if body.shares is not None:
        item.shares = body.shares
    if body.avg_cost is not None:
        item.avg_cost = body.avg_cost
    if body.notes is not None:
        item.notes = body.notes
    await db.flush()
    return {"id": item.id, "ticker": item.ticker}


@router.delete(
    "/{portfolio_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_portfolio_item(
    portfolio_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    result = await db.execute(
        select(PortfolioItemModel)
        .join(PortfolioModel, PortfolioModel.id == PortfolioItemModel.portfolio_id)
        .where(
            PortfolioItemModel.id == item_id,
            PortfolioItemModel.portfolio_id == portfolio_id,
            PortfolioModel.user_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.delete(item)
