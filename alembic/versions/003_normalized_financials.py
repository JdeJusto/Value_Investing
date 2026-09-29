"""normalized financials schema

Revision ID: 003
Revises: 002
Create Date: 2026-08-13
"""

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_METRIC_COLUMNS = (
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


def upgrade() -> None:
    op.create_table(
        "normalized_financials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("period", sa.String(length=10), nullable=False, server_default="FY"),
        sa.Column(
            "currency", sa.String(length=3), nullable=False, server_default="USD"
        ),
        sa.Column(
            "source", sa.String(length=50), nullable=False, server_default="yahoo"
        ),
        sa.Column("shares_outstanding", sa.BigInteger(), nullable=True),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=True),
        *[sa.Column(name, sa.Float(), nullable=True) for name in _METRIC_COLUMNS],
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["ticker"], ["companies.ticker"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ticker", "fiscal_year", "period", name="uq_normalized_ticker_year_period"
        ),
    )
    op.create_index(
        "ix_normalized_financials_ticker_year",
        "normalized_financials",
        ["ticker", "fiscal_year"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_normalized_financials_ticker_year", table_name="normalized_financials"
    )
    op.drop_table("normalized_financials")
