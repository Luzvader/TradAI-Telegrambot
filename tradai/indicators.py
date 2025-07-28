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
    """Calcula la última EMA (*Exponential Moving Average*) de *period*.

    Se utiliza el algoritmo estándar iniciando el cálculo desde los primeros
    ``period`` valores. Si los datos son insuficientes se devuelve ``None``.
    """

    try:
        if isinstance(values, dict):
            vals = [float(v["price"] if "price" in v else v["close"]) for v in values.get("data", [values])]
        else:
            vals = [float(v) for v in values]

        if len(vals) < period:
            logger.warning(f"Insuficientes datos para EMA ({len(vals)} < {period})")
            return None

        k = 2 / (period + 1)
        ema_val = float(np.mean(vals[:period]))
        for price in vals[period:]:
            ema_val = price * k + ema_val * (1 - k)
        return ema_val
    except (TypeError, ValueError, KeyError) as e:
        logger.error(f"Error calculando EMA: {e}")
        return None

def rsi(values: Union[Iterable[float], Dict[str, Any]], period: int = 14) -> Optional[float]:
    """Calcula el último RSI (*Relative Strength Index*) usando el método estándar."""

    try:
        if isinstance(values, dict):
            vals = [float(v["price"] if "price" in v else v["close"]) for v in values.get("data", [values])]
        else:
            vals = [float(v) for v in values]

        if len(vals) < period + 1:
            logger.warning(f"Insuficientes datos para RSI ({len(vals)} < {period + 1})")
            return None

        deltas = np.diff(vals)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            logger.warning("RSI=100 debido a avg_loss=0 (condición de sobrecompra extrema)")
            return 100.0

        rs = avg_gain / avg_loss
        rsi_val = 100 - (100 / (1 + rs))
        return rsi_val
    except (TypeError, ValueError, KeyError) as e:
        logger.error(f"Error calculando RSI: {e}")
        return None

def _ema_sequence(values: Sequence[float], period: int) -> Optional[List[float]]:
    """Devuelve la secuencia completa de EMAs para ``values`` usando el algoritmo estándar."""
    if len(values) < period:
        logger.warning(f"Insuficientes datos para secuencia EMA ({len(values)} < {period})")
        return None

    k = 2 / (period + 1)
    ema_val = float(np.mean(values[:period]))
    seq = [ema_val]
    for price in values[period:]:
        ema_val = price * k + ema_val * (1 - k)
        seq.append(ema_val)
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
            vals = [float(v) for v in values]

        ema_short_seq = _ema_sequence(vals, short_period)
        ema_long_seq = _ema_sequence(vals, long_period)
        if ema_short_seq is None or ema_long_seq is None:
            logger.warning("No se pudieron calcular secuencias EMA para MACD")
            return None

        start_short = len(vals) - len(ema_short_seq)
        start_long = len(vals) - len(ema_long_seq)
        start = max(start_short, start_long)

        macd_seq = []
        for i in range(start, len(vals)):
            es = ema_short_seq[i - start_short]
            el = ema_long_seq[i - start_long]
            macd_seq.append(es - el)

        signal_seq = _ema_sequence(macd_seq, signal_period)
        if signal_seq is None:
            logger.warning("No se pudo calcular la línea de señal para MACD")
            return None
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
            h = [float(v) for v in highs]
            l = [float(v) for v in lows]
            c = [float(v) for v in closes]

        if len(h) != len(l) or len(l) != len(c):
            logger.error("Las listas de highs, lows y closes no están sincronizadas")
            raise ValueError("Highs, lows, and closes must have the same length")
        if len(h) < period:
            logger.warning(f"Insuficientes datos para ATR ({len(h)} < {period})")
            return None

        for i in range(len(h)):
            if h[i] < l[i]:
                logger.error(f"High ({h[i]}) menor que low ({l[i]}) en índice {i}")
                raise ValueError("High price cannot be less than low price")

        trs = []
        for i in range(len(h)):
            prev_close = c[i-1] if i > 0 else c[i]
            tr = max(h[i] - l[i], abs(h[i] - prev_close), abs(l[i] - prev_close))
            trs.append(tr)
        return float(np.mean(trs[-period:]))
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

        c1, o1, h1, l1 = cl[-2], op[-2], h[-2], l[-2]
        c2, o2, h2, l2 = cl[-1], op[-1], h[-1], l[-1]
        # Engulfing alcista
        if c1 < o1 and c2 > o2 and c2 >= o1 and o2 <= c1:
            return "bullish_engulfing"

        # Engulfing bajista
        if c1 > o1 and c2 < o2 and c2 <= o1 and o2 >= c1:
            return "bearish_engulfing"

        # Patrón de martillo sencillo
        body = abs(c2 - o2)
        lower_shadow = min(o2, c2) - l2
        upper_shadow = h2 - max(o2, c2)
        if body > 0 and lower_shadow > 2 * body and upper_shadow < body and c2 > o2:
            return "hammer"

        return None  # No se detectó ningún patrón
    except (TypeError, ValueError, KeyError) as e:
        logger.error(f"Error detectando patrón de vela: {e}")
        return None
