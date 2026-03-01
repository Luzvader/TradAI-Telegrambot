"""
Gestor de portfolio – tracker de operaciones reales.
  • REAL: cartera principal con operaciones reales
  • BACKTEST: cartera virtual para probar estrategias

El usuario indica qué operaciones ha realizado (ticker, acciones, precio)
y el bot las registra, monitoriza y analiza.
Incluye tracking de cash y aprendizaje automático al cerrar posiciones.

Para carteras REAL conectadas a Trading212, usa precios del broker como
fuente primaria (más precisa y sin delay de 15 min vs yfinance).
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from config.markets import MARKET_CURRENCY, get_currency_symbol, format_price
from config.settings import ACCOUNT_CURRENCY
from data.fundamentals import get_sector
from data.fx import get_fx_rate
from data.market_data import get_prices_batch, refresh_broker_prices
from database import repository as repo
from database.models import (
    AssetType,
    OperationOrigin,
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


def _is_known_etf(ticker: str) -> bool:
    """Check if a ticker is a known ETF from the universe.
    Fallback for positions without asset_type set."""
    try:
        from strategy.etf_config import get_etf_category_for_ticker
        return get_etf_category_for_ticker(ticker.upper()) is not None
    except Exception:
        return False


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
    origin: OperationOrigin = OperationOrigin.MANUAL,
    asset_type: AssetType | None = None,
) -> dict[str, Any]:
    """
    Registra una operación de compra.
    Evalúa riesgos (informativo) pero nunca bloquea.
    asset_type: si es ETF, se marca la posición como tal.
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
        origin=origin,
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
        asset_type=asset_type,
    )

    # Descontar cash del portfolio
    await repo.adjust_cash(portfolio_id, -amount_usd)

    logger.info(
        f"🟢 BUY {ticker}: {shares:.4f} acciones a {format_price(price, MARKET_CURRENCY.get(market, 'USD'))} "
        f"(total: {format_price(amount_usd, MARKET_CURRENCY.get(market, 'USD'))})"
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
    origin: OperationOrigin = OperationOrigin.MANUAL,
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
        origin=origin,
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
        f"🔴 SELL {ticker}: {shares:.4f} acciones a {format_price(price, MARKET_CURRENCY.get(market, 'USD'))} "
        f"(PnL: {pnl:+.2f} / {pnl_pct:+.1f}%)"
    )

    # Auto-invocar aprendizaje al cerrar posición
    if is_closing:
        try:
            from ai.learning import analyze_closed_trade
            holding_days = (datetime.now(UTC) - position.opened_at).days if position.opened_at else 0

            # ── Recopilar contexto enriquecido para el aprendizaje ──
            # Dividendos cobrados durante la posición
            total_dividends = 0.0
            try:
                total_dividends = await repo.get_total_dividends(
                    portfolio_id, ticker=ticker
                )
            except Exception as e:
                logger.debug(f"Error obteniendo dividendos de {ticker}: {e}")

            # Contexto de mercado al momento de la entrada
            market_ctx = None
            try:
                if position.opened_at:
                    ctx = await repo.get_market_context_near_date(position.opened_at)
                    if ctx:
                        market_ctx = ctx.summary[:300]
            except Exception as e:
                logger.debug(f"Error obteniendo contexto de mercado para {ticker}: {e}")

            # Indicadores técnicos actuales (momento de venta)
            entry_rsi = None
            entry_macd_signal = None
            try:
                from data.technical import get_technical_analysis
                ti = await get_technical_analysis(ticker, market)
                if ti:
                    entry_rsi = ti.rsi
                    entry_macd_signal = ti.signal if hasattr(ti, "signal") else None
            except Exception as e:
                logger.debug(f"Error obteniendo técnicos de {ticker}: {e}")

            # Score de señal al momento de compra
            entry_score = None
            try:
                analysis = await repo.get_latest_analysis(ticker)
                if analysis:
                    entry_score = analysis.overall_score
            except Exception as e:
                logger.debug(f"Error obteniendo score previo de {ticker}: {e}")

            # Score de diversificación
            div_score = None
            try:
                from strategy.correlation import portfolio_correlation
                positions_all = list(await repo.get_open_positions(portfolio_id))
                if len(positions_all) >= 2:
                    corr_result = await portfolio_correlation(portfolio_id)
                    div_score = corr_result.get("diversification_score")
            except Exception as e:
                logger.debug(f"Error calculando diversificación para {ticker}: {e}")

            # Régimen de mercado
            market_regime = None
            try:
                latest_ctx = await repo.get_latest_context("geopolitical", limit=1)
                if latest_ctx:
                    summary_lower = latest_ctx[0].summary.lower()
                    if any(w in summary_lower for w in ("miedo", "fear", "pánico", "crisis")):
                        market_regime = "fear"
                    elif any(w in summary_lower for w in ("codicia", "greed", "euforia", "rally")):
                        market_regime = "greed"
                    else:
                        market_regime = "neutral"
            except Exception as e:
                logger.debug(f"Error obteniendo régimen de mercado para {ticker}: {e}")

            # Determinar origin de la operación
            origin_str = origin.value if origin else "manual"

            # Obtener estrategia activa
            strategy_used = None
            try:
                strategy_obj = await repo.get_portfolio_strategy(portfolio_id)
                strategy_used = strategy_obj.value if strategy_obj else None
            except Exception as e:
                logger.debug(f"Error obteniendo estrategia del portfolio: {e}")

            asyncio.create_task(
                analyze_closed_trade(
                    ticker=ticker,
                    side="SELL",
                    entry_price=position.avg_price,
                    exit_price=price,
                    holding_days=holding_days,
                    market_context=market_ctx,
                    source="real",
                    strategy_used=strategy_used,
                    origin=origin_str,
                    total_dividends=total_dividends,
                    entry_signal_score=entry_score,
                    entry_rsi=entry_rsi,
                    entry_macd_signal=entry_macd_signal,
                    diversification_score_at_entry=div_score,
                    market_regime=market_regime,
                )
            )
            logger.info(f"🧠 Análisis de aprendizaje lanzado para {ticker} (contexto enriquecido)")
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
    """Genera un resumen completo del portfolio.

    Los precios por posición se muestran en su divisa nativa (market currency).
    Los totales (valor, PnL, cash) se convierten a ACCOUNT_CURRENCY.
    """
    portfolio = await repo.get_portfolio(portfolio_id)
    if portfolio is None:
        return {"error": "Portfolio no encontrado"}

    positions = list(await repo.get_open_positions(portfolio_id))
    acct_ccy = ACCOUNT_CURRENCY

    # Para cartera REAL, refrescar precios T212 antes de usar get_prices_batch
    if portfolio.portfolio_type == PortfolioType.REAL:
        try:
            await refresh_broker_prices()
        except Exception as e:
            logger.debug(f"Error refrescando precios T212: {e}")

    # Actualizar precios (T212 primero, yfinance como fallback)
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
            except Exception as e:
                logger.debug(f"Error actualizando sector de {pos.ticker}: {e}")

    # Pre-calcular FX rates por mercado → ACCOUNT_CURRENCY
    fx_rates: dict[str, float] = {}
    markets_in_use = set(p.market for p in positions)
    for market in markets_in_use:
        native_ccy = MARKET_CURRENCY.get(market, "USD")
        if native_ccy not in fx_rates:
            fx_rates[native_ccy] = await asyncio.to_thread(
                get_fx_rate, native_ccy, acct_ccy
            )

    def _to_acct(amount: float, market: str) -> float:
        """Convierte un importe de la divisa del mercado a ACCOUNT_CURRENCY."""
        native_ccy = MARKET_CURRENCY.get(market, "USD")
        return amount * fx_rates.get(native_ccy, 1.0)

    # Totales en ACCOUNT_CURRENCY
    total_value_acct = 0.0
    total_invested_acct = 0.0
    total_current_acct = 0.0

    # Detalle por posición
    pos_details = []
    for p in positions:
        cur = p.current_price or p.avg_price
        native_ccy = MARKET_CURRENCY.get(p.market, "USD")
        pnl_native = (cur - p.avg_price) * p.shares
        pnl_pct = ((cur - p.avg_price) / p.avg_price * 100) if p.avg_price > 0 else 0

        # Valor en divisa de la cuenta
        val_acct = _to_acct(cur * p.shares, p.market)
        invested_acct = _to_acct(p.avg_price * p.shares, p.market)
        pnl_acct = val_acct - invested_acct

        total_value_acct += val_acct
        total_invested_acct += invested_acct
        total_current_acct += val_acct

        sl_tp = check_stop_loss_take_profit(p)

        pos_details.append({
            "ticker": p.ticker,
            "market": p.market,
            "sector": p.sector,
            "currency": native_ccy,
            "shares": round(p.shares, 4),
            "avg_price": round(p.avg_price, 4),
            "current_price": round(cur, 4),
            "pnl": round(pnl_native, 2),
            "pnl_pct": round(pnl_pct, 2),
            "pnl_acct": round(pnl_acct, 2),
            "value_acct": round(val_acct, 2),
            "weight_pct": 0,  # Se calcula abajo con total
            "stop_loss": p.stop_loss,
            "take_profit": p.take_profit,
            "stop_loss_hit": sl_tp["stop_loss_hit"],
            "take_profit_hit": sl_tp["take_profit_hit"],
        })

    # Calcular pesos con totales
    for pd in pos_details:
        pd["weight_pct"] = round(
            pd["value_acct"] / total_value_acct * 100, 2
        ) if total_value_acct > 0 else 0

    total_pnl_acct = total_current_acct - total_invested_acct
    total_pnl_pct = (
        total_pnl_acct / total_invested_acct * 100
    ) if total_invested_acct > 0 else 0

    # Cash disponible (ya está en ACCOUNT_CURRENCY, viene del broker)
    cash = portfolio.cash or 0
    total_with_cash = total_value_acct + cash

    # Concentración por sector (en ACCOUNT_CURRENCY)
    sector_weights: dict[str, float] = {}
    for pd in pos_details:
        s = pd["sector"] or "Unknown"
        sector_weights[s] = sector_weights.get(s, 0) + pd["value_acct"]

    sector_pcts = {
        s: round(v / total_value_acct * 100, 2) if total_value_acct > 0 else 0
        for s, v in sector_weights.items()
    }

    # ── Desglose stocks vs ETFs ──
    stock_value_acct = 0.0
    etf_value_acct = 0.0
    for pd_item, pos in zip(pos_details, positions):
        is_etf = (
            (hasattr(pos, "asset_type") and pos.asset_type == AssetType.ETF)
            or _is_known_etf(pos.ticker)
        )
        pd_item["asset_type"] = "etf" if is_etf else "stock"
        if is_etf:
            etf_value_acct += pd_item["value_acct"]
        else:
            stock_value_acct += pd_item["value_acct"]

    etf_pct = round(etf_value_acct / total_with_cash * 100, 2) if total_with_cash > 0 else 0
    stock_pct = round(stock_value_acct / total_with_cash * 100, 2) if total_with_cash > 0 else 0

    return {
        "portfolio_name": portfolio.name,
        "portfolio_type": portfolio.portfolio_type.value,
        "account_currency": acct_ccy,
        "total_value": round(total_value_acct, 2),
        "total_with_cash": round(total_with_cash, 2),
        "cash": round(cash, 2),
        "initial_capital": round(portfolio.initial_capital or 0, 2),
        "total_invested": round(total_invested_acct, 2),
        "total_pnl": round(total_pnl_acct, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "num_positions": len(positions),
        "positions": pos_details,
        "sector_weights": sector_pcts,
        # ETF allocation metrics
        "etf_value": round(etf_value_acct, 2),
        "stock_value": round(stock_value_acct, 2),
        "etf_pct": etf_pct,
        "stock_pct": stock_pct,
    }


async def update_all_prices(portfolio_id: int) -> int:
    """Actualiza los precios de todas las posiciones abiertas.
    Para REAL, usa T212 primero (1 llamada) y yfinance como fallback."""
    portfolio = await repo.get_portfolio(portfolio_id)
    positions = list(await repo.get_open_positions(portfolio_id))
    updated = 0

    # Refrescar precios T212 si es cartera REAL
    if portfolio and portfolio.portfolio_type == PortfolioType.REAL:
        try:
            await refresh_broker_prices()
        except Exception:
            pass

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

    # Refrescar T212 para precios más precisos en SL/TP
    portfolio = await repo.get_portfolio(portfolio_id)
    if portfolio and portfolio.portfolio_type == PortfolioType.REAL:
        try:
            await refresh_broker_prices()
        except Exception:
            pass

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
