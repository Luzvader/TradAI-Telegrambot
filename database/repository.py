"""
Repositorio de acceso a datos – operaciones CRUD sobre los modelos.

Este módulo re-exporta todas las funciones desde los sub-módulos en
``database.repos`` para mantener compatibilidad con el código existente
(``from database import repository as repo``).

Los sub-módulos organizan las funciones por dominio:
  • portfolio  – Portfolio, Position, Operation, Cash, Strategy, Snapshot
  • signals    – Signal, Watchlist, Earnings
  • config     – Auto Mode, Investment Objective, Custom Alert
  • analytics  – Learning, Market Context, OpenAI Usage
"""

# ── Portfolio, Position, Operation, Cash, Strategy, Snapshot ─
from database.repos.portfolio import (  # noqa: F401
    adjust_cash,
    close_position,
    get_open_positions,
    get_operations,
    get_or_create_portfolio,
    get_portfolio,
    get_portfolio_by_type,
    get_portfolio_snapshots,
    get_portfolio_strategy,
    get_position_by_ticker,
    record_operation,
    save_portfolio_snapshot,
    set_cash,
    set_initial_capital,
    set_portfolio_strategy,
    update_portfolio_cash,
    update_position_price,
    update_position_sector,
    upsert_position,
)

# ── Signal, Watchlist, Earnings ──────────────────────────────────
from database.repos.signals import (  # noqa: F401
    add_to_watchlist,
    get_active_watchlist,
    get_recent_signals,
    get_signals_since,
    get_upcoming_earnings,
    has_recent_signal,
    remove_from_watchlist,
    save_earnings_event,
    save_signal,
)

# ── Auto Mode, Investment Objective, Custom Alert ─────────────
from database.repos.config import (  # noqa: F401
    create_custom_alert,
    deactivate_objective,
    delete_alert,
    get_active_alerts,
    get_all_active_auto_modes,
    get_all_active_objectives,
    get_auto_mode_config,
    get_investment_objective,
    get_or_create_auto_mode_config,
    save_investment_objective,
    set_auto_mode,
    toggle_auto_mode,
    trigger_alert,
    update_auto_mode_config,
    update_auto_mode_timestamps,
)

# ── Learning, Market Context, OpenAI Usage, Dividends ─────────
from database.repos.analytics import (  # noqa: F401
    get_dividends_for_portfolio,
    get_latest_context,
    get_learning_logs,
    get_learning_summary,
    get_openai_usage_summary,
    get_total_dividends,
    save_dividend_payment,
    save_learning_log,
    save_market_context,
    save_openai_usage,
)
