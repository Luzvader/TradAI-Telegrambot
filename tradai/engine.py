from __future__ import annotations

from typing import List

from .strategies import Strategy
from .wallet import Wallet


def execute(strategy: Strategy, prices: List[float], wallet: Wallet) -> str:
    """Evalúa la estrategia y ejecuta la orden usando la wallet."""
    action = strategy.evaluate(prices)
    if action in {"BUY", "SELL"}:
        wallet.place_order(strategy.symbol, action, 1.0)
    return action
