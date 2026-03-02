"""
Generación de señales para posiciones abiertas de un portfolio.
Comprueba stop-loss, take-profit y reevalúa score según estrategia.
"""

import asyncio
import logging
from typing import Any

from ai.analyst import analyze_with_context
from data.fundamentals import fetch_fundamentals
from data.market_data import get_current_price
from data.technical import get_technical_analysis
from database import repository as repo
from database.models import AssetType, SignalType, StrategyType
from strategy import technical_analyst, price_analyst
from strategy.etf_config import get_etf_category_for_ticker
from strategy.risk_manager import check_stop_loss_take_profit
from strategy.score import StrategyScore
from strategy.selector import get_strategy_analyzer

from config.settings import SIGNAL_BUY_THRESHOLD, SIGNAL_SELL_THRESHOLD
from signals.builders import compute_deterministic_context, build_signal_justification

logger = logging.getLogger(__name__)


async def generate_signals_for_portfolio(
    portfolio_id: int,
    skip_dedup: bool = False,
) -> list[dict[str, Any]]:
    """
    Genera señales para todas las posiciones abiertas del portfolio.
    Comprueba stop-loss, take-profit y reevalúa el score según la estrategia.

    Args:
        portfolio_id: ID del portfolio.
        skip_dedup: Si True, omite la deduplicación de señales recientes.
                    Útil cuando se llama desde el modo automático para que
                    siempre obtenga señales accionables.
    """
    portfolio = await repo.get_portfolio(portfolio_id)
    strategy = (
        portfolio.strategy if portfolio and portfolio.strategy else StrategyType.VALUE
    )
    analyzer = get_strategy_analyzer(strategy)

    positions = list(await repo.get_open_positions(portfolio_id))
    signals: list[dict[str, Any]] = []

    for pos in positions:
        try:
            # ETFs se gestionan por el sistema de asignación ETF, no por señales de stock
            is_etf = (
                getattr(pos, "asset_type", None) == AssetType.ETF
                or get_etf_category_for_ticker(pos.ticker) is not None
            )
            if is_etf:
                logger.debug(f"Posición ETF {pos.ticker} omitida (gestionada por ETF allocator)")
                continue

            # Actualizar precio (ahora async)
            price = await get_current_price(pos.ticker, pos.market)
            if price is not None:
                await repo.update_position_price(pos.id, price)
                pos.current_price = price

            # Deduplicación: si ya hay señal reciente (24h) para este ticker, saltar
            # Nota: comprobamos señales de cualquier tipo para no saturar
            if not skip_dedup:
                recent_sell = await repo.has_recent_signal(
                    pos.ticker, SignalType.SELL, hours=24, market=pos.market
                )
                recent_hold = await repo.has_recent_signal(
                    pos.ticker, SignalType.HOLD, hours=24, market=pos.market
                )
                if recent_sell or recent_hold:
                    logger.debug(f"Señal reciente ya existe para {pos.ticker}, omitiendo")
                    continue

            # Check stop-loss / take-profit
            sl_tp = check_stop_loss_take_profit(pos)
            if sl_tp["stop_loss_hit"]:
                _sl_score = StrategyScore(
                    ticker=pos.ticker, strategy="", value_score=0,
                    quality_score=0, safety_score=0, overall_score=0,
                    margin_of_safety=None, reasoning=[],
                )
                reasoning = build_signal_justification(_sl_score, sl_tp=sl_tp)
                sig = await repo.save_signal(
                    ticker=pos.ticker,
                    market=pos.market,
                    signal_type=SignalType.SELL,
                    price=pos.current_price,
                    reasoning=f"🔴 STOP-LOSS alcanzado. PnL: {sl_tp['pnl_pct']}%\n{reasoning}",
                )
                signals.append({
                    "signal_id": sig.id,
                    "ticker": pos.ticker,
                    "market": pos.market,
                    "type": "SELL",
                    "reason": "STOP-LOSS",
                    "price": pos.current_price,
                    "pnl_pct": sl_tp["pnl_pct"],
                })
                continue

            if sl_tp["take_profit_hit"]:
                _tp_score = StrategyScore(
                    ticker=pos.ticker, strategy="", value_score=100,
                    quality_score=100, safety_score=100, overall_score=100,
                    margin_of_safety=None, reasoning=[],
                )
                reasoning = build_signal_justification(_tp_score, sl_tp=sl_tp)
                sig = await repo.save_signal(
                    ticker=pos.ticker,
                    market=pos.market,
                    signal_type=SignalType.SELL,
                    price=pos.current_price,
                    reasoning=f"🟢 TAKE-PROFIT alcanzado. PnL: {sl_tp['pnl_pct']}%\n{reasoning}",
                )
                signals.append({
                    "signal_id": sig.id,
                    "ticker": pos.ticker,
                    "market": pos.market,
                    "type": "SELL",
                    "reason": "TAKE-PROFIT",
                    "price": pos.current_price,
                    "pnl_pct": sl_tp["pnl_pct"],
                })
                continue

            # Re-evaluar score value
            fd = await asyncio.to_thread(fetch_fundamentals, pos.ticker, pos.market)
            if fd is None or fd.current_price is None:
                logger.debug(f"Sin datos fundamentales para {pos.ticker}, omitiendo")
                continue
            vs = await asyncio.to_thread(analyzer, fd)

            # Diagnósticos deterministas (técnico + precio)
            det_context = await compute_deterministic_context(pos.ticker, fd, pos.market)
            tech_diag = None
            price_diag_obj = None
            try:
                ti = await get_technical_analysis(pos.ticker, pos.market)
                if ti is not None:
                    tech_diag = technical_analyst.diagnose(
                        ti, fd.current_price, fd.high_52w, fd.low_52w, fd.avg_50d, fd.avg_200d,
                    )
            except Exception as e:
                logger.debug(f"Error en análisis técnico de {pos.ticker}: {e}")
            try:
                price_diag_obj = price_analyst.diagnose(fd)
            except Exception as e:
                logger.debug(f"Error en diagnóstico de precio de {pos.ticker}: {e}")

            signal_type = SignalType.HOLD
            if vs.overall_score <= SIGNAL_SELL_THRESHOLD:
                signal_type = SignalType.SELL
            else:
                pnl = sl_tp.get("pnl_pct")
                if vs.overall_score >= SIGNAL_BUY_THRESHOLD and pnl is not None and pnl < -5:
                    signal_type = SignalType.HOLD  # Score alto pero en pérdidas, mantener

            # Obtener análisis IA solo para señales de VENTA (ahorro de tokens)
            # HOLD no necesita análisis IA; BUY en posiciones existentes no debería ocurrir
            ai_summary = None
            if signal_type == SignalType.SELL:
                try:
                    strat_str = strategy.value if isinstance(strategy, StrategyType) else str(strategy)
                    ai_text = await analyze_with_context(
                        pos.ticker,
                        pos.market,
                        {
                            "name": fd.name, "sector": fd.sector,
                            "current_price": fd.current_price, "pe_ratio": fd.pe_ratio,
                            "roe": fd.roe, "debt_to_equity": fd.debt_to_equity,
                        },
                        strategy=strat_str,
                        deterministic_context=det_context,
                    )
                    ai_summary = ai_text
                except Exception as e:
                    logger.warning(f"Error en análisis IA para señal {pos.ticker}: {e}")

            reasoning = build_signal_justification(
                vs, fd=fd, sl_tp=sl_tp, ai_summary=ai_summary,
                tech_diag=tech_diag, price_diag=price_diag_obj,
            )
            sig = await repo.save_signal(
                ticker=pos.ticker,
                market=pos.market,
                signal_type=signal_type,
                price=pos.current_price,
                value_score=vs.overall_score,
                reasoning=reasoning,
                ai_analysis=ai_summary,
            )

            signals.append({
                "signal_id": sig.id,
                "ticker": pos.ticker,
                "market": pos.market,
                "type": signal_type.value,
                "price": pos.current_price,
                "overall_score": vs.overall_score,
                "score": vs.overall_score,
                "margin_of_safety": vs.margin_of_safety,
                "pnl_pct": sl_tp.get("pnl_pct"),
                "reasoning": reasoning,
                "strategy": vs.strategy,
            })

        except Exception as e:
            logger.error(f"Error generando señal para {pos.ticker}: {e}")

    return signals
