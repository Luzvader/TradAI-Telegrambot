"""
Paquete base para el bot de trading TradAI.

Este paquete proporciona herramientas para interactuar con TradingView, ejecutar estrategias de trading,
y procesar datos de mercado, especialmente para criptomonedas. Incluye clientes para obtener datos,
servicios para indicadores técnicos, estrategias predefinidas y un motor de ejecución.

Módulos principales:
- tradingview: Cliente para interactuar con la API de TradingView.
- services.market_service: Funciones para obtener datos de mercado con indicadores.
- strategies: Clases y funciones para definir y gestionar estrategias de trading.
- engine: Motor para ejecutar estrategias.
- crypto_bot: Funciones específicas para trading de criptomonedas.
"""

__version__ = "1.0.0"

# Cliente para TradingView y otros módulos opcionales
try:  # pragma: no cover - optional imports for lightweight testing
    from .tradingview import TradingViewClient
    from .services.market_service import fetch_with_indicators
    from .strategies import (
        Strategy,
        MACDStrategy,
        save_strategy,
        load_strategies,
    )
    from .engine import execute
    from .crypto_bot import process_crypto

    __all__ = [
        "TradingViewClient",
        "fetch_with_indicators",
        "Strategy",
        "MACDStrategy",
        "save_strategy",
        "load_strategies",
        "execute",
        "process_crypto",
    ]
except Exception:  # pragma: no cover - ignore missing heavy deps
    __all__ = []
