"""ORM model for normalized annual financial data (provider-agnostic)."""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)

from backend.adapters.database.base import Base

# Columns holding a single normalized metric. Shared with the repository
# mapping code so model and object stay in sync.
METRIC_COLUMNS: tuple[str, ...] = (
    "revenue",
    "cogs",
    "gross_profit",
    "operating_income",
    "ebit",
    "ebitda",
    "net_income",
    "interest_expense",
    "tax_provision",
    "pretax_income",
    "total_assets",
    "total_liabilities",
    "total_debt",
    "cash_and_equivalents",
    "working_capital",
    "retained_earnings",
    "stockholders_equity",
    "operating_cash_flow",
    "capital_expenditure",
    "free_cash_flow",
    "depreciation_amortization",
    "dividends_paid",
    "repurchase_of_stock",
    "working_capital_change",
)


class NormalizedFinancialModel(Base):
    __tablename__ = "normalized_financials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(
        String(10),
        ForeignKey("companies.ticker", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fiscal_year = Column(Integer, nullable=False)
    period = Column(String(10), nullable=False, server_default="FY")
    currency = Column(String(3), nullable=False, server_default="USD")
    source = Column(String(50), nullable=False, server_default="yahoo")
    shares_outstanding = Column(BigInteger, nullable=True)
    loaded_at = Column(DateTime(timezone=True), nullable=True)

    revenue = Column(Float, nullable=True)
    cogs = Column(Float, nullable=True)
    gross_profit = Column(Float, nullable=True)
    operating_income = Column(Float, nullable=True)
    ebit = Column(Float, nullable=True)
    ebitda = Column(Float, nullable=True)
    net_income = Column(Float, nullable=True)
    interest_expense = Column(Float, nullable=True)
    tax_provision = Column(Float, nullable=True)
    pretax_income = Column(Float, nullable=True)
    total_assets = Column(Float, nullable=True)
    total_liabilities = Column(Float, nullable=True)
    total_debt = Column(Float, nullable=True)
    cash_and_equivalents = Column(Float, nullable=True)
    working_capital = Column(Float, nullable=True)
    retained_earnings = Column(Float, nullable=True)
    stockholders_equity = Column(Float, nullable=True)
    operating_cash_flow = Column(Float, nullable=True)
    capital_expenditure = Column(Float, nullable=True)
    free_cash_flow = Column(Float, nullable=True)
    depreciation_amortization = Column(Float, nullable=True)
    dividends_paid = Column(Float, nullable=True)
    repurchase_of_stock = Column(Float, nullable=True)
    working_capital_change = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "ticker", "fiscal_year", "period", name="uq_normalized_ticker_year_period"
        ),
    )
