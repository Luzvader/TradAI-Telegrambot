"""Sencillo POC de decisiones a nivel de portafolio.

Este módulo define estructuras básicas para representar un portafolio y
calcular recomendaciones de rebalanceo ("BUY", "SELL" o "HOLD"). Las
recomendaciones se obtienen comparando la distribución actual del
portafolio con un objetivo deseado y aplicando un umbral de desviación.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Position:
    """Posición simple de una cripto."""

    symbol: str
    amount: float
    price: float

    def value(self) -> float:
        """Valor de mercado de la posición."""
        return self.amount * self.price


@dataclass
class Portfolio:
    """Colección de posiciones y efectivo disponible."""

    cash: float = 0.0
    positions: Dict[str, Position] = field(default_factory=dict)

    def total_value(self) -> float:
        """Valor total del portafolio (efectivo + posiciones)."""
        return self.cash + sum(p.value() for p in self.positions.values())

    def weights(self) -> Dict[str, float]:
        """Porcentajes del portafolio por activo."""
        total = self.total_value()
        if total == 0:
            return {sym: 0.0 for sym in self.positions}
        return {sym: pos.value() / total for sym, pos in self.positions.items()}


def decide_actions(
    portfolio: Portfolio,
    target_weights: Dict[str, float],
    prices: Dict[str, float],
    threshold: float = 0.05,
) -> Dict[str, str]:
    """Genera acciones BUY/SELL/HOLD para cada activo.

    Parameters
    ----------
    portfolio:
        Estado actual del portafolio.
    target_weights:
        Mapeo de símbolo a porcentaje objetivo (0-1) del portafolio.
    prices:
        Precios de mercado más recientes por símbolo.
    threshold:
        Desviación absoluta mínima para proponer un ajuste.

    Returns
    -------
    Dict[str, str]
        Acciones recomendadas por símbolo.
    """

    # Actualizar el precio de las posiciones existentes
    for sym, price in prices.items():
        if sym in portfolio.positions:
            portfolio.positions[sym].price = price

    current_weights = portfolio.weights()
    decisions: Dict[str, str] = {}

    for sym, target_w in target_weights.items():
        current_w = current_weights.get(sym, 0.0)
        diff = current_w - target_w
        if diff > threshold:
            decisions[sym] = "SELL"
        elif diff < -threshold:
            decisions[sym] = "BUY"
        else:
            decisions[sym] = "HOLD"

    # Activos presentes en el portafolio pero no en el objetivo
    for sym in portfolio.positions:
        if sym not in decisions:
            decisions[sym] = "SELL"

    return decisions
