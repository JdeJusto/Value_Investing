from dataclasses import dataclass
from typing import Optional


@dataclass
class IncomeStatement:
    revenue: Optional[float] = None
    cogs: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    ebit: Optional[float] = None
    ebitda: Optional[float] = None
    net_income: Optional[float] = None
    interest_expense: Optional[float] = None
    tax_provision: Optional[float] = None
    pretax_income: Optional[float] = None
    effective_tax_rate: Optional[float] = None


@dataclass
class BalanceSheet:
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_debt: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    working_capital: Optional[float] = None
    retained_earnings: Optional[float] = None
    stockholders_equity: Optional[float] = None


@dataclass
class CashFlowStatement:
    operating_cash_flow: Optional[float] = None
    capital_expenditure: Optional[float] = None
    free_cash_flow: Optional[float] = None
    depreciation_amortization: Optional[float] = None
    dividends_paid: Optional[float] = None
    repurchase_of_stock: Optional[float] = None
    working_capital_change: Optional[float] = None


@dataclass
class FinancialStatement:
    income: Optional[IncomeStatement] = None
    balance: Optional[BalanceSheet] = None
    cash_flow: Optional[CashFlowStatement] = None
    year: Optional[int] = None
