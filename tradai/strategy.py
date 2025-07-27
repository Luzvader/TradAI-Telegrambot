from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import pandas as pd
import numpy as np


# Directorios de las estrategias
STRATEGIES_DIR = Path.home() / ".tradai_strategies"
STRATEGY_FILE = Path.home() / ".tradai_strategies.json"


# Funciones de indicadores
def ema(prices: List[float], period: int) -> float:
    """Calcula la EMA (Exponential Moving Average)."""
    return pd.Series(prices).ewm(span=period, adjust=False).mean().iloc[-1]

def rsi(prices: List[float], period: int) -> float:
    """Calcula el RSI (Relative Strength Index)."""
    delta = np.diff(prices)
    gain = delta[delta > 0].sum() / period
    loss = -delta[delta < 0].sum() / period
    rs = gain / loss if loss != 0 else float('inf')
    return 100 - (100 / (1 + rs))

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calcula el ATR (Average True Range) de un dataframe de precios."""
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(window=period).mean()

def detect_candle(df: pd.DataFrame) -> pd.Series:
    """Detecta patrones de velas en un dataframe."""
    conditions = []
    for i in range(1, len(df)):
        open_ = df['open'].iloc[i]
        close = df['close'].iloc[i]
        prev_open = df['open'].iloc[i-1]
        prev_close = df['close'].iloc[i-1]

        # Ejemplo simple: Detecta un patrón de martillo
        if close > open_ and prev_close < prev_open and (close - open_) > (prev_open - prev_close):
            conditions.append('Hammer')
        else:
            conditions.append('None')
    return pd.Series(conditions, index=df.index[1:], dtype="object")


@dataclass
class Estrategia:
    """Estrategia avanzada para criptomonedas utilizando indicadores como EMA, RSI, MACD y ATR."""

    name: str
    symbol: str
    ema_short: int = 20
    ema_long: int = 50
    rsi_period: int = 14
    macd_short: int = 12
    macd_long: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    buy_above_rsi: float = 30
    sell_below_rsi: float = 70

    def evaluate(self, df: pd.DataFrame) -> str:
        """Evalúa señales de compra, venta o mantener basadas en los indicadores."""

        # Calcular los indicadores
        rsi_value = rsi(df['close'].tolist(), self.rsi_period)
        atr_value = atr(df, self.atr_period).iloc[-1]
        ema_short_value = ema(df['close'].tolist(), self.ema_short)
        ema_long_value = ema(df['close'].tolist(), self.ema_long)
        macd_value = ema(df['close'].tolist(), self.macd_short) - ema(df['close'].tolist(), self.macd_long)
        macd_signal_value = ema([macd_value] * self.macd_signal, self.macd_signal)  # simplificado

        # Evaluar las condiciones para comprar o vender
        if rsi_value < self.buy_above_rsi and macd_value > macd_signal_value and df['close'].iloc[-1] > ema_short_value:
            return "BUY"
        if rsi_value > self.sell_below_rsi and macd_value < macd_signal_value and df['close'].iloc[-1] < ema_short_value:
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
        STRATEGY_FILE.write_text(json.dumps(data, indent=2))
        return None

    _ensure_dir()
    if strategy_id is None:
        strategy_id = str(uuid.uuid4())
    path = STRATEGIES_DIR / f"{strategy_id}.json"
    path.write_text(json.dumps(strategy, indent=2))
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
