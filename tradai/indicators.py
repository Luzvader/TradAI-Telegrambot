"""Funciones de indicadores técnicos sencillos (EMA y RSI).

Se implementan de forma mínima para que puedan reutilizarse tanto desde
el CLI como desde la API web.  Las funciones devuelven ``None`` si la
lista de valores no contiene suficientes datos para calcular el
indicador.
"""
from __future__ import annotations

from typing import Iterable, List, Optional


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
