"""data reliability schema: quality columns and multi-source support

Revision ID: 004
Revises: 003
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "normalized_financials",
        sa.Column("data_quality_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "normalized_financials",
        sa.Column("data_completeness", sa.Float(), nullable=True),
    )
    op.add_column(
        "normalized_financials",
        sa.Column(
            "is_complete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "normalized_financials",
        sa.Column(
            "data_source_priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "normalized_financials",
        sa.Column("derived_metrics", JSONB(), nullable=True),
    )

    op.drop_constraint(
        "uq_normalized_ticker_year_period",
        "normalized_financials",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_normalized_ticker_year_period_source",
        "normalized_financials",
        ["ticker", "fiscal_year", "period", "source"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_normalized_ticker_year_period_source",
        "normalized_financials",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_normalized_ticker_year_period",
        "normalized_financials",
        ["ticker", "fiscal_year", "period"],
    )

    op.drop_column("normalized_financials", "derived_metrics")
    op.drop_column("normalized_financials", "data_source_priority")
    op.drop_column("normalized_financials", "is_complete")
    op.drop_column("normalized_financials", "data_completeness")
    op.drop_column("normalized_financials", "data_quality_score")
