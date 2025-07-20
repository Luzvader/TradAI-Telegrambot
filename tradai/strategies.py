from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List

from .indicators import ema

STRATEGIES_FILE = Path.home() / ".tradai_strategies.json"


@dataclass
class Strategy:
    """Representa una estrategia muy sencilla basada en dos EMAs."""

    name: str
    symbol: str
    ema_short: int = 20
    ema_long: int = 50

    def evaluate(self, prices: List[float]) -> str:
        """Devuelve BUY, SELL u HOLD dependiendo del cruce de EMAs."""
        short = ema(prices, self.ema_short)
        long = ema(prices, self.ema_long)
        if short is None or long is None:
            return "HOLD"
        return "BUY" if short > long else "SELL"


def load_strategies() -> Dict[str, Strategy]:
    """Carga las estrategias guardadas."""
    if not STRATEGIES_FILE.exists():
        return {}
    try:
        data = json.loads(STRATEGIES_FILE.read_text())
    except Exception:
        return {}
    return {name: Strategy(**cfg) for name, cfg in data.items()}


def save_strategy(strategy: Strategy) -> None:
    """Persiste una estrategia en el archivo configurado."""
    strategies = {name: asdict(s) for name, s in load_strategies().items()}
    strategies[strategy.name] = asdict(strategy)
    STRATEGIES_FILE.write_text(json.dumps(strategies))


def get_strategy(name: str) -> Strategy | None:
    """Devuelve la estrategia guardada por nombre."""
    return load_strategies().get(name)
