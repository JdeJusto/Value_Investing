from dataclasses import dataclass


@dataclass
class IncomeStatement:
    revenue: float | None = None
    cogs: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    ebit: float | None = None
    ebitda: float | None = None
    net_income: float | None = None
    interest_expense: float | None = None
    tax_provision: float | None = None
    pretax_income: float | None = None
    effective_tax_rate: float | None = None
    # Additional income statement fields
    operating_expense: float | None = None
    research_development: float | None = None
    sga: float | None = None
    non_operating_income_expense: float | None = None


@dataclass
class BalanceSheet:
    total_assets: float | None = None
    total_liabilities: float | None = None
    total_debt: float | None = None
    cash_and_equivalents: float | None = None
    working_capital: float | None = None
    retained_earnings: float | None = None
    stockholders_equity: float | None = None


@dataclass
class CashFlowStatement:
    operating_cash_flow: float | None = None
    capital_expenditure: float | None = None
    free_cash_flow: float | None = None
    depreciation_amortization: float | None = None
    dividends_paid: float | None = None
    repurchase_of_stock: float | None = None
    working_capital_change: float | None = None


@dataclass
class FinancialStatement:
    income: IncomeStatement | None = None
    balance: BalanceSheet | None = None
    cash_flow: CashFlowStatement | None = None
    year: int | None = None
