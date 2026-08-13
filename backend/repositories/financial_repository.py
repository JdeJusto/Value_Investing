"""SQLAlchemy implementation of the financial repository (PostgreSQL)."""

from __future__ import annotations

from typing import Callable, Optional

import sqlalchemy as sa
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.adapters.database.base import SessionLocal
from backend.adapters.database.models.normalized import (
    METRIC_COLUMNS,
    NormalizedFinancialModel,
)
from backend.domain.interfaces.financial_repository import FinancialRepository
from backend.domain.value_objects.financials_normalized import (
    ANNUAL_PERIOD,
    NormalizedFinancials,
    ProviderName,
)


class SqlAlchemyFinancialRepository(FinancialRepository):
    """Persists normalized financials in a relational database.

    One row per (ticker, fiscal_year, period); re-saving a year overwrites
    the stored values (upsert semantics).
    """

    def __init__(self, session_factory: Callable[[], Session] = SessionLocal):
        self._session_factory = session_factory

    def available(self) -> bool:
        """True when the backing database is reachable and the table exists."""
        try:
            with self._session_factory() as session:
                return sa.inspect(session.bind).has_table(
                    NormalizedFinancialModel.__tablename__
                )
        except sa.exc.SQLAlchemyError:
            return False

    # ------------------------------------------------------------------
    def upsert(self, financials: NormalizedFinancials) -> None:
        with self._session_factory() as session:
            model = self._find(
                session, financials.ticker, financials.fiscal_year, financials.period
            )
            if model is None:
                model = NormalizedFinancialModel(
                    ticker=financials.ticker,
                    fiscal_year=financials.fiscal_year,
                    period=financials.period or ANNUAL_PERIOD,
                )
                session.add(model)
            self._apply(model, financials)
            session.commit()

    def upsert_many(self, financials: list[NormalizedFinancials]) -> None:
        if not financials:
            return
        with self._session_factory() as session:
            ticker = financials[0].ticker
            existing = {
                (m.fiscal_year, m.period): m
                for m in session.execute(
                    select(NormalizedFinancialModel).where(
                        NormalizedFinancialModel.ticker == ticker
                    )
                ).scalars()
            }
            for item in financials:
                model = existing.get((item.fiscal_year, item.period or ANNUAL_PERIOD))
                if model is None:
                    model = NormalizedFinancialModel(
                        ticker=item.ticker,
                        fiscal_year=item.fiscal_year,
                        period=item.period or ANNUAL_PERIOD,
                    )
                    session.add(model)
                self._apply(model, item)
            session.commit()

    def get_by_year(
        self, ticker: str, fiscal_year: int
    ) -> Optional[NormalizedFinancials]:
        with self._session_factory() as session:
            model = session.execute(
                select(NormalizedFinancialModel).where(
                    NormalizedFinancialModel.ticker == ticker.upper(),
                    NormalizedFinancialModel.fiscal_year == fiscal_year,
                )
            ).scalar_one_or_none()
            return self._to_entity(model) if model else None

    def list_years(self, ticker: str) -> list[NormalizedFinancials]:
        with self._session_factory() as session:
            models = session.execute(
                select(NormalizedFinancialModel)
                .where(NormalizedFinancialModel.ticker == ticker.upper())
                .order_by(NormalizedFinancialModel.fiscal_year.desc())
            ).scalars()
            return [self._to_entity(m) for m in models]

    def has_data(self, ticker: str) -> bool:
        with self._session_factory() as session:
            count = session.execute(
                select(func.count())
                .select_from(NormalizedFinancialModel)
                .where(NormalizedFinancialModel.ticker == ticker.upper())
            ).scalar()
            return bool(count)

    def delete_ticker(self, ticker: str) -> None:
        with self._session_factory() as session:
            session.execute(
                delete(NormalizedFinancialModel).where(
                    NormalizedFinancialModel.ticker == ticker.upper()
                )
            )
            session.commit()

    # ------------------------------------------------------------------
    @staticmethod
    def _find(session: Session, ticker: str, fiscal_year: int, period: str):
        return session.execute(
            select(NormalizedFinancialModel).where(
                NormalizedFinancialModel.ticker == ticker.upper(),
                NormalizedFinancialModel.fiscal_year == fiscal_year,
                NormalizedFinancialModel.period == (period or ANNUAL_PERIOD),
            )
        ).scalar_one_or_none()

    @staticmethod
    def _apply(
        model: NormalizedFinancialModel, financials: NormalizedFinancials
    ) -> None:
        model.currency = financials.currency or "USD"
        model.source = (
            financials.source.value
            if isinstance(financials.source, ProviderName)
            else str(financials.source)
        )
        model.shares_outstanding = financials.shares_outstanding
        model.loaded_at = financials.loaded_at
        for column in METRIC_COLUMNS:
            setattr(model, column, getattr(financials, column, None))

    @staticmethod
    def _to_entity(model: NormalizedFinancialModel) -> NormalizedFinancials:
        return NormalizedFinancials(
            ticker=model.ticker,
            fiscal_year=model.fiscal_year,
            period=model.period,
            currency=model.currency,
            source=ProviderName(model.source),
            shares_outstanding=model.shares_outstanding,
            loaded_at=model.loaded_at,
            **{column: getattr(model, column) for column in METRIC_COLUMNS},
        )
