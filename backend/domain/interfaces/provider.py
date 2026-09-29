from abc import ABC, abstractmethod

from backend.domain.entities.financials import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
)


class FinancialDataProvider(ABC):
    @abstractmethod
    def get_income_statement(
        self, ticker: str, year_index: int = 0
    ) -> IncomeStatement | None: ...

    @abstractmethod
    def get_balance_sheet(
        self, ticker: str, year_index: int = 0
    ) -> BalanceSheet | None: ...

    @abstractmethod
    def get_cash_flow(
        self, ticker: str, year_index: int = 0
    ) -> CashFlowStatement | None: ...


class MarketDataProvider(ABC):
    @abstractmethod
    def get_company_name(self, ticker: str) -> str | None: ...

    @abstractmethod
    def get_market_cap(self, ticker: str) -> float | None: ...

    @abstractmethod
    def get_enterprise_value(self, ticker: str) -> float | None: ...

    @abstractmethod
    def get_current_price(self, ticker: str) -> float | None: ...

    @abstractmethod
    def get_beta(self, ticker: str) -> float | None: ...

    @abstractmethod
    def get_shares_outstanding(self, ticker: str) -> int | None: ...
