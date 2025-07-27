import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List
from abc import ABC, abstractmethod
import pandas as pd

from .indicators import ema, macd, rsi, atr, detect_candle

# Configuración de logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Ruta del archivo de estrategias
STRATEGIES_FILE = Path.home() / ".tradai_strategies.json"

# Función para generar señales usando múltiples indicadores
def generate_signals(df: pd.DataFrame, symbol: str) -> list:
    """Genera señales usando EMA, RSI, MACD, ATR y patrones de vela."""
    signals = []
    atr_mean = df['atr'].mean()  # Precalcular ATR
    for i in range(1, len(df)):
        # Condiciones intermedias
        rsi_cond = pd.notna(df['rsi'].iloc[i])
        atr_cond = pd.notna(df['atr'].iloc[i])
        candle_cond = 'candle_pattern' in df.columns and pd.notna(df['candle_pattern'].iloc[i])
        
        if rsi_cond and atr_cond and candle_cond:
            candle_pattern = df['candle_pattern'].iloc[i].lower()  # Normalizar el patrón
            buy_cond = (
                df['close'].iloc[i] > df['ema'].iloc[i] and
                df['close'].iloc[i-1] <= df['ema'].iloc[i-1] and
                df['rsi'].iloc[i] < 30 and
                df['macd'].iloc[i] > df['macd_signal'].iloc[i] and
                df['atr'].iloc[i] < atr_mean and
                candle_pattern in ['hammer', 'bullish_engulfing']
            )
            sell_cond = (
                df['close'].iloc[i] < df['ema'].iloc[i] and
                df['close'].iloc[i-1] >= df['ema'].iloc[i-1] and
                df['rsi'].iloc[i] > 70 and
                df['macd'].iloc[i] < df['macd_signal'].iloc[i] and
                df['atr'].iloc[i] > atr_mean and
                candle_pattern in ['bearish_engulfing', 'bearish engulfing']
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


# Clase base para las estrategias
class BaseStrategy(ABC):
    """Clase base para todas las estrategias."""
    
    @abstractmethod
    def evaluate(self, prices: List[float]) -> str:
        """Evalúa una estrategia y devuelve BUY, SELL o HOLD."""
        pass


@dataclass
class EMAStrategy(BaseStrategy):
    """Estrategia basada en dos EMAs."""
    
    name: str
    symbol: str
    ema_short: int = 20
    ema_long: int = 50

    def evaluate(self, prices: List[float]) -> str:
        short = ema(prices, self.ema_short)
        long = ema(prices, self.ema_long)
        if short is None or long is None:
            return "HOLD"
        return "BUY" if short > long else "SELL"


# Alias simple para compatibilidad con la API y los tests
@dataclass
class Strategy(EMAStrategy):
    """Estrategia por defecto basada en dos EMAs."""
    pass


@dataclass
class MACDStrategy(BaseStrategy):
    """Estrategia basada en el cruce de MACD y la señal."""
    
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

# Estrategias predeterminadas incluidas en el paquete
DEFAULT_STRATEGIES = [
    EMAStrategy(name="ema_default", symbol="BTC"),
    MACDStrategy(name="macd_default", symbol="BTC"),
]

def list_default_strategies() -> List[BaseStrategy]:
    """Devuelve las estrategias incluidas de forma predeterminada."""
    return DEFAULT_STRATEGIES

# Alias de compatibilidad para versiones antiguas
# 'Strategy' solía ser la estrategia EMA por defecto
Strategy = EMAStrategy


# Cargar las estrategias desde un archivo JSON
def load_strategies() -> Dict[str, BaseStrategy]:
    """Carga las estrategias guardadas desde el archivo JSON."""
    if not STRATEGIES_FILE.exists() or STRATEGIES_FILE.stat().st_size == 0:
        return {}
    
    try:
        with open(STRATEGIES_FILE, 'r', encoding='utf-8') as file:
            data = json.load(file)
            return {name: Strategy(**cfg) for name, cfg in data.items() if isinstance(cfg, dict)}
    except json.JSONDecodeError as e:
        logger.error(f"Error decodificando el archivo JSON de estrategias: {e}")
        return {}
    except OSError as e:
        logger.error(f"Error al leer el archivo de estrategias: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error desconocido al cargar las estrategias: {e}")
        return {}


# Guardar una estrategia en el archivo
def save_strategy(strategy: BaseStrategy) -> None:
    """Guarda una estrategia en el archivo configurado."""
    try:
        strategies = load_strategies()
        strategies[strategy.name] = asdict(strategy)
        with open(STRATEGIES_FILE, 'w', encoding='utf-8') as file:
            json.dump(strategies, file, indent=2, ensure_ascii=False)
        logger.info(f"Estrategia '{strategy.name}' guardada correctamente.")
    except Exception as e:
        logger.error(f"Error al guardar la estrategia '{strategy.name}': {e}")


# Obtener una estrategia por su nombre
def get_strategy(name: str) -> BaseStrategy | None:
    """Devuelve una estrategia guardada por nombre."""
    return load_strategies().get(name)


# Eliminar una estrategia por su nombre
def delete_strategy(name: str) -> bool:
    """Elimina una estrategia guardada por nombre."""
    strategies = load_strategies()
    if name in strategies:
        del strategies[name]
        try:
            with open(STRATEGIES_FILE, 'w', encoding='utf-8') as file:
                json.dump({n: asdict(s) for n, s in strategies.items()}, file, indent=2, ensure_ascii=False)
            logger.info(f"Estrategia '{name}' eliminada correctamente.")
            return True
        except Exception as e:
            logger.error(f"Error al eliminar la estrategia '{name}': {e}")
            return False
    return False
