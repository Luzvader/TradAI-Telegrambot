from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Directory for individual strategy JSON files
STRATEGIES_DIR = Path.home() / ".tradai_strategies"
# File storing simple named strategies
STRATEGY_FILE = Path.home() / ".tradai_strategies.json"


@dataclass
class Estrategia:
    """Estrategia básica basada en reglas de precio."""

    name: str
    buy_above: float | None = None
    sell_below: float | None = None

    def evaluate(self, market_data: Dict[str, Any]) -> str:
        price = market_data.get("price")
        if price is None:
            return "HOLD"
        if self.buy_above is not None and price > self.buy_above:
            return "BUY"
        if self.sell_below is not None and price < self.sell_below:
            return "SELL"
        return "HOLD"


def _ensure_dir() -> None:
    STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)


def _load_all() -> Dict[str, Dict[str, Any]]:
    if not STRATEGY_FILE.exists():
        return {}
    try:
        return json.loads(STRATEGY_FILE.read_text())
    except Exception:
        return {}


def save_strategy(
    strategy: Union[Estrategia, Dict[str, Any]], strategy_id: str | None = None
) -> Optional[str]:
    """Guarda una estrategia.

    - Si ``strategy`` es :class:`Estrategia`, se persiste en :data:`STRATEGY_FILE`
      por nombre y no se devuelve identificador.
    - Si ``strategy`` es ``dict``, se guarda en :data:`STRATEGIES_DIR` y se
      devuelve su ``strategy_id``.
    """

    if isinstance(strategy, Estrategia):
        data = _load_all()
        data[strategy.name] = asdict(strategy)
        STRATEGY_FILE.write_text(json.dumps(data))
        return None

    _ensure_dir()
    if strategy_id is None:
        strategy_id = str(uuid.uuid4())
    path = STRATEGIES_DIR / f"{strategy_id}.json"
    path.write_text(json.dumps(strategy))
    return strategy_id


def load_strategy(identifier: str) -> Union[Estrategia, Dict[str, Any], None]:
    """Carga una estrategia por ``identifier``.

    Se intenta primero buscar un archivo en :data:`STRATEGIES_DIR` usando el
    identificador. Si no existe se busca una estrategia por nombre en
    :data:`STRATEGY_FILE`.
    """

    path = STRATEGIES_DIR / f"{identifier}.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return None

    data = _load_all()
    cfg = data.get(identifier)
    if not cfg:
        return None
    return Estrategia(**cfg)


def list_strategies() -> List[str]:
    """Devuelve los identificadores de estrategias almacenadas en
    :data:`STRATEGIES_DIR`."""

    if not STRATEGIES_DIR.exists():
        return []
    return [p.stem for p in STRATEGIES_DIR.glob("*.json")]


def delete_strategy(strategy_id: str) -> bool:
    """Elimina la estrategia identificada por ``strategy_id``."""

    path = STRATEGIES_DIR / f"{strategy_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False
