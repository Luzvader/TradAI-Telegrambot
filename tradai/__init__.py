"""Paquete base para el bot de trading TradAI."""

# Exponemos solo el cliente de TradingView y funciones básicas a nivel de paquete
from .tradingview import TradingViewClient
from .strategies import Strategy, save_strategy, load_strategies
from .engine import execute

__all__ = [
    "TradingViewClient",
    "Strategy",
    "save_strategy",
    "load_strategies",
    "execute",
]
