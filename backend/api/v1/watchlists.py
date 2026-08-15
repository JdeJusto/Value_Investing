from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.deps import get_current_active_user, get_db
from backend.models import UserModel, WatchlistItemModel, WatchlistModel
from backend.schemas import WatchlistCreate, WatchlistResponse

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


@router.get("", response_model=list[WatchlistResponse])
async def list_watchlists(
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    result = await db.execute(
        select(WatchlistModel)
        .where(WatchlistModel.user_id == user.id)
        .options(selectinload(WatchlistModel.items))
        .order_by(WatchlistModel.created_at.desc())
    )
    watchlists = result.scalars().all()
    return [
        WatchlistResponse(
            id=w.id,
            name=w.name,
            created_at=w.created_at,
            ticker_count=len(w.items),
            items=[{"id": i.id, "ticker": i.ticker} for i in w.items],
        )
        for w in watchlists
    ]


@router.post("", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED)
async def create_watchlist(
    body: WatchlistCreate,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    watchlist = WatchlistModel(user_id=user.id, name=body.name)
    db.add(watchlist)
    await db.flush()

    for ticker in body.tickers:
        item = WatchlistItemModel(watchlist_id=watchlist.id, ticker=ticker.upper())
        db.add(item)
    await db.flush()

    return WatchlistResponse(
        id=watchlist.id,
        name=watchlist.name,
        created_at=watchlist.created_at,
        ticker_count=len(body.tickers),
        items=[{"id": item.id, "ticker": item.ticker} for item in watchlist.items],
    )


@router.get("/{watchlist_id}", response_model=WatchlistResponse)
async def get_watchlist(
    watchlist_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    result = await db.execute(
        select(WatchlistModel)
        .where(WatchlistModel.id == watchlist_id, WatchlistModel.user_id == user.id)
        .options(selectinload(WatchlistModel.items))
    )
    watchlist = result.scalar_one_or_none()
    if watchlist is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return WatchlistResponse(
        id=watchlist.id,
        name=watchlist.name,
        created_at=watchlist.created_at,
        ticker_count=len(watchlist.items),
        items=[{"id": i.id, "ticker": i.ticker} for i in watchlist.items],
    )


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(
    watchlist_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_active_user),
):
    result = await db.execute(
        select(WatchlistModel).where(
            WatchlistModel.id == watchlist_id, WatchlistModel.user_id == user.id
        )
    )
    watchlist = result.scalar_one_or_none()
    if watchlist is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    await db.delete(watchlist)
