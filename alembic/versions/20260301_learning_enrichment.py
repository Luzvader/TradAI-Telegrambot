"""Enrich learning engine: operation origin, LearningLog metadata.

Revision ID: 20260301_learning_enrichment
Revises: 20260301_analysis_logs
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa

revision = "20260301_learning_enrich"
down_revision = "20260301_analysis_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Operation: add origin enum column ──
    op.execute(
        "CREATE TYPE operationorigin AS ENUM "
        "('manual', 'auto', 'safe', 'backtest', 'import')"
    )
    op.add_column(
        "operations",
        sa.Column(
            "origin",
            sa.Enum(
                "manual", "auto", "safe", "backtest", "import",
                name="operationorigin",
            ),
            nullable=False,
            server_default="manual",
        ),
    )

    # ── LearningLog: add enrichment columns ──
    op.add_column(
        "learning_logs",
        sa.Column("origin", sa.String(20), nullable=True),
    )
    op.add_column(
        "learning_logs",
        sa.Column("total_dividends", sa.Float(), nullable=True),
    )
    op.add_column(
        "learning_logs",
        sa.Column("entry_signal_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "learning_logs",
        sa.Column("entry_rsi", sa.Float(), nullable=True),
    )
    op.add_column(
        "learning_logs",
        sa.Column("entry_macd_signal", sa.String(20), nullable=True),
    )
    op.add_column(
        "learning_logs",
        sa.Column("diversification_score_at_entry", sa.Float(), nullable=True),
    )
    op.add_column(
        "learning_logs",
        sa.Column("market_regime", sa.String(30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("learning_logs", "market_regime")
    op.drop_column("learning_logs", "diversification_score_at_entry")
    op.drop_column("learning_logs", "entry_macd_signal")
    op.drop_column("learning_logs", "entry_rsi")
    op.drop_column("learning_logs", "entry_signal_score")
    op.drop_column("learning_logs", "total_dividends")
    op.drop_column("learning_logs", "origin")
    op.drop_column("operations", "origin")
    op.execute("DROP TYPE operationorigin")
