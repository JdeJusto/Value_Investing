"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-07-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("sector", sa.String(length=100), nullable=True),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("exchange", sa.String(length=50), nullable=True),
        sa.Column("market_cap", sa.Float(), nullable=True),
        sa.Column("enterprise_value", sa.Float(), nullable=True),
        sa.Column("beta", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker"),
    )
    op.create_index("ix_companies_ticker", "companies", ["ticker"])

    op.create_table(
        "financial_statements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_period", sa.String(length=10), nullable=True),
        sa.Column("statement_type", sa.String(length=20), nullable=False),
        sa.Column("data", JSONB(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True
        ),
        sa.ForeignKeyConstraint(["ticker"], ["companies.ticker"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_financial_statements_ticker", "financial_statements", ["ticker"]
    )

    op.create_table(
        "analysis_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("metric_name", sa.String(length=50), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("params", JSONB(), nullable=True),
        sa.Column(
            "calculated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True
        ),
        sa.ForeignKeyConstraint(["ticker"], ["companies.ticker"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_results_ticker", "analysis_results", ["ticker"])


def downgrade() -> None:
    op.drop_table("analysis_results")
    op.drop_table("financial_statements")
    op.drop_table("companies")
