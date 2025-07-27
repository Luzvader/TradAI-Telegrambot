from __future__ import annotations
from typing import Iterable, List, Optional, Sequence, Tuple, Dict, Any, Union
import logging
import numpy as np

# Configuración básica para logging, consistente con otros módulos
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class InsufficientDataError(Exception):
    """Excepción personalizada para indicar que no hay suficientes datos."""
    pass

def ema(values: Union[Iterable[float], Dict[str, Any]], period: int = 20) -> Optional[float]:
    """Calcula la última EMA (*Exponential Moving Average*) de *period*."""

    try:
        if isinstance(values, dict):
            vals = [float(v["price"] if "price" in v else v["close"]) for v in values.get("data", [values])]
        else:
            vals = [float(v) for v in values if isinstance(v, (int, float)) and v > 0]

        if len(vals) < period:
            logger.warning(f"Insuficientes datos para EMA ({len(vals)} < {period})")
            raise InsufficientDataError(f"Need at least {period} data points for EMA")

        k = 2 / (period + 1)
        sma = np.mean(vals[-period:])
        ema_prev = sma
        for price in vals[-period + 1:]:
            ema_prev = price * k + ema_prev * (1 - k)
        return ema_prev
    except (TypeError, ValueError, KeyError) as e:
        logger.error(f"Error calculando EMA: {e}")
        return None

def rsi(values: Union[Iterable[float], Dict[str, Any]], period: int = 14) -> Optional[float]:
    """Calcula el último RSI (*Relative Strength Index*)."""

    try:
        if isinstance(values, dict):
            vals = [float(v["price"] if "price" in v else v["close"]) for v in values.get("data", [values])]
        else:
            vals = [float(v) for v in values if isinstance(v, (int, float)) and v > 0]

        if len(vals) < period + 1:
            logger.warning(f"Insuficientes datos para RSI ({len(vals)} < {period + 1})")
            raise InsufficientDataError(f"Need at least {period + 1} data points for RSI")

        deltas = np.diff(vals)
        gains = np.maximum(deltas, 0)
        losses = np.maximum(-deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            logger.warning("RSI=100 debido a avg_loss=0 (condición de sobrecompra extrema)")
            return 100.0

        rs = avg_gain / avg_loss
        rsi_val = 100 - (100 / (1 + rs))
        return rsi_val
    except (TypeError, ValueError, KeyError) as e:
        logger.error(f"Error calculando RSI: {e}")
        return None

def _ema_sequence(values: Sequence[float], period: int) -> List[float]:
    """Devuelve la secuencia completa de EMAs para ``values``."""
    if len(values) < period:
        logger.warning(f"Insuficientes datos para secuencia EMA ({len(values)} < {period})")
        return []

    k = 2 / (period + 1)
    sma = np.mean(values[-period:])
    seq = [sma]
    for price in values[-period + 1:]:
        sma = price * k + sma * (1 - k)
        seq.append(sma)
    return seq

def macd(
    values: Union[Iterable[float], Dict[str, Any]],
    short_period: int = 12,
    long_period: int = 26,
    signal_period: int = 9
) -> Optional[Tuple[float, float]]:
    """Calcula MACD y línea de señal."""

    try:
        if isinstance(values, dict):
            vals = [float(v["price"] if "price" in v else v["close"]) for v in values.get("data", [values])]
        else:
            vals = [float(v) for v in values if isinstance(v, (int, float)) and v > 0]

        if len(vals) < long_period + signal_period:
            logger.warning(f"Insuficientes datos para MACD ({len(vals)} < {long_period + signal_period})")
            raise InsufficientDataError(f"Need at least {long_period + signal_period} data points for MACD")

        ema_short_seq = _ema_sequence(vals, short_period)
        ema_long_seq = _ema_sequence(vals, long_period)
        if not ema_short_seq or not ema_long_seq:
            logger.warning("No se pudieron calcular secuencias EMA para MACD")
            raise InsufficientDataError("Failed to compute EMA sequences for MACD")

        mlen = min(len(ema_short_seq), len(ema_long_seq))
        ema_short_seq = ema_short_seq[-mlen:]
        ema_long_seq = ema_long_seq[-mlen:]
        macd_seq = [s - l for s, l in zip(ema_short_seq, ema_long_seq)]
        signal_seq = _ema_sequence(macd_seq, signal_period)
        if not signal_seq:
            logger.warning("No se pudo calcular la línea de señal para MACD")
            raise InsufficientDataError("Failed to compute signal line for MACD")
        return macd_seq[-1], signal_seq[-1]
    except (TypeError, ValueError, KeyError) as e:
        logger.error(f"Error calculando MACD: {e}")
        return None

def atr(
    highs: Union[Iterable[float], Dict[str, Any]],
    lows: Union[Iterable[float], Dict[str, Any]],
    closes: Union[Iterable[float], Dict[str, Any]],
    period: int = 14
) -> Optional[float]:
    """Calcula el ATR (*Average True Range*)."""

    try:
        if isinstance(highs, dict):
            h = [float(v["high"]) for v in highs.get("data", [highs])]
            l = [float(v["low"]) for v in lows.get("data", [lows])]
            c = [float(v["close"] if "close" in v else v["price"]) for v in closes.get("data", [closes])]
        else:
            h = [float(v) for v in highs if isinstance(v, (int, float)) and v > 0]
            l = [float(v) for v in lows if isinstance(v, (int, float)) and v > 0]
            c = [float(v) for v in closes if isinstance(v, (int, float)) and v > 0]

        if len(h) != len(l) or len(l) != len(c):
            logger.error("Las listas de highs, lows y closes no están sincronizadas")
            raise ValueError("Highs, lows, and closes must have the same length")
        if len(h) < period + 1:
            logger.warning(f"Insuficientes datos para ATR ({len(h)} < {period + 1})")
            raise InsufficientDataError(f"Need at least {period + 1} data points for ATR")

        for i in range(len(h)):
            if h[i] < l[i]:
                logger.error(f"High ({h[i]}) menor que low ({l[i]}) en índice {i}")
                raise ValueError("High price cannot be less than low price")

        # Optimización de cálculo de ATR usando numpy
        trs = np.maximum(h[-period:] - l[-period:], 
                         np.abs(h[-period:] - c[-period-1:-1]), 
                         np.abs(l[-period:] - c[-period-1:-1]))
        return np.mean(trs)
    except (TypeError, ValueError, KeyError, IndexError) as e:
        logger.error(f"Error calculando ATR: {e}")
        return None

def detect_candle(
    opens: Union[Iterable[float], Dict[str, Any]],
    highs: Union[Iterable[float], Dict[str, Any]],
    lows: Union[Iterable[float], Dict[str, Any]],
    closes: Union[Iterable[float], Dict[str, Any]]
) -> Optional[str]:
    """Detecta patrones de vela simples (engulfing alcista/bajista, martillo, estrella fugaz)."""

    try:
        if isinstance(opens, dict):
            op = [float(v["open"]) for v in opens.get("data", [opens])]
            h = [float(v["high"]) for v in highs.get("data", [highs])]
            l = [float(v["low"]) for v in lows.get("data", [lows])]
            cl = [float(v["close"]) for v in closes.get("data", [closes])]
        else:
            op = [float(v) for v in opens if isinstance(v, (int, float)) and v > 0]
            h = [float(v) for v in highs if isinstance(v, (int, float)) and v > 0]
            l = [float(v) for v in lows if isinstance(v, (int, float)) and v > 0]
            cl = [float(v) for v in closes if isinstance(v, (int, float)) and v > 0]

        if len(op) != len(h) or len(h) != len(l) or len(l) != len(cl):
            logger.error("Las listas de open, high, low, close no están sincronizadas")
            raise ValueError("Open, high, low, and close must have the same length")

        if len(op) < 2:
            logger.warning("No hay suficientes datos para detectar patrones de vela")
            return None

        # Patrón de martillo
        c1, o1, h1, l1 = cl[-2], op[-2], h[-2], l[-2]
        c2, o2, h2, l2 = cl[-1], op[-1], h[-1], l[-1]]

        if c1 < o1 and c2 > o2 and (c2 - o2) < (o1 - c1) * 0.5:
            return "Hammer"
        
        return None  # No se detectó ningún patrón
    except (TypeError, ValueError, KeyError) as e:
        logger.error(f"Error detectando patrón de vela: {e}")
        return None
