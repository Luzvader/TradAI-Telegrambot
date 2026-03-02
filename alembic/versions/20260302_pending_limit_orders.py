"""Add pending_limit_orders table for tracking limit buy orders.

Revision ID: 20260302_pending_limit_orders
Revises: 20260301_pos_asset_type
Create Date: 2026-03-02
"""

from alembic import op
import sqlalchemy as sa

revision = "20260302_pending_limit_orders"
down_revision = "20260301_pos_asset_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the pendingLimitOrderStatus enum
    op.execute(sa.text(
        "DO $$ BEGIN CREATE TYPE pendinglimitorderstatus AS ENUM "
        "('pending','filled','cancelled','expired'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    ))
    pending_status = sa.Enum(
        "pending", "filled", "cancelled", "expired",
        name="pendinglimitorderstatus",
        create_type=False,
    )

    op.create_table(
        "pending_limit_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id"), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("market", sa.String(20), nullable=False, server_default="NASDAQ"),
        sa.Column("shares", sa.Float(), nullable=False),
        sa.Column("limit_price", sa.Float(), nullable=False),
        sa.Column("broker_order_id", sa.String(100), nullable=True),
        sa.Column("chat_id", sa.String(50), nullable=True),
        sa.Column("asset_type", sa.String(10), nullable=True),
        sa.Column("status", pending_status, nullable=False, server_default="pending"),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filled_price", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_pending_limit_orders_status", "pending_limit_orders", ["status"])
    op.create_index("ix_pending_limit_orders_ticker", "pending_limit_orders", ["ticker"])


def downgrade() -> None:
    op.drop_index("ix_pending_limit_orders_ticker", table_name="pending_limit_orders")
    op.drop_index("ix_pending_limit_orders_status", table_name="pending_limit_orders")
    op.drop_table("pending_limit_orders")
    op.execute(sa.text("DROP TYPE IF EXISTS pendinglimitorderstatus"))
