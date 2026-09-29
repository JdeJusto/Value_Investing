"""SQLAlchemy implementation of the financial repository (PostgreSQL).

Supports multiple providers per (ticker, fiscal_year, period): one row per
source, upserted individually. Source selection is delegated to
``get_best_available`` which prefers consistent, high-quality sources.
"""

from __future__ import annotations

from typing import Optional
from collections.abc import Callable

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
from backend.repositories.source_selection import best_of, best_per_year, choose_history


def _py_scalar(value):
    """Convert numpy scalars (np.float64, np.int64) to Python natives.

    psycopg2 renders numpy 2.x scalars as ``np.float64(...)`` which is
    not valid SQL; normalizers produce them from pandas.
    """
    if value is None or type(value).__module__ == "builtins":
        return value
    return value.item() if hasattr(value, "item") else value


class SqlAlchemyFinancialRepository(FinancialRepository):
    """Persists normalized financials in a relational database.

    One row per (ticker, fiscal_year, period, source); re-saving a
    source-year overwrites the stored values (upsert semantics).
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
                session,
                financials.ticker,
                financials.fiscal_year,
                financials.period,
                financials.source,
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
                (m.fiscal_year, m.period, m.source): m
                for m in session.execute(
                    select(NormalizedFinancialModel).where(
                        NormalizedFinancialModel.ticker == ticker
                    )
                ).scalars()
            }
            for item in financials:
                key = (
                    item.fiscal_year,
                    item.period or ANNUAL_PERIOD,
                    (
                        item.source.value
                        if isinstance(item.source, ProviderName)
                        else str(item.source)
                    ),
                )
                model = existing.get(key)
                if model is None:
                    model = NormalizedFinancialModel(
                        ticker=item.ticker,
                        fiscal_year=item.fiscal_year,
                        period=item.period or ANNUAL_PERIOD,
                    )
                    session.add(model)
                    existing[key] = model
                self._apply(model, item)
            session.commit()

    def get_by_year(
        self, ticker: str, fiscal_year: int
    ) -> NormalizedFinancials | None:
        """Best available record for a year (highest priority, then quality)."""
        with self._session_factory() as session:
            models = session.execute(
                select(NormalizedFinancialModel).where(
                    NormalizedFinancialModel.ticker == ticker.upper(),
                    NormalizedFinancialModel.fiscal_year == fiscal_year,
                )
            ).scalars()
            records = [self._to_entity(m) for m in models]
        if not records:
            return None
        return best_of(records)

    def list_years(self, ticker: str) -> list[NormalizedFinancials]:
        """Best available record per year, most recent first."""
        with self._session_factory() as session:
            models = session.execute(
                select(NormalizedFinancialModel)
                .where(NormalizedFinancialModel.ticker == ticker.upper())
                .order_by(NormalizedFinancialModel.fiscal_year.desc())
            ).scalars()
            records = [self._to_entity(m) for m in models]
        return best_per_year(records)

    def list_all(self, ticker: str) -> list[NormalizedFinancials]:
        """Every stored record across sources, year desc then quality desc."""
        with self._session_factory() as session:
            models = session.execute(
                select(NormalizedFinancialModel)
                .where(NormalizedFinancialModel.ticker == ticker.upper())
                .order_by(
                    NormalizedFinancialModel.fiscal_year.desc(),
                    NormalizedFinancialModel.data_source_priority.desc(),
                    NormalizedFinancialModel.data_quality_score.desc(),
                )
            ).scalars()
            return [self._to_entity(m) for m in models]

    def get_best_available(self, ticker: str) -> list[NormalizedFinancials]:
        """Select the best consistent history for a company.

        A single source is used whenever it covers at least
        FULL_COVERAGE_THRESHOLD of the stored years (preferred by source
        priority, then coverage, then mean quality). Otherwise the best
        record per year is blended (the consumer can flag this as MIXED).
        """
        rows = self.list_all(ticker)
        if not rows:
            return []
        return choose_history(rows)

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

    # FinancialRepository interface extensions for historical data (not implemented in SQL repo)
    def get_shares_outstanding(self, ticker: str, fiscal_year: int) -> float | None:
        """Get shares outstanding from normalized financials for the given year."""
        record = self.get_by_year(ticker, fiscal_year)
        if record and record.shares_outstanding is not None:
            return float(record.shares_outstanding)
        return None

    # ------------------------------------------------------------------
    @staticmethod
    def _find(session: Session, ticker: str, fiscal_year: int, period: str, source):
        return session.execute(
            select(NormalizedFinancialModel).where(
                NormalizedFinancialModel.ticker == ticker.upper(),
                NormalizedFinancialModel.fiscal_year == fiscal_year,
                NormalizedFinancialModel.period == (period or ANNUAL_PERIOD),
                NormalizedFinancialModel.source
                == (source.value if isinstance(source, ProviderName) else str(source)),
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
        model.shares_outstanding = _py_scalar(financials.shares_outstanding)
        model.loaded_at = financials.loaded_at
        model.data_quality_score = _py_scalar(financials.data_quality_score)
        model.data_completeness = _py_scalar(financials.data_completeness)
        model.is_complete = financials.is_complete
        model.data_source_priority = _py_scalar(financials.data_source_priority)
        model.derived_metrics = list(financials.derived_metrics) or None
        for column in METRIC_COLUMNS:
            value = getattr(financials, column, None)
            setattr(model, column, _py_scalar(value))

    @staticmethod
    def _py_scalar(value):
        """Convert numpy scalars (np.float64, np.int64) to Python natives.

        psycopg2 renders numpy 2.x scalars as ``np.float64(...)`` which is
        not valid SQL; normalizers produce them from pandas.
        """

        def _to_py(v):
            if v is None or type(v).__module__ == "builtins":
                return v
            return v.item() if hasattr(v, "item") else v

        return _to_py(value)

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
            data_quality_score=model.data_quality_score,
            data_completeness=model.data_completeness,
            is_complete=model.is_complete,
            data_source_priority=model.data_source_priority,
            derived_metrics=(
                list(model.derived_metrics) if model.derived_metrics else []
            ),
            **{column: getattr(model, column) for column in METRIC_COLUMNS},
        )
