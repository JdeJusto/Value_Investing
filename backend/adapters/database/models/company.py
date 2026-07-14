from sqlalchemy import Column, DateTime, Float, Integer, String, func

from backend.adapters.database.base import Base


class CompanyModel(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), unique=True, nullable=False, index=True)
    name = Column(String(255))
    sector = Column(String(100))
    industry = Column(String(100))
    exchange = Column(String(50))
    market_cap = Column(Float)
    enterprise_value = Column(Float)
    beta = Column(Float)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
