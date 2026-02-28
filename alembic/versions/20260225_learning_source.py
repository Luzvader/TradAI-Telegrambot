"""add source and strategy_used to learning_logs

Revision ID: 20260225_learning_source
Revises:
Create Date: 2026-02-25

Añade campos source y strategy_used a learning_logs para distinguir
entre operaciones reales y de backtesting, y registrar la estrategia
que generó cada trade.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260225_learning_source"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learning_logs",
        sa.Column("source", sa.String(20), nullable=False, server_default="real"),
    )
    op.add_column(
        "learning_logs",
        sa.Column("strategy_used", sa.String(30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("learning_logs", "strategy_used")
    op.drop_column("learning_logs", "source")
