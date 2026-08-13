from sqlalchemy import Column, DateTime, Float, String, func

from backend.adapters.database.base import Base


class CompanyModel(Base):
    __tablename__ = "companies"

    ticker = Column(String(10), primary_key=True)
    name = Column(String(255))
    sector = Column(String(100))
    industry = Column(String(100))
    exchange = Column(String(50))
    country = Column(String(50), server_default="US")
    market_cap = Column(Float)
    enterprise_value = Column(Float)
    beta = Column(Float)
    price = Column(Float)
    currency = Column(String(3), server_default="USD")
    data_updated_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
