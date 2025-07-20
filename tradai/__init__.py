"""Paquete base para el bot de trading TradAI."""

# Exponemos solo el cliente de TradingView a nivel de paquete
from .tradingview import TradingViewClient
from .monitor import monitor_prices
from .strategies import Strategy, save_strategy, load_strategies
from .engine import execute

__all__ = [
    "TradingViewClient",
    "monitor_prices",
    "Strategy",
    "save_strategy",
    "load_strategies",
    "execute",
]
