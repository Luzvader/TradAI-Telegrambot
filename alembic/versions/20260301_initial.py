"""Initial schema — creates all TradAI tables from scratch.

Revision ID: 20260301_initial
Revises: (none — first migration)
Create Date: 2026-03-01

Consolidates previous incremental migrations (learning_source,
auto_mode_type, watchlist_asset_type) into a single baseline.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260301_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums (crear explícitamente antes de las tablas) ─────
    # ── Enums (raw SQL idempotente para asyncpg) ───────────────
    _enum_defs = [
        ("portfoliotype",   "'real','backtest'"),
        ("operationside",   "'BUY','SELL'"),
        ("signaltype",      "'BUY','SELL','HOLD'"),
        ("positionstatus",  "'open','closed'"),
        ("watchliststatus", "'active','removed','promoted'"),
        ("assettype",       "'stock','etf'"),
        ("automodetype",    "'off','on','safe'"),
        ("strategytype",    "'value','growth','dividend','balanced','conservative'"),
    ]
    for name, vals in _enum_defs:
        op.execute(sa.text(
            f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({vals}); "
            f"EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        ))

    # Referencias a enums ya creados (create_type=False evita doble CREATE TYPE)
    portfolio_type = sa.Enum("real", "backtest", name="portfoliotype", create_type=False)
    operation_side = sa.Enum("BUY", "SELL", name="operationside", create_type=False)
    signal_type = sa.Enum("BUY", "SELL", "HOLD", name="signaltype", create_type=False)
    position_status = sa.Enum("open", "closed", name="positionstatus", create_type=False)
    watchlist_status = sa.Enum("active", "removed", "promoted", name="watchliststatus", create_type=False)
    asset_type = sa.Enum("stock", "etf", name="assettype", create_type=False)
    auto_mode_type = sa.Enum("off", "on", "safe", name="automodetype", create_type=False)
    strategy_type = sa.Enum(
        "value", "growth", "dividend", "balanced", "conservative",
        name="strategytype", create_type=False,
    )

    # ── portfolios ───────────────────────────────────────────
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("portfolio_type", portfolio_type, nullable=False),
        sa.Column("strategy", strategy_type, server_default="value"),
        sa.Column("initial_capital", sa.Float(), nullable=True, server_default="0"),
        sa.Column("cash", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("name", "portfolio_type", name="uq_portfolio_name_type"),
    )

    # ── positions ────────────────────────────────────────────
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id"), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("market", sa.String(20), nullable=False, server_default="NASDAQ"),
        sa.Column("sector", sa.String(100), nullable=True),
        sa.Column("shares", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("current_price", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("take_profit", sa.Float(), nullable=True),
        sa.Column("status", position_status, server_default="open"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_positions_portfolio_status", "positions", ["portfolio_id", "status"])
    op.create_index("ix_positions_ticker", "positions", ["ticker"])

    # ── operations ───────────────────────────────────────────
    op.create_table(
        "operations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id"), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("market", sa.String(20), nullable=False, server_default="NASDAQ"),
        sa.Column("side", operation_side, nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("shares", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_operations_portfolio_timestamp", "operations", ["portfolio_id", "timestamp"])
    op.create_index("ix_operations_ticker", "operations", ["ticker"])

    # ── signals ──────────────────────────────────────────────
    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("market", sa.String(20), nullable=False, server_default="NASDAQ"),
        sa.Column("signal_type", signal_type, nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("value_score", sa.Float(), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("ai_analysis", sa.Text(), nullable=True),
        sa.Column("acted_on", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_signals_ticker_type_created", "signals", ["ticker", "signal_type", "created_at"])
    op.create_index("ix_signals_created_at", "signals", ["created_at"])

    # ── watchlist ────────────────────────────────────────────
    op.create_table(
        "watchlist",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("market", sa.String(20), nullable=False, server_default="NASDAQ"),
        sa.Column("asset_type", asset_type, nullable=False, server_default="stock"),
        sa.Column("sector", sa.String(100), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("ai_notes", sa.Text(), nullable=True),
        sa.Column("status", watchlist_status, server_default="active"),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_watchlist_status", "watchlist", ["status"])

    # ── earnings_events ──────────────────────────────────────
    op.create_table(
        "earnings_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("report_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fiscal_quarter", sa.String(10), nullable=True),
        sa.Column("expected_eps", sa.Float(), nullable=True),
        sa.Column("actual_eps", sa.Float(), nullable=True),
        sa.Column("expected_revenue", sa.Float(), nullable=True),
        sa.Column("actual_revenue", sa.Float(), nullable=True),
        sa.Column("surprise_pct", sa.Float(), nullable=True),
        sa.Column("ai_analysis", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("ticker", "report_date", name="uq_earnings_ticker_date"),
    )
    op.create_index("ix_earnings_report_date", "earnings_events", ["report_date"])

    # ── dividend_payments ────────────────────────────────────
    op.create_table(
        "dividend_payments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id"), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("market", sa.String(20), nullable=False, server_default="NASDAQ"),
        sa.Column("ex_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pay_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("amount_per_share", sa.Float(), nullable=False),
        sa.Column("shares_held", sa.Float(), nullable=False),
        sa.Column("total_amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="USD"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_dividends_portfolio_ticker", "dividend_payments", ["portfolio_id", "ticker"])

    # ── learning_logs ────────────────────────────────────────
    op.create_table(
        "learning_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("operation_id", sa.Integer(), sa.ForeignKey("operations.id"), nullable=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("side", operation_side, nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("profit_pct", sa.Float(), nullable=True),
        sa.Column("holding_days", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=True),
        sa.Column("what_went_well", sa.Text(), nullable=True),
        sa.Column("what_went_wrong", sa.Text(), nullable=True),
        sa.Column("lessons_learned", sa.Text(), nullable=True),
        sa.Column("market_context_at_entry", sa.Text(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="real"),
        sa.Column("strategy_used", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── market_contexts ──────────────────────────────────────
    op.create_table(
        "market_contexts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("context_type", sa.String(50), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source", sa.String(200), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── auto_mode_config ─────────────────────────────────────
    op.create_table(
        "auto_mode_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id"), nullable=False, unique=True),
        sa.Column("mode", auto_mode_type, nullable=False, server_default="off"),
        sa.Column("scan_interval_minutes", sa.Integer(), server_default="60"),
        sa.Column("analyze_interval_minutes", sa.Integer(), server_default="120"),
        sa.Column("macro_interval_minutes", sa.Integer(), server_default="240"),
        sa.Column("watchlist_auto_manage", sa.Boolean(), server_default="true"),
        sa.Column("daily_summary_hour", sa.Integer(), server_default="9"),
        sa.Column("daily_summary_minute", sa.Integer(), server_default="0"),
        sa.Column("notify_signals", sa.Boolean(), server_default="true"),
        sa.Column("notify_watchlist_changes", sa.Boolean(), server_default="true"),
        sa.Column("last_scan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_analyze_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_macro_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_daily_summary_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_watchlist_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── portfolio_snapshots ──────────────────────────────────
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id"), nullable=False),
        sa.Column("total_value", sa.Float(), nullable=False),
        sa.Column("invested_value", sa.Float(), nullable=False),
        sa.Column("cash", sa.Float(), nullable=False, server_default="0"),
        sa.Column("num_positions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pnl", sa.Float(), nullable=True),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("benchmark_value", sa.Float(), nullable=True),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=True),
    )

    # ── custom_alerts ────────────────────────────────────────
    op.create_table(
        "custom_alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("market", sa.String(20), nullable=False, server_default="NASDAQ"),
        sa.Column("alert_type", sa.String(30), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("triggered", sa.Boolean(), server_default="false"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alerts_triggered", "custom_alerts", ["triggered"])

    # ── openai_usage ─────────────────────────────────────────
    op.create_table(
        "openai_usage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("model", sa.String(50), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("context", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_openai_usage_created", "openai_usage", ["created_at"])

    # ── investment_objectives ────────────────────────────────
    op.create_table(
        "investment_objectives",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("market", sa.String(20), nullable=False, server_default="NASDAQ"),
        sa.Column("thesis", sa.Text(), nullable=True),
        sa.Column("target_entry_price", sa.Float(), nullable=True),
        sa.Column("target_exit_price", sa.Float(), nullable=True),
        sa.Column("catalysts", sa.Text(), nullable=True),
        sa.Column("risks", sa.Text(), nullable=True),
        sa.Column("time_horizon", sa.String(20), nullable=True, server_default="medio"),
        sa.Column("conviction", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="ai"),
        sa.Column("active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("investment_objectives")
    op.drop_index("ix_openai_usage_created", table_name="openai_usage")
    op.drop_table("openai_usage")
    op.drop_index("ix_alerts_triggered", table_name="custom_alerts")
    op.drop_table("custom_alerts")
    op.drop_table("portfolio_snapshots")
    op.drop_table("auto_mode_config")
    op.drop_table("market_contexts")
    op.drop_table("learning_logs")
    op.drop_index("ix_dividends_portfolio_ticker", table_name="dividend_payments")
    op.drop_table("dividend_payments")
    op.drop_index("ix_earnings_report_date", table_name="earnings_events")
    op.drop_table("earnings_events")
    op.drop_index("ix_watchlist_status", table_name="watchlist")
    op.drop_table("watchlist")
    op.drop_index("ix_signals_created_at", table_name="signals")
    op.drop_index("ix_signals_ticker_type_created", table_name="signals")
    op.drop_table("signals")
    op.drop_index("ix_operations_ticker", table_name="operations")
    op.drop_index("ix_operations_portfolio_timestamp", table_name="operations")
    op.drop_table("operations")
    op.drop_index("ix_positions_ticker", table_name="positions")
    op.drop_index("ix_positions_portfolio_status", table_name="positions")
    op.drop_table("positions")
    op.drop_table("portfolios")

    # Enums
    sa.Enum(name="strategytype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="automodetype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="assettype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="watchliststatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="positionstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="signaltype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="operationside").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="portfoliotype").drop(op.get_bind(), checkfirst=True)
