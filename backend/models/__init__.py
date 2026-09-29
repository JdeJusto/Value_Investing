import uuid
from datetime import UTC, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.core.database import Base


def utcnow():
    return datetime.now(UTC)


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    portfolios = relationship(
        "PortfolioModel", back_populates="user", cascade="all, delete-orphan"
    )
    watchlists = relationship(
        "WatchlistModel", back_populates="user", cascade="all, delete-orphan"
    )
    alerts = relationship(
        "AlertModel", back_populates="user", cascade="all, delete-orphan"
    )
    screener_jobs = relationship(
        "ScreenerJobModel", back_populates="user", cascade="all, delete-orphan"
    )


class CompanyModel(Base):
    __tablename__ = "companies"

    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255))
    sector: Mapped[str | None] = mapped_column(String(100))
    industry: Mapped[str | None] = mapped_column(String(100))
    exchange: Mapped[str | None] = mapped_column(String(50))
    country: Mapped[str] = mapped_column(String(50), default="US")
    market_cap: Mapped[float | None] = mapped_column(Float)
    enterprise_value: Mapped[float | None] = mapped_column(Float)
    beta: Mapped[float | None] = mapped_column(Float)
    price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    data_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FinancialDataModel(Base):
    __tablename__ = "financial_data"
    __table_args__ = (
        UniqueConstraint("ticker", "fiscal_year", "fiscal_period", "statement_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("companies.ticker", ondelete="CASCADE"), nullable=False
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_period: Mapped[str | None] = mapped_column(String(10))
    statement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="yahoo")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AnalysisCacheModel(Base):
    __tablename__ = "analysis_cache"

    ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("companies.ticker", ondelete="CASCADE"), primary_key=True
    )
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_provider: Mapped[str | None] = mapped_column(String(50))
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScreenerJobModel(Base):
    __tablename__ = "screener_jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tickers: Mapped[dict | None] = mapped_column(JSON)
    filters: Mapped[dict | None] = mapped_column(JSON)
    top_n: Mapped[int] = mapped_column(Integer, default=25)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    results: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("UserModel", back_populates="screener_jobs")


class PortfolioModel(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("UserModel", back_populates="portfolios")
    items = relationship(
        "PortfolioItemModel", back_populates="portfolio", cascade="all, delete-orphan"
    )


class PortfolioItemModel(Base):
    __tablename__ = "portfolio_items"
    __table_args__ = (UniqueConstraint("portfolio_id", "ticker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("companies.ticker", ondelete="CASCADE"), nullable=False
    )
    shares: Mapped[float] = mapped_column(Float, default=0)
    avg_cost: Mapped[float | None] = mapped_column(Float)
    added_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    notes: Mapped[str | None] = mapped_column(Text)

    portfolio = relationship("PortfolioModel", back_populates="items")


class WatchlistModel(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user = relationship("UserModel", back_populates="watchlists")
    items = relationship(
        "WatchlistItemModel", back_populates="watchlist", cascade="all, delete-orphan"
    )


class WatchlistItemModel(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "ticker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watchlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("companies.ticker", ondelete="CASCADE"), nullable=False
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    watchlist = relationship("WatchlistModel", back_populates="items")


class AlertModel(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("companies.ticker", ondelete="CASCADE"), nullable=False
    )
    metric_name: Mapped[str] = mapped_column(String(50), nullable=False)
    operator: Mapped[str] = mapped_column(String(5), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_push: Mapped[bool] = mapped_column(Boolean, default=False)
    last_triggered: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user = relationship("UserModel", back_populates="alerts")
