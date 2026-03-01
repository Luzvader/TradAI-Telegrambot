"""
Screener de acciones – filtra el universo de acciones
para encontrar candidatos según la estrategia activa.

El universo de tickers se obtiene dinámicamente de los índices
bursátiles (S&P 500, DAX 40, CAC 40, FTSE MIB, FTSE 100, IBEX 35)
a través del módulo data.ticker_discovery.
"""

import asyncio
import logging
from typing import Any

from data.fundamentals import fetch_fundamentals
from data.ticker_discovery import get_tickers_for_market, get_supported_markets
from database.models import StrategyType
from strategy.score import StrategyScore
from strategy.selector import get_strategy_analyzer
from config.settings import YFINANCE_MAX_CONCURRENCY

logger = logging.getLogger(__name__)


# Tickers personalizados añadidos por el usuario (en memoria)
_custom_tickers: dict[str, list[str]] = {}


async def screen_universe(
    markets: list[str] | None = None,
    min_score: float = 60.0,
    max_results: int = 10,
    strategy: StrategyType | str | None = None,
) -> list[StrategyScore]:
    """
    Analiza todo el universo de acciones y devuelve las mejores
    oportunidades según estrategia, ordenadas por score.

    Los tickers se descubren dinámicamente de los índices bursátiles.
    """
    if markets is None:
        markets = get_supported_markets()

    analyzer = get_strategy_analyzer(strategy)
    all_scores: list[StrategyScore] = []
    sem = asyncio.Semaphore(max(1, int(YFINANCE_MAX_CONCURRENCY)))

    async def _analyze_one(t: str, m: str) -> StrategyScore | None:
        try:
            async with sem:
                fd = await asyncio.to_thread(fetch_fundamentals, t, m)
                vs = await asyncio.to_thread(analyzer, fd)
                vs.market = m  # Propagar mercado de origen
                vs.fundamentals = fd  # Cachear para evitar doble fetch en scanner
            return vs if vs.overall_score >= min_score else None
        except Exception as e:
            logger.warning(f"Error analizando {t}: {e}")
            return None

    # Recopilar todos los tickers de todos los mercados y luego analizar en paralelo
    all_tasks = []
    for market in markets:
        # Descubrimiento dinámico de tickers
        tickers = await get_tickers_for_market(market)
        # Añadir tickers custom del usuario
        tickers = list(set(tickers + _custom_tickers.get(market, [])))
        logger.info(f"🔍 Screening {market}: {len(tickers)} tickers...")

        all_tasks.extend(_analyze_one(t, market) for t in tickers)

    results = await asyncio.gather(*all_tasks)
    all_scores.extend(vs for vs in results if vs is not None)

    # Ordenar por score descendente
    all_scores.sort(key=lambda x: x.overall_score, reverse=True)

    top = all_scores[:max_results]
    logger.info(
        f"📋 Screening completado: {len(all_scores)} candidatos sobre "
        f"{min_score} score, mostrando top {len(top)}"
    )
    return top


async def analyze_single(
    ticker: str,
    market: str | None = None,
    strategy: StrategyType | str | None = None,
) -> StrategyScore:
    """Análisis de un ticker individual."""
    fd = await asyncio.to_thread(fetch_fundamentals, ticker, market)
    analyzer = get_strategy_analyzer(strategy)
    return await asyncio.to_thread(analyzer, fd)


async def quick_scan(
    tickers: list[str],
    strategy: StrategyType | str | None = None,
) -> list[dict[str, Any]]:
    """Escaneo rápido: price + P/E + señal para una lista (paralelizado)."""
    analyzer = get_strategy_analyzer(strategy)
    sem = asyncio.Semaphore(max(1, int(YFINANCE_MAX_CONCURRENCY)))

    async def _scan_one(ticker: str) -> dict[str, Any] | None:
        try:
            async with sem:
                fd = await asyncio.to_thread(fetch_fundamentals, ticker)
                vs = await asyncio.to_thread(analyzer, fd)
            return {
                "ticker": ticker.upper(),
                "price": fd.current_price,
                "pe": fd.pe_ratio,
                "sector": fd.sector,
                "score": vs.overall_score,
                "signal": vs.signal,
                "strategy": vs.strategy,
            }
        except Exception as e:
            logger.warning(f"Error en quick_scan de {ticker}: {e}")
            return None

    results = await asyncio.gather(*[_scan_one(t) for t in tickers])
    return [r for r in results if r is not None]
