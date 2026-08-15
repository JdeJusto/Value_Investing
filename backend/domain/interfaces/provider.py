from abc import ABC, abstractmethod
from typing import Optional

from backend.domain.entities.financials import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
)


class FinancialDataProvider(ABC):
    @abstractmethod
    def get_income_statement(
        self, ticker: str, year_index: int = 0
    ) -> Optional[IncomeStatement]: ...

    @abstractmethod
    def get_balance_sheet(
        self, ticker: str, year_index: int = 0
    ) -> Optional[BalanceSheet]: ...

    @abstractmethod
    def get_cash_flow(
        self, ticker: str, year_index: int = 0
    ) -> Optional[CashFlowStatement]: ...


class MarketDataProvider(ABC):
    @abstractmethod
    def get_company_name(self, ticker: str) -> Optional[str]: ...

    @abstractmethod
    def get_market_cap(self, ticker: str) -> Optional[float]: ...

    @abstractmethod
    def get_enterprise_value(self, ticker: str) -> Optional[float]: ...

    @abstractmethod
    def get_current_price(self, ticker: str) -> Optional[float]: ...

    @abstractmethod
    def get_beta(self, ticker: str) -> Optional[float]: ...

    @abstractmethod
    def get_shares_outstanding(self, ticker: str) -> Optional[int]: ...
