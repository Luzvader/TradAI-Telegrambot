from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List

from .indicators import ema, macd

from .indicators import rsi, atr, detect_candle
import pandas as pd

def generate_signals(df: pd.DataFrame, symbol: str) -> list:
    """Genera señales usando EMA, RSI, MACD, ATR y patrones de vela."""
    signals = []
    for i in range(1, len(df)):
        # Verifica que los indicadores estén presentes
        if (
            pd.notna(df['rsi'].iloc[i]) and
            pd.notna(df['atr'].iloc[i]) and
            'candle_pattern' in df.columns and pd.notna(df['candle_pattern'].iloc[i])
        ):
            buy_cond = (
                df['close'].iloc[i] > df['ema'].iloc[i] and
                df['close'].iloc[i-1] <= df['ema'].iloc[i-1] and
                df['rsi'].iloc[i] < 30 and
                df['macd'].iloc[i] > df['macd_signal'].iloc[i] and
                df['atr'].iloc[i] < df['atr'].mean() and
                df['candle_pattern'].iloc[i] in ['Hammer', 'bullish_engulfing']
            )
            sell_cond = (
                df['close'].iloc[i] < df['ema'].iloc[i] and
                df['close'].iloc[i-1] >= df['ema'].iloc[i-1] and
                df['rsi'].iloc[i] > 70 and
                df['macd'].iloc[i] < df['macd_signal'].iloc[i] and
                df['atr'].iloc[i] > df['atr'].mean() and
                df['candle_pattern'].iloc[i] in ['Bearish Engulfing', 'bearish_engulfing']
            )
            if buy_cond:
                signals.append("BUY")
            elif sell_cond:
                signals.append("SELL")
            else:
                signals.append("HOLD")
        else:
            signals.append("HOLD")
    return signals

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


@dataclass
class MACDStrategy:
    """Estrategia basada en el cruce MACD/señal."""

    name: str
    symbol: str
    short_period: int = 12
    long_period: int = 26
    signal_period: int = 9

    def evaluate(self, prices: List[float]) -> str:
        result = macd(
            prices,
            short_period=self.short_period,
            long_period=self.long_period,
            signal_period=self.signal_period,
        )
        if result is None:
            return "HOLD"
        macd_val, signal_val = result
        return "BUY" if macd_val > signal_val else "SELL"


def load_strategies() -> Dict[str, Strategy]:
    """Carga las estrategias guardadas de forma robusta."""
    if not STRATEGIES_FILE.exists():
        return {}
    try:
        content = STRATEGIES_FILE.read_text()
        if not content.strip():
            return {}
        data = json.loads(content)
        if not isinstance(data, dict):
            return {}
        return {name: Strategy(**cfg) for name, cfg in data.items() if isinstance(cfg, dict)}
    except Exception as e:
        print(f"Error cargando estrategias: {e}")
        return {}


def save_strategy(strategy: Strategy) -> None:
    """Persiste una estrategia en el archivo configurado."""
    strategies = {name: asdict(s) for name, s in load_strategies().items()}
    strategies[strategy.name] = asdict(strategy)
    STRATEGIES_FILE.write_text(json.dumps(strategies, indent=2, ensure_ascii=False))


def get_strategy(name: str) -> Strategy | None:
    """Devuelve la estrategia guardada por nombre."""
    return load_strategies().get(name)


def delete_strategy(name: str) -> bool:
    """Elimina una estrategia guardada por nombre."""
    strategies = load_strategies()
    if name in strategies:
        del strategies[name]
        STRATEGIES_FILE.write_text(json.dumps({n: asdict(s) for n, s in strategies.items()}, indent=2, ensure_ascii=False))
        return True
    return False
