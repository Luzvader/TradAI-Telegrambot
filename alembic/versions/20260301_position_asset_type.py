"""Add asset_type column to positions table for stock/ETF distinction.

Revision ID: 20260301_pos_asset_type
Revises: 20260301_learning_enrich
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa

revision = "20260301_pos_asset_type"
down_revision = "20260301_learning_enrich"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The 'assettype' enum already exists from the initial migration (used by watchlist)
    asset_type = sa.Enum("stock", "etf", name="assettype", create_type=False)

    op.add_column(
        "positions",
        sa.Column(
            "asset_type",
            asset_type,
            nullable=False,
            server_default="stock",
        ),
    )


def downgrade() -> None:
    op.drop_column("positions", "asset_type")
