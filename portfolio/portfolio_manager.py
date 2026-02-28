"""
Gestor de portfolio – tracker de operaciones reales.
  • REAL: cartera principal con operaciones reales
  • BACKTEST: cartera virtual para probar estrategias

El usuario indica qué operaciones ha realizado (ticker, acciones, precio)
y el bot las registra, monitoriza y analiza.
Incluye tracking de cash y aprendizaje automático al cerrar posiciones.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from data.fundamentals import get_sector
from data.market_data import get_prices_batch
from database import repository as repo
from database.models import (
    OperationSide,
    Portfolio,
    PortfolioType,
    Position,
)
from strategy.risk_manager import (
    RiskCheck,
    calculate_portfolio_value,
    check_risk,
    check_stop_loss_take_profit,
)

logger = logging.getLogger(__name__)


async def init_portfolios() -> dict[str, Portfolio]:
    """Inicializa las dos carteras al arrancar."""
    real = await repo.get_or_create_portfolio(
        name="Principal", ptype=PortfolioType.REAL
    )
    backtest = await repo.get_or_create_portfolio(
        name="Backtest", ptype=PortfolioType.BACKTEST
    )
    logger.info("📁 Portfolios inicializados: Principal + Backtest")
    return {"real": real, "backtest": backtest}


async def execute_buy(
    portfolio_id: int,
    ticker: str,
    price: float,
    shares: float,
    market: str = "NASDAQ",
    notes: str | None = None,
) -> dict[str, Any]:
    """
    Registra una operación de compra.
    Evalúa riesgos (informativo) pero nunca bloquea.
    """
    portfolio = await repo.get_portfolio(portfolio_id)
    if portfolio is None:
        return {"success": False, "error": "Portfolio no encontrado"}

    positions = list(await repo.get_open_positions(portfolio_id))
    sector = await asyncio.to_thread(get_sector, ticker, market)

    amount_usd = round(shares * price, 2)

    # Evaluar riesgos (informativo)
    risk = check_risk(positions, ticker, sector, amount_usd, price)

    # ── Ejecutar primero en broker para cartera REAL ──
    broker_info = {}
    if portfolio.portfolio_type == PortfolioType.REAL:
        from config.settings import TRADING212_REQUIRE_EXECUTION

        try:
            from broker.bridge import broker_buy
            broker_result = await broker_buy(ticker, shares, price)
            if broker_result.success:
                order = broker_result.data
                if order is not None:
                    shares = abs(order.filled_shares or order.shares or shares)
                    if shares <= 0:
                        shares = abs(shares)
                    price = float(order.filled_price or order.price or price)
                    amount_usd = round(shares * price, 2)
                broker_info = {
                    "broker_executed": True,
                    "broker_order": order.order_id if order else None,
                }
            else:
                broker_info = {
                    "broker_executed": False,
                    "broker_note": broker_result.error,
                }
                if TRADING212_REQUIRE_EXECUTION:
                    return {
                        "success": False,
                        "error": f"Trading212 rechazó la compra: {broker_result.error}",
                        "risk_warnings": risk.warnings,
                        **broker_info,
                    }
        except Exception as e:
            broker_info = {"broker_executed": False, "broker_note": str(e)}
            if TRADING212_REQUIRE_EXECUTION:
                return {
                    "success": False,
                    "error": f"Error ejecutando compra en Trading212: {e}",
                    "risk_warnings": risk.warnings,
                    **broker_info,
                }

    # Registrar operación
    op = await repo.record_operation(
        portfolio_id=portfolio_id,
        ticker=ticker,
        market=market,
        side=OperationSide.BUY,
        price=price,
        amount_usd=amount_usd,
        shares=shares,
        notes=notes,
    )

    # Actualizar/crear posición
    await repo.upsert_position(
        portfolio_id=portfolio_id,
        ticker=ticker,
        market=market,
        sector=sector,
        shares=shares,
        avg_price=price,
        stop_loss=risk.suggested_stop_loss,
        take_profit=risk.suggested_take_profit,
    )

    # Descontar cash del portfolio
    await repo.adjust_cash(portfolio_id, -amount_usd)

    logger.info(
        f"🟢 BUY {ticker}: {shares:.4f} acciones a {price}$ "
        f"(total: {amount_usd}$)"
    )

    return {
        "success": True,
        "operation_id": op.id,
        "ticker": ticker,
        "shares": shares,
        "price": price,
        "amount": amount_usd,
        "stop_loss": risk.suggested_stop_loss,
        "take_profit": risk.suggested_take_profit,
        "risk_warnings": risk.warnings,
        **broker_info,
    }


async def execute_sell(
    portfolio_id: int,
    ticker: str,
    price: float,
    shares_to_sell: float,
    market: str = "NASDAQ",
    notes: str | None = None,
) -> dict[str, Any]:
    """
    Registra una operación de venta.
    """
    portfolio = await repo.get_portfolio(portfolio_id)
    if portfolio is None:
        return {"success": False, "error": "Portfolio no encontrado"}

    position = await repo.get_position_by_ticker(portfolio_id, ticker, market=market)
    if position is None:
        return {"success": False, "error": f"No hay posición abierta en {ticker}"}

    shares = min(shares_to_sell, position.shares)
    amount = round(shares * price, 2)

    # ── Ejecutar primero en broker para cartera REAL ──
    broker_info = {}
    if portfolio.portfolio_type == PortfolioType.REAL:
        from config.settings import TRADING212_REQUIRE_EXECUTION

        try:
            from broker.bridge import broker_sell
            broker_result = await broker_sell(ticker, shares, price)
            if broker_result.success:
                order = broker_result.data
                if order is not None:
                    broker_shares = abs(order.filled_shares or order.shares or shares)
                    if broker_shares > 0:
                        shares = min(broker_shares, position.shares)
                    broker_price = float(order.filled_price or order.price or price)
                    if broker_price > 0:
                        price = broker_price
                    amount = round(shares * price, 2)
                broker_info = {
                    "broker_executed": True,
                    "broker_order": order.order_id if order else None,
                }
            else:
                broker_info = {
                    "broker_executed": False,
                    "broker_note": broker_result.error,
                }
                if TRADING212_REQUIRE_EXECUTION:
                    return {
                        "success": False,
                        "error": f"Trading212 rechazó la venta: {broker_result.error}",
                        **broker_info,
                    }
        except Exception as e:
            broker_info = {"broker_executed": False, "broker_note": str(e)}
            if TRADING212_REQUIRE_EXECUTION:
                return {
                    "success": False,
                    "error": f"Error ejecutando venta en Trading212: {e}",
                    **broker_info,
                }

    # Registrar operación
    op = await repo.record_operation(
        portfolio_id=portfolio_id,
        ticker=ticker,
        market=market,
        side=OperationSide.SELL,
        price=price,
        amount_usd=amount,
        shares=shares,
        notes=notes,
    )

    # Actualizar posición
    remaining = position.shares - shares
    is_closing = remaining <= 0.0001
    if is_closing:
        await repo.close_position(position.id)
    else:
        await repo.upsert_position(
            portfolio_id=portfolio_id,
            ticker=ticker,
            market=market,
            sector=position.sector,
            shares=-shares,
            avg_price=position.avg_price,
        )

    # Sumar cash al portfolio
    await repo.adjust_cash(portfolio_id, amount)

    pnl = (price - position.avg_price) * shares
    pnl_pct = ((price - position.avg_price) / position.avg_price * 100) if position.avg_price > 0 else 0

    logger.info(
        f"🔴 SELL {ticker}: {shares:.4f} acciones a {price}$ "
        f"(PnL: {pnl:+.2f}$ / {pnl_pct:+.1f}%)"
    )

    # Auto-invocar aprendizaje al cerrar posición
    if is_closing:
        try:
            from ai.learning import analyze_closed_trade
            holding_days = (datetime.now(UTC) - position.opened_at).days if position.opened_at else 0
            asyncio.create_task(
                analyze_closed_trade(
                    ticker=ticker,
                    side="SELL",
                    entry_price=position.avg_price,
                    exit_price=price,
                    holding_days=holding_days,
                )
            )
            logger.info(f"🧠 Análisis de aprendizaje lanzado para {ticker}")
        except Exception as e:
            logger.warning(f"Error lanzando aprendizaje para {ticker}: {e}")

    return {
        "success": True,
        "operation_id": op.id,
        "ticker": ticker,
        "shares_sold": shares,
        "price": price,
        "amount": amount,
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        **broker_info,
    }


async def get_portfolio_summary(portfolio_id: int) -> dict[str, Any]:
    """Genera un resumen completo del portfolio."""
    portfolio = await repo.get_portfolio(portfolio_id)
    if portfolio is None:
        return {"error": "Portfolio no encontrado"}

    positions = list(await repo.get_open_positions(portfolio_id))

    # Actualizar precios
    tickers_by_market: dict[str, list[str]] = {}
    for pos in positions:
        tickers_by_market.setdefault(pos.market, []).append(pos.ticker)

    prices_by_market: dict[str, dict[str, float]] = {}
    for market, tickers in tickers_by_market.items():
        prices_by_market[market] = await get_prices_batch(tickers, market=market)

    for pos in positions:
        price = prices_by_market.get(pos.market, {}).get(pos.ticker.upper())
        if price is not None:
            await repo.update_position_price(pos.id, price)
            pos.current_price = price

    # Rellenar sectores faltantes (posiciones antiguas sin sector)
    for pos in positions:
        if pos.sector is None or pos.sector in ("N/A", "Unknown", ""):
            try:
                sector = await asyncio.to_thread(get_sector, pos.ticker, pos.market)
                if sector and sector not in ("Unknown", "N/A", ""):
                    pos.sector = sector
                    await repo.update_position_sector(pos.id, sector)
            except Exception:
                pass

    total_value = calculate_portfolio_value(positions)
    total_invested = sum(p.avg_price * p.shares for p in positions)
    total_current = sum(
        (p.current_price or p.avg_price) * p.shares for p in positions
    )
    total_pnl = total_current - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0

    # Cash disponible
    cash = portfolio.cash or 0
    total_with_cash = total_value + cash

    # Detalle por posición
    pos_details = []
    for p in positions:
        cur = p.current_price or p.avg_price
        pnl = (cur - p.avg_price) * p.shares
        pnl_pct = ((cur - p.avg_price) / p.avg_price * 100) if p.avg_price > 0 else 0
        weight = (cur * p.shares / total_value * 100) if total_value > 0 else 0

        sl_tp = check_stop_loss_take_profit(p)

        pos_details.append({
            "ticker": p.ticker,
            "market": p.market,
            "sector": p.sector,
            "shares": round(p.shares, 4),
            "avg_price": round(p.avg_price, 4),
            "current_price": round(cur, 4),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "weight_pct": round(weight, 2),
            "stop_loss": p.stop_loss,
            "take_profit": p.take_profit,
            "stop_loss_hit": sl_tp["stop_loss_hit"],
            "take_profit_hit": sl_tp["take_profit_hit"],
        })

    # Concentración por sector
    sector_weights: dict[str, float] = {}
    for p in positions:
        s = p.sector or "Unknown"
        val = (p.current_price or p.avg_price) * p.shares
        sector_weights[s] = sector_weights.get(s, 0) + val

    sector_pcts = {
        s: round(v / total_value * 100, 2) if total_value > 0 else 0
        for s, v in sector_weights.items()
    }

    return {
        "portfolio_name": portfolio.name,
        "portfolio_type": portfolio.portfolio_type.value,
        "total_value": round(total_value, 2),
        "total_with_cash": round(total_with_cash, 2),
        "cash": round(cash, 2),
        "initial_capital": round(portfolio.initial_capital or 0, 2),
        "total_invested": round(total_invested, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "num_positions": len(positions),
        "positions": pos_details,
        "sector_weights": sector_pcts,
    }


async def update_all_prices(portfolio_id: int) -> int:
    """Actualiza los precios de todas las posiciones abiertas."""
    positions = list(await repo.get_open_positions(portfolio_id))
    updated = 0
    tickers_by_market: dict[str, list[str]] = {}
    for pos in positions:
        tickers_by_market.setdefault(pos.market, []).append(pos.ticker)

    prices_by_market: dict[str, dict[str, float]] = {}
    for market, tickers in tickers_by_market.items():
        prices_by_market[market] = await get_prices_batch(tickers, market=market)

    for pos in positions:
        price = prices_by_market.get(pos.market, {}).get(pos.ticker.upper())
        if price is not None:
            await repo.update_position_price(pos.id, price)
            updated += 1
    return updated


async def check_alerts(portfolio_id: int) -> list[dict[str, Any]]:
    """Comprueba alertas de stop-loss y take-profit."""
    positions = list(await repo.get_open_positions(portfolio_id))
    alerts = []

    tickers_by_market: dict[str, list[str]] = {}
    for pos in positions:
        tickers_by_market.setdefault(pos.market, []).append(pos.ticker)

    prices_by_market: dict[str, dict[str, float]] = {}
    for market, tickers in tickers_by_market.items():
        prices_by_market[market] = await get_prices_batch(tickers, market=market)

    for pos in positions:
        price = prices_by_market.get(pos.market, {}).get(pos.ticker.upper())
        if price is not None:
            await repo.update_position_price(pos.id, price)
            pos.current_price = price

        sl_tp = check_stop_loss_take_profit(pos)
        if sl_tp["stop_loss_hit"]:
            alerts.append({
                "type": "🔴 STOP-LOSS",
                "ticker": pos.ticker,
                "current_price": pos.current_price,
                "stop_loss": pos.stop_loss,
                "pnl_pct": sl_tp["pnl_pct"],
            })
        if sl_tp["take_profit_hit"]:
            alerts.append({
                "type": "🟢 TAKE-PROFIT",
                "ticker": pos.ticker,
                "current_price": pos.current_price,
                "take_profit": pos.take_profit,
                "pnl_pct": sl_tp["pnl_pct"],
            })

    return alerts
