"""Add analysis_logs table for storing full analysis output.

Revision ID: 20260301_analysis_logs
Revises: 20260301_initial
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa

revision = "20260301_analysis_logs"
down_revision = "20260301_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("market", sa.String(20), nullable=False, server_default="NASDAQ"),
        sa.Column("strategy_used", sa.String(30), nullable=True),
        sa.Column("signal", sa.String(10), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("value_score", sa.Float(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("safety_score", sa.Float(), nullable=True),
        sa.Column("price_at_analysis", sa.Float(), nullable=True),
        sa.Column("margin_of_safety", sa.Float(), nullable=True),
        sa.Column("pe_ratio", sa.Float(), nullable=True),
        sa.Column("roe", sa.Float(), nullable=True),
        sa.Column("debt_to_equity", sa.Float(), nullable=True),
        sa.Column("dividend_yield", sa.Float(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("tech_summary", sa.Text(), nullable=True),
        sa.Column("price_summary", sa.Text(), nullable=True),
        sa.Column("ai_analysis", sa.Text(), nullable=True),
        sa.Column("broker_tradable", sa.Boolean(), nullable=True),
        sa.Column("deterministic_context", sa.Text(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_analysis_logs_ticker", "analysis_logs", ["ticker"])
    op.create_index("ix_analysis_logs_created", "analysis_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_analysis_logs_created", table_name="analysis_logs")
    op.drop_index("ix_analysis_logs_ticker", table_name="analysis_logs")
    op.drop_table("analysis_logs")
