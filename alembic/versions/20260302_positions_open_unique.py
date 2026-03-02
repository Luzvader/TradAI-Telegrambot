"""Add partial unique index for open positions.

Revision ID: 20260302_positions_open_unique
Revises: 20260302_pending_limit_orders
Create Date: 2026-03-02
"""

from alembic import op
import sqlalchemy as sa

revision = "20260302_positions_open_unique"
down_revision = "20260302_pending_limit_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "DROP INDEX IF EXISTS uq_positions_open_portfolio_ticker_market"
        )
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "uq_positions_open_portfolio_ticker_market "
            "ON positions (portfolio_id, ticker, market) "
            "WHERE lower(status::text) = 'open'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP INDEX IF EXISTS uq_positions_open_portfolio_ticker_market"
        )
    )
