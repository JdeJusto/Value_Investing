from typing import Optional

from sqlalchemy import select

from backend.adapters.database.base import get_session
from backend.adapters.database.models.company import CompanyModel
from backend.domain.entities.company import Company


class CompanyRepository:
    def save(self, company: Company) -> Company:
        with get_session() as session:
            stmt = select(CompanyModel).where(CompanyModel.ticker == company.ticker)
            existing = session.execute(stmt).scalar_one_or_none()
            if existing:
                existing.name = company.name
                existing.sector = company.sector
                existing.industry = company.industry
                existing.exchange = company.exchange
            else:
                model = CompanyModel(
                    ticker=company.ticker,
                    name=company.name,
                    sector=company.sector,
                    industry=company.industry,
                    exchange=company.exchange,
                )
                session.add(model)
            session.commit()
        return company

    def find_by_ticker(self, ticker: str) -> Optional[Company]:
        with get_session() as session:
            stmt = select(CompanyModel).where(CompanyModel.ticker == ticker.upper())
            model = session.execute(stmt).scalar_one_or_none()
            if model:
                return Company(
                    ticker=model.ticker,
                    name=model.name,
                    sector=model.sector,
                    industry=model.industry,
                    exchange=model.exchange,
                )
            return None
