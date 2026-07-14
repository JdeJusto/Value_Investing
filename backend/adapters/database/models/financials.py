from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB

from backend.adapters.database.base import Base


class FinancialStatementModel(Base):
    __tablename__ = "financial_statements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), ForeignKey("companies.ticker", ondelete="CASCADE"), nullable=False, index=True)
    fiscal_year = Column(Integer, nullable=False)
    fiscal_period = Column(String(10))
    statement_type = Column(String(20), nullable=False)
    data = Column(JSONB)
    source = Column(String(50))
    created_at = Column(DateTime, server_default=func.now())


class AnalysisResultModel(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), ForeignKey("companies.ticker", ondelete="CASCADE"), nullable=False, index=True)
    metric_name = Column(String(50), nullable=False)
    metric_value = Column(Float)
    fiscal_year = Column(Integer)
    params = Column(JSONB)
    calculated_at = Column(DateTime, server_default=func.now())
