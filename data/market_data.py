"""
Obtención de datos de mercado en tiempo real y históricos con yfinance.
Todas las llamadas a yfinance se ejecutan en thread pool para no
bloquear el event loop asyncio.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

import yfinance as yf
from zoneinfo import ZoneInfo

from config.markets import (
    MARKETS,
    MarketSchedule,
    get_yfinance_ticker,
    DEFAULT_TICKER_MARKET,
)
from config.settings import YFINANCE_MAX_CONCURRENCY
from data.cache import price_cache, ticker_info_cache

logger = logging.getLogger(__name__)


def is_market_open(market_key: str) -> bool:
    """Comprueba si el mercado está abierto ahora mismo (incluye festivos)."""
    schedule = MARKETS.get(market_key)
    if schedule is None:
        return False
    now = datetime.now(schedule.tz)
    if now.weekday() not in schedule.trading_days:
        return False

    # Comprobar festivos con exchange_calendars si está disponible
    try:
        import exchange_calendars as xcals
        _exchange_map = {
            "NASDAQ": "XNYS",  # exchange_calendars usa XNYS para US
            "NYSE": "XNYS",
            "IBEX": "XMAD",
            "LSE": "XLON",
            "XETRA": "XFRA",
            "EURONEXT_PARIS": "XPAR",
            "BORSA_ITALIANA": "XMIL",
            "EURONEXT_AMSTERDAM": "XAMS",
        }
        exc_code = _exchange_map.get(market_key)
        if exc_code:
            cal = xcals.get_calendar(exc_code)
            today = now.date()
            import pandas as pd
            ts = pd.Timestamp(today)
            if not cal.is_session(ts):
                return False
    except ImportError:
        pass  # exchange_calendars no instalado, solo usar día de semana
    except Exception:
        pass  # Cualquier error, fallback a solo día de semana

    market_open = now.replace(
        hour=schedule.open_hour, minute=schedule.open_minute, second=0
    )
    market_close = now.replace(
        hour=schedule.close_hour, minute=schedule.close_minute, second=0
    )
    return market_open <= now <= market_close


def get_open_markets() -> list[str]:
    """Devuelve lista de mercados actualmente abiertos."""
    return [k for k in MARKETS if is_market_open(k)]


def _sync_get_current_price(ticker: str, market: str | None = None) -> float | None:
    """Obtiene el precio actual de un ticker (sync)."""
    cache_key = f"price:{ticker.upper()}:{market or 'auto'}"
    cached = price_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        yf_ticker = get_yfinance_ticker(ticker, market)
        stock = yf.Ticker(yf_ticker)
        data = stock.history(period="1d")
        if data.empty:
            return None
        price = round(float(data["Close"].iloc[-1]), 4)
        price_cache.set(cache_key, price)
        return price
    except Exception as e:
        logger.error(f"Error obteniendo precio de {ticker}: {e}")
        return None


async def get_current_price(ticker: str, market: str | None = None) -> float | None:
    """Obtiene el precio actual de un ticker (async, no bloquea el event loop)."""
    return await asyncio.to_thread(_sync_get_current_price, ticker, market)


async def get_prices_batch(
    tickers: list[str],
    market: str | None = None,
    max_concurrency: int | None = None,
) -> dict[str, float]:
    """Obtiene precios actuales para una lista de tickers (con concurrencia limitada)."""
    prices: dict[str, float] = {}
    tickers = [t.upper() for t in tickers]

    limit = max_concurrency if max_concurrency is not None else YFINANCE_MAX_CONCURRENCY
    sem = asyncio.Semaphore(max(1, int(limit)))

    async def _one(ticker: str) -> float | None:
        async with sem:
            return await get_current_price(ticker, market)

    tasks = [_one(t) for t in tickers]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for ticker, result in zip(tickers, results):
        if isinstance(result, (int, float)) and result is not None:
            prices[ticker] = float(result)
    return prices


def _sync_get_historical_data(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
    market: str | None = None,
) -> Any:
    """Obtiene datos históricos de un ticker (sync)."""
    try:
        yf_ticker = get_yfinance_ticker(ticker, market)
        stock = yf.Ticker(yf_ticker)
        return stock.history(period=period, interval=interval)
    except Exception as e:
        logger.error(f"Error obteniendo histórico de {ticker}: {e}")
        return None


async def get_historical_data(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
    market: str | None = None,
) -> Any:
    """Obtiene datos históricos de un ticker (async).

    Args:
        ticker: Símbolo del ticker
        period: Período (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
        interval: Intervalo (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
        market: Mercado (opcional)

    Returns:
        DataFrame con datos OHLCV
    """
    return await asyncio.to_thread(
        _sync_get_historical_data, ticker, period, interval, market
    )


def _sync_get_ticker_info(ticker: str, market: str | None = None) -> dict[str, Any]:
    """Obtiene información completa de un ticker (sync)."""
    cache_key = f"info:{ticker.upper()}:{market or 'auto'}"
    cached = ticker_info_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        yf_ticker = get_yfinance_ticker(ticker, market)
        stock = yf.Ticker(yf_ticker)
        info = stock.info
        result = {
            "ticker": ticker.upper(),
            "name": info.get("longName", "N/A"),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "market_cap": info.get("marketCap"),
            "currency": info.get("currency", "USD"),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "pb_ratio": info.get("priceToBook"),
            "ps_ratio": info.get("priceToSalesTrailing12Months"),
            "dividend_yield": info.get("dividendYield"),
            "roe": info.get("returnOnEquity"),
            "roa": info.get("returnOnAssets"),
            "debt_to_equity": info.get("debtToEquity"),
            "free_cash_flow": info.get("freeCashflow"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "profit_margins": info.get("profitMargins"),
            "operating_margins": info.get("operatingMargins"),
            "beta": info.get("beta"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "50d_avg": info.get("fiftyDayAverage"),
            "200d_avg": info.get("twoHundredDayAverage"),
            "target_mean_price": info.get("targetMeanPrice"),
            "recommendation": info.get("recommendationKey"),
        }
        ticker_info_cache.set(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"Error obteniendo info de {ticker}: {e}")
        return {"ticker": ticker.upper(), "error": str(e)}


async def get_ticker_info(ticker: str, market: str | None = None) -> dict[str, Any]:
    """Obtiene información completa de un ticker (async, no bloquea event loop)."""
    return await asyncio.to_thread(_sync_get_ticker_info, ticker, market)


def get_tickers_for_market(market_key: str) -> list[str]:
    """Devuelve tickers conocidos para un mercado dado.

    Usa el mapeo estático como referencia rápida. Para descubrimiento
    completo, usar data.ticker_discovery.get_tickers_for_market().
    """
    return [
        t for t, m in DEFAULT_TICKER_MARKET.items() if m == market_key
    ]
