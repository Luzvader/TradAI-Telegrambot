"""
Motor de señales – punto de entrada principal.

Re-exporta las funciones públicas desde los sub-módulos:
  - signals.builders          → helpers internos
  - signals.portfolio_signals → generate_signals_for_portfolio
  - signals.scanner           → scan_opportunities
  - signals.signal_engine     → analyze_ticker (aquí)
"""

import asyncio
import logging
from typing import Any

from config.markets import DEFAULT_TICKER_MARKET, normalize_ticker, split_yfinance_suffix
from config.settings import TRADING212_ANALYSIS_ORIENTED
from data.fundamentals import fetch_fundamentals
from data.technical import get_technical_analysis
from database import repository as repo
from database.models import PortfolioType, StrategyType
from strategy import technical_analyst, price_analyst
from strategy.selector import get_strategy_analyzer

from signals.builders import compute_deterministic_context  # noqa: F401
from signals.portfolio_signals import generate_signals_for_portfolio  # noqa: F401
from signals.scanner import scan_opportunities  # noqa: F401

logger = logging.getLogger(__name__)


async def analyze_ticker(
    ticker: str,
    market: str | None = None,
    portfolio_id: int | None = None,
    strategy: StrategyType | str | None = None,
) -> dict[str, Any]:
    """Análisis completo de un ticker individual."""
    # Validar ticker
    ticker = ticker.strip().upper().replace("$", "")
    if not ticker or len(ticker) > 10:
        return {"ticker": ticker, "error": "Ticker inválido"}

    # Permitir tickers con sufijo yfinance (ej. SAN.MC)
    base, inferred_market = split_yfinance_suffix(ticker)
    ticker = normalize_ticker(base)
    if market is None:
        market = inferred_market
    resolved_market = market or DEFAULT_TICKER_MARKET.get(normalize_ticker(ticker), "NASDAQ")

    if strategy is None:
        if portfolio_id is not None:
            portfolio = await repo.get_portfolio(portfolio_id)
        else:
            portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
        strategy = (
            portfolio.strategy if portfolio and portfolio.strategy else StrategyType.VALUE
        )

    analyzer = get_strategy_analyzer(strategy)

    fd = await asyncio.to_thread(fetch_fundamentals, ticker, resolved_market)
    vs = await asyncio.to_thread(analyzer, fd)

    # Diagnósticos deterministas
    det_context = await compute_deterministic_context(ticker, fd, resolved_market)

    tech_summary = ""
    price_summary = ""
    try:
        ti = await get_technical_analysis(ticker, resolved_market)
        if ti is not None:
            td = technical_analyst.diagnose(
                ti, fd.current_price, fd.high_52w, fd.low_52w, fd.avg_50d, fd.avg_200d,
            )
            tech_summary = td.summary
    except Exception as e:
        logger.debug(f"Error en análisis técnico de {ticker}: {e}")
    try:
        pd_obj = price_analyst.diagnose(fd)
        price_summary = pd_obj.summary
    except Exception as e:
        logger.debug(f"Error en diagnóstico de precio de {ticker}: {e}")

    broker_tradability: dict[str, Any] = {}
    if TRADING212_ANALYSIS_ORIENTED:
        try:
            from broker.bridge import get_trading212_tradability
            broker_tradability = await get_trading212_tradability(ticker)
        except Exception as e:
            logger.debug(f"No se pudo validar {ticker} en Trading212: {e}")
            broker_tradability = {"tradable": None, "reason": str(e)}

    return {
        "ticker": ticker.upper(),
        "market": resolved_market,
        "name": fd.name,
        "sector": fd.sector,
        "price": fd.current_price,
        "signal": vs.signal,
        "overall_score": vs.overall_score,
        "value_score": vs.value_score,
        "quality_score": vs.quality_score,
        "safety_score": vs.safety_score,
        "margin_of_safety": vs.margin_of_safety,
        "pe_ratio": fd.pe_ratio,
        "roe": fd.roe,
        "debt_to_equity": fd.debt_to_equity,
        "dividend_yield": fd.dividend_yield,
        "reasoning": vs.reasoning,
        "strategy": vs.strategy,
        "tech_summary": tech_summary,
        "price_summary": price_summary,
        "deterministic_context": det_context,
        "broker_tradability": broker_tradability,
    }
