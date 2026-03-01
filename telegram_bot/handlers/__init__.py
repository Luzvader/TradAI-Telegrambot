"""
Handlers de comandos de Telegram – paquete reorganizado.

Cada sub-módulo define una lista ``COMMANDS`` de :class:`CommandInfo`.
Este ``__init__`` los recopila en ``ALL_COMMANDS`` para que ``bot.py``
registre handlers y menú de Telegram desde un punto único.

Sub-módulos:
  • helpers          – Utilidades compartidas (_parse_buy_sell, _send_long)
  • registry         – CommandInfo dataclass
  • portfolio_cmds   – /cartera, /buy, /sell, /capital, /dividendos, /etf_cartera
  • analysis_cmds    – /analizar, /scan, /macro, /strategy, /historial, /comparar,
                       /backtest, /diversificacion, /etf, /insider
  • system_cmds      – /help, /costes, unknown_command
  • watchlist_cmds   – /watchlist
  • auto_cmds        – /auto
  • alert_cmds       – /alertas
  • objective_cmds   – /objetivo
  • earnings_cmds    – /earnings
  • broker_cmds      – /broker
  • callbacks        – callback_handler (botones inline)
"""

from telegram_bot.handlers.registry import CommandInfo  # noqa: F401

from telegram_bot.handlers.portfolio_cmds import COMMANDS as _portfolio_cmds
from telegram_bot.handlers.analysis_cmds import COMMANDS as _analysis_cmds
from telegram_bot.handlers.system_cmds import COMMANDS as _system_cmds
from telegram_bot.handlers.watchlist_cmds import COMMANDS as _watchlist_cmds
from telegram_bot.handlers.auto_cmds import COMMANDS as _auto_cmds
from telegram_bot.handlers.alert_cmds import COMMANDS as _alert_cmds
from telegram_bot.handlers.objective_cmds import COMMANDS as _objective_cmds
from telegram_bot.handlers.earnings_cmds import COMMANDS as _earnings_cmds
from telegram_bot.handlers.broker_cmds import COMMANDS as _broker_cmds
from telegram_bot.handlers.web_cmds import COMMANDS as _web_cmds

# Callbacks y unknown_command se registran aparte en bot.py
from telegram_bot.handlers.callbacks import callback_handler  # noqa: F401
from telegram_bot.handlers.system_cmds import unknown_command  # noqa: F401

# ── Registro unificado de todos los comandos ─────────────────

ALL_COMMANDS: list[CommandInfo] = [
    *_system_cmds,
    *_portfolio_cmds,
    *_analysis_cmds,
    *_watchlist_cmds,
    *_auto_cmds,
    *_alert_cmds,
    *_objective_cmds,
    *_earnings_cmds,
    *_broker_cmds,
    *_web_cmds,
]
