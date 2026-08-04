"""full schema v2

Revision ID: 002
Revises: 001
Create Date: 2026-08-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("analysis_results")
    op.drop_table("financial_statements")
    op.drop_table("companies")

    op.create_table(
        "companies",
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("sector", sa.String(length=100), nullable=True),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("exchange", sa.String(length=50), nullable=True),
        sa.Column("country", sa.String(length=50), nullable=True, server_default="US"),
        sa.Column("market_cap", sa.Float(), nullable=True),
        sa.Column("enterprise_value", sa.Float(), nullable=True),
        sa.Column("beta", sa.Float(), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True, server_default="USD"),
        sa.Column("data_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("ticker"),
    )
    op.create_index("ix_companies_sector", "companies", ["sector"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("is_superuser", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "financial_data",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_period", sa.String(length=10), nullable=True),
        sa.Column("statement_type", sa.String(length=20), nullable=False),
        sa.Column("data", JSONB(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=True, server_default="yahoo"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["ticker"], ["companies.ticker"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "fiscal_year", "fiscal_period", "statement_type"),
    )
    op.create_index("ix_financial_data_ticker_year", "financial_data", ["ticker", "fiscal_year"])

    op.create_table(
        "analysis_cache",
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("metrics", JSONB(), nullable=False),
        sa.Column("source_provider", sa.String(length=50), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["ticker"], ["companies.ticker"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("ticker"),
    )

    op.create_table(
        "screener_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tickers", JSONB(), nullable=True),
        sa.Column("filters", JSONB(), nullable=True),
        sa.Column("top_n", sa.Integer(), nullable=True, server_default="25"),
        sa.Column("status", sa.String(length=20), nullable=True, server_default="pending"),
        sa.Column("progress", sa.Float(), nullable=True, server_default="0"),
        sa.Column("results", JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "portfolio_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("shares", sa.Float(), nullable=True, server_default="0"),
        sa.Column("avg_cost", sa.Float(), nullable=True),
        sa.Column("added_date", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ticker"], ["companies.ticker"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portfolio_id", "ticker"),
    )

    op.create_table(
        "watchlists",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("watchlist_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["ticker"], ["companies.ticker"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["watchlist_id"], ["watchlists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("watchlist_id", "ticker"),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("metric_name", sa.String(length=50), nullable=False),
        sa.Column("operator", sa.String(length=5), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("notify_email", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("notify_push", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("last_triggered", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["ticker"], ["companies.ticker"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("watchlist_items")
    op.drop_table("watchlists")
    op.drop_table("portfolio_items")
    op.drop_table("portfolios")
    op.drop_table("screener_jobs")
    op.drop_table("analysis_cache")
    op.drop_table("financial_data")
    op.drop_table("users")
    op.drop_table("companies")

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
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker"),
    )
