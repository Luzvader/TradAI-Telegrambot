"""Funciones de indicadores técnicos sencillos (EMA y RSI).

Se implementan de forma mínima para que puedan reutilizarse tanto desde
el CLI como desde la API web.  Las funciones devuelven ``None`` si la
lista de valores no contiene suficientes datos para calcular el
indicador.
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple


def ema(values: Iterable[float], period: int = 20) -> Optional[float]:
    """Calcula la última EMA (*Exponential Moving Average*) de *period*.

    Parameters
    ----------
    values: Iterable[float]
        Una secuencia de precios de cierre.  Se utilizarán los últimos
        ``period`` elementos.
    period: int, default ``20``
        El número de periodos sobre el que calcular la media.

    Returns
    -------
    float | None
        El valor de la EMA o ``None`` si no hay suficientes datos.
    """

    vals: List[float] = list(values)
    if len(vals) < period:
        return None

    k = 2 / (period + 1)
    # Usamos la SMA inicial de los primeros *period* valores como punto de partida
    sma = sum(vals[:period]) / period
    ema_prev = sma
    for price in vals[period:]:
        ema_prev = price * k + ema_prev * (1 - k)
    return ema_prev


def rsi(values: Iterable[float], period: int = 14) -> Optional[float]:
    """Calcula el último RSI (*Relative Strength Index*).

    Parameters
    ----------
    values: Iterable[float]
        Secuencia de precios de cierre.  Se necesitan al menos ``period`` + 1
        valores.
    period: int, default ``14``
        Periodo del RSI.

    Returns
    -------
    float | None
        Valor de RSI (0-100) o ``None`` si no hay suficientes datos.
    """

    vals: List[float] = list(values)
    if len(vals) < period + 1:
        return None

    gains = []
    losses = []
    for i in range(1, period + 1):
        delta = vals[i] - vals[i - 1]
        if delta >= 0:
            gains.append(delta)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(-delta)

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val


def _ema_sequence(values: Sequence[float], period: int) -> List[float]:
    """Devuelve la secuencia completa de EMAs para ``values``."""

    if len(values) < period:
        return []

    k = 2 / (period + 1)
    ema_prev = sum(values[:period]) / period
    seq = [ema_prev]
    for price in values[period:]:
        ema_prev = price * k + ema_prev * (1 - k)
        seq.append(ema_prev)
    return seq


def macd(
    values: Iterable[float],
    short_period: int = 12,
    long_period: int = 26,
    signal_period: int = 9,
) -> Optional[Tuple[float, float]]:
    """Calcula MACD y línea de señal.

    Parameters
    ----------
    values:
        Precios de cierre.
    short_period:
        Periodo para la EMA corta.
    long_period:
        Periodo para la EMA larga.
    signal_period:
        Periodo para la línea de señal.

    Returns
    -------
    (float, float) | None
        Tupla ``(macd, signal)`` o ``None`` si no hay suficientes datos.
    """

    vals = list(values)
    if len(vals) < long_period + signal_period:
        return None

    ema_short_seq = _ema_sequence(vals, short_period)
    ema_long_seq = _ema_sequence(vals, long_period)
    mlen = min(len(ema_short_seq), len(ema_long_seq))
    if mlen == 0:
        return None

    ema_short_seq = ema_short_seq[-mlen:]
    ema_long_seq = ema_long_seq[-mlen:]
    macd_seq = [s - l for s, l in zip(ema_short_seq, ema_long_seq)]
    signal_seq = _ema_sequence(macd_seq, signal_period)
    if not signal_seq:
        return None
    return macd_seq[-1], signal_seq[-1]


def atr(
    highs: Iterable[float],
    lows: Iterable[float],
    closes: Iterable[float],
    period: int = 14,
) -> Optional[float]:
    """Calcula el ATR (*Average True Range*).

    Se requieren ``period`` + 1 valores para obtener ``period`` rangos
    verdaderos.
    """

    h = list(highs)
    l = list(lows)
    c = list(closes)
    if min(len(h), len(l), len(c)) < period + 1:
        return None

    trs = []
    for i in range(-period, 0):
        tr = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        trs.append(tr)
    return sum(trs) / period


def detect_candle(
    opens: Iterable[float],
    highs: Iterable[float],
    lows: Iterable[float],
    closes: Iterable[float],
) -> Optional[str]:
    """Detecta patrones de vela simples (engulfing alcista/bajista)."""

    op = list(opens)
    cl = list(closes)
    if len(op) < 2 or len(cl) < 2:
        return None

    o1, c1 = op[-2], cl[-2]
    o2, c2 = op[-1], cl[-1]

    if c1 < o1 and c2 > o2 and c2 >= o1 and o2 <= c1:
        return "bullish_engulfing"
    if c1 > o1 and c2 < o2 and c2 <= o1 and o2 >= c1:
        return "bearish_engulfing"
    return None
