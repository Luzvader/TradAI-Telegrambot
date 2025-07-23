"""Paquete base para el bot de trading TradAI."""

# Exponemos solo el cliente de TradingView y funciones básicas a nivel de paquete
from .tradingview import TradingViewClient
from .services.market_service import fetch_with_indicators
from .strategies import Strategy, MACDStrategy, save_strategy, load_strategies
from .engine import execute

__all__ = [
    "TradingViewClient",
    "fetch_with_indicators",
    "Strategy",
    "MACDStrategy",
    "save_strategy",
    "load_strategies",
    "execute",
]
