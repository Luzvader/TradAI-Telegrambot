"""
Escaneo del universo de tickers buscando nuevas oportunidades de compra.
"""

import asyncio
import logging
from typing import Any

from ai.analyst import analyze_with_context
from config.markets import DEFAULT_TICKER_MARKET, normalize_ticker
from data.fundamentals import fetch_fundamentals
from data.market_data import get_current_price
from data.technical import get_technical_analysis
from database import repository as repo
from database.models import PortfolioType, SignalType, StrategyType
from strategy import technical_analyst, price_analyst
from strategy.screener import screen_universe
from strategy.selector import get_strategy_analyzer

from config.settings import SCAN_MIN_SCORE
from config.settings import TRADING212_ANALYSIS_ORIENTED
from signals.builders import compute_deterministic_context, build_signal_justification

logger = logging.getLogger(__name__)


async def scan_opportunities(
    markets: list[str] | None = None,
    min_score: float = SCAN_MIN_SCORE,
    max_results: int = 5,
    portfolio_id: int | None = None,
    strategy: StrategyType | str | None = None,
) -> list[dict[str, Any]]:
    """
    Escanea el universo buscando nuevas oportunidades de compra.
    Devuelve las mejores candidatas con sus scores.
    """
    if strategy is None:
        if portfolio_id is not None:
            portfolio = await repo.get_portfolio(portfolio_id)
        else:
            portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
        strategy = (
            portfolio.strategy if portfolio and portfolio.strategy else StrategyType.VALUE
        )

    top_scores = await screen_universe(
        markets=markets,
        min_score=min_score,
        max_results=max_results,
        strategy=strategy,
    )

    opportunities: list[dict[str, Any]] = []
    for idx, vs in enumerate(top_scores):
        detected_market = vs.market or DEFAULT_TICKER_MARKET.get(normalize_ticker(vs.ticker), "NASDAQ")

        broker_tradability: dict[str, Any] = {}
        if TRADING212_ANALYSIS_ORIENTED:
            try:
                from broker.bridge import get_trading212_tradability

                broker_tradability = await get_trading212_tradability(vs.ticker)
                if broker_tradability.get("tradable") is False:
                    logger.debug(
                        f"Omitiendo {vs.ticker} en scan: no operable en Trading212"
                    )
                    continue
            except Exception as e:
                logger.debug(f"No se pudo validar {vs.ticker} en Trading212: {e}")
                broker_tradability = {"tradable": None, "reason": str(e)}

        # Deduplicación: saltar si ya hay señal BUY reciente
        if await repo.has_recent_signal(vs.ticker, SignalType.BUY, hours=24, market=detected_market):
            logger.debug(f"Señal reciente ya existe para {vs.ticker}, omitiendo oportunidad")
            continue

        ticker_price = await get_current_price(vs.ticker, detected_market)

        # Obtener fundamentales para justificación
        fd = None
        det_context = ""
        tech_diag = None
        price_diag_obj = None
        try:
            fd = await asyncio.to_thread(fetch_fundamentals, vs.ticker, detected_market)
            if fd is not None:
                det_context = await compute_deterministic_context(vs.ticker, fd, detected_market)
                try:
                    ti = await get_technical_analysis(vs.ticker, detected_market)
                    if ti is not None:
                        tech_diag = technical_analyst.diagnose(
                            ti, fd.current_price, fd.high_52w, fd.low_52w, fd.avg_50d, fd.avg_200d,
                        )
                except Exception as e:
                    logger.debug(f"Error en análisis técnico de {vs.ticker}: {e}")
                try:
                    price_diag_obj = price_analyst.diagnose(fd)
                except Exception as e:
                    logger.debug(f"Error en diagnóstico de precio de {vs.ticker}: {e}")
        except Exception as e:
            logger.debug(f"Error obteniendo datos de {vs.ticker}: {e}")

        # Análisis IA solo para las 2 mejores oportunidades BUY (ahorro de tokens)
        ai_summary = None
        if vs.signal == "BUY" and idx < 2:
            try:
                fund_dict = {}
                if fd:
                    fund_dict = {
                        "name": fd.name, "sector": fd.sector,
                        "current_price": fd.current_price, "pe_ratio": fd.pe_ratio,
                        "roe": fd.roe, "debt_to_equity": fd.debt_to_equity,
                        "dividend_yield": fd.dividend_yield,
                        "revenue_growth": fd.revenue_growth,
                    }
                strat_val = strategy.value if isinstance(strategy, StrategyType) else str(strategy)
                ai_text = await analyze_with_context(
                    vs.ticker, detected_market, fund_dict,
                    strategy=strat_val,
                    deterministic_context=det_context,
                )
                ai_summary = ai_text
            except Exception as e:
                logger.warning(f"Error en análisis IA para oportunidad {vs.ticker}: {e}")

        reasoning = build_signal_justification(
            vs, fd=fd, ai_summary=ai_summary,
            tech_diag=tech_diag, price_diag=price_diag_obj,
        )

        sig = await repo.save_signal(
            ticker=vs.ticker,
            market=detected_market,
            signal_type=SignalType.BUY if vs.signal == "BUY" else SignalType.HOLD,
            price=ticker_price,
            value_score=vs.overall_score,
            reasoning=reasoning,
            ai_analysis=ai_summary,
        )

        opportunities.append({
            "signal_id": sig.id,
            "ticker": vs.ticker,
            "signal": vs.signal,
            "price": ticker_price,
            "overall_score": vs.overall_score,
            "value_score": vs.value_score,
            "quality_score": vs.quality_score,
            "safety_score": vs.safety_score,
            "margin_of_safety": vs.margin_of_safety,
            "reasoning": vs.reasoning,
            "justification": reasoning,
            "ai_analysis": ai_summary,
            "strategy": vs.strategy,
            "broker_tradability": broker_tradability,
        })

    return opportunities
