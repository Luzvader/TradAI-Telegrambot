"""
Tipos compartidos para las distintas estrategias.
Todas las estrategias devuelven el mismo objeto de scoring para que el
resto del sistema (signals, screener, watchlist, Telegram) sea agnóstico.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config.settings import SIGNAL_BUY_THRESHOLD, SIGNAL_SELL_THRESHOLD


@dataclass(slots=True)
class StrategyScore:
    """Resultado del análisis de una acción para una estrategia concreta."""

    ticker: str
    strategy: str  # value|growth|dividend|balanced|conservative

    # 0-100
    value_score: float
    quality_score: float
    safety_score: float
    overall_score: float

    margin_of_safety: float | None
    reasoning: list[str]
    market: str | None = None  # Mercado de origen (IBEX, LSE, etc.)

    # FundamentalData cacheado durante screening (evita doble fetch)
    fundamentals: Any = field(default=None, repr=False)

    @property
    def signal(self) -> str:
        if self.overall_score >= SIGNAL_BUY_THRESHOLD:
            return "BUY"
        if self.overall_score <= SIGNAL_SELL_THRESHOLD:
            return "SELL"
        return "HOLD"

