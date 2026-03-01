"""
Módulo de tipos de cambio (FX) entre divisas.

Obtiene tasas de cambio vía yfinance y las cachea con TTL de 2h.
Soporta conversión de cualquier divisa a la moneda base de la cuenta.

Nota especial: GBp (peniques) se trata como GBP/100.
"""

import logging
from typing import Any

import yfinance as yf

from data.cache import TTLCache

logger = logging.getLogger(__name__)

# Caché de tipos de cambio: TTL 2 horas (las tasas FX no cambian mucho)
_fx_cache = TTLCache(default_ttl=7200)

# Pares sintéticos / especiales
_SPECIAL_CONVERSIONS: dict[str, float] = {
    "GBp_GBP": 0.01,   # 100 GBp = 1 GBP
    "GBP_GBp": 100.0,   # 1 GBP = 100 GBp
}


def _get_yfinance_fx_rate(from_ccy: str, to_ccy: str) -> float | None:
    """
    Obtiene tasa de cambio via yfinance (sync, para uso en threads).
    Retorna cuántas unidades de `to_ccy` se obtienen por 1 unidad de `from_ccy`.
    """
    if from_ccy == to_ccy:
        return 1.0

    # Comprobar conversiones especiales
    special_key = f"{from_ccy}_{to_ccy}"
    if special_key in _SPECIAL_CONVERSIONS:
        return _SPECIAL_CONVERSIONS[special_key]

    # Normalizar GBp a GBP para yfinance
    yf_from = "GBP" if from_ccy == "GBp" else from_ccy
    yf_to = "GBP" if to_ccy == "GBp" else to_ccy

    if yf_from == yf_to:
        # Ya son iguales tras normalizar (ej: GBp→GBP con ajuste de factor)
        factor = 1.0
        if from_ccy == "GBp" and to_ccy != "GBp":
            factor = 0.01  # peniques a libras
        elif from_ccy != "GBp" and to_ccy == "GBp":
            factor = 100.0
        return factor

    try:
        pair = f"{yf_from}{yf_to}=X"
        ticker = yf.Ticker(pair)
        data = ticker.history(period="1d")
        if not data.empty:
            rate = float(data["Close"].iloc[-1])
            # Ajustar por GBp si es necesario
            if from_ccy == "GBp":
                rate *= 0.01  # de peniques a la otra moneda
            elif to_ccy == "GBp":
                rate *= 100.0  # de la otra moneda a peniques
            return rate
    except Exception as e:
        logger.debug(f"Error obteniendo FX {from_ccy}→{to_ccy}: {e}")

    # Intentar par inverso
    try:
        pair = f"{yf_to}{yf_from}=X"
        ticker = yf.Ticker(pair)
        data = ticker.history(period="1d")
        if not data.empty:
            rate = 1.0 / float(data["Close"].iloc[-1])
            if from_ccy == "GBp":
                rate *= 0.01
            elif to_ccy == "GBp":
                rate *= 100.0
            return rate
    except Exception as e:
        logger.debug(f"Error obteniendo FX inverso {to_ccy}→{from_ccy}: {e}")

    return None


def get_fx_rate(from_ccy: str, to_ccy: str) -> float:
    """
    Obtiene tasa de cambio cacheada (sync).
    Devuelve cuántas unidades de `to_ccy` se obtienen por 1 `from_ccy`.
    Si no se puede obtener, devuelve 1.0 como fallback seguro.
    """
    if not from_ccy or not to_ccy or from_ccy == to_ccy:
        return 1.0

    cache_key = f"fx:{from_ccy}:{to_ccy}"
    cached = _fx_cache.get(cache_key)
    if cached is not None:
        return cached

    rate = _get_yfinance_fx_rate(from_ccy, to_ccy)
    if rate is None:
        logger.warning(
            f"No se pudo obtener FX {from_ccy}→{to_ccy}, usando 1.0"
        )
        rate = 1.0
        _fx_cache.set(cache_key, rate, ttl=300)  # TTL corto para reintentar
    else:
        _fx_cache.set(cache_key, rate)
        logger.debug(f"💱 FX {from_ccy}→{to_ccy} = {rate:.6f}")

    return rate


def convert_amount(
    amount: float,
    from_ccy: str,
    to_ccy: str,
) -> float:
    """Convierte un importe de una divisa a otra."""
    if not amount or from_ccy == to_ccy:
        return amount
    rate = get_fx_rate(from_ccy, to_ccy)
    return round(amount * rate, 4)


def convert_price(
    price: float | None,
    from_ccy: str | None,
    to_ccy: str | None,
) -> float | None:
    """Convierte un precio de una divisa a otra.
    Devuelve None si el precio es None."""
    if price is None or not from_ccy or not to_ccy or from_ccy == to_ccy:
        return price
    rate = get_fx_rate(from_ccy, to_ccy)
    return round(price * rate, 4)


async def async_get_fx_rate(from_ccy: str, to_ccy: str) -> float:
    """Versión async de get_fx_rate (ejecuta en thread)."""
    import asyncio
    if not from_ccy or not to_ccy or from_ccy == to_ccy:
        return 1.0
    return await asyncio.to_thread(get_fx_rate, from_ccy, to_ccy)


async def async_convert(amount: float, from_ccy: str, to_ccy: str) -> float:
    """Versión async de convert_amount."""
    import asyncio
    return await asyncio.to_thread(convert_amount, amount, from_ccy, to_ccy)


def get_fx_cache_stats() -> dict[str, Any]:
    """Estadísticas del caché FX."""
    return _fx_cache.stats
