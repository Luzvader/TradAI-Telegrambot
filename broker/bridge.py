"""
Broker bridge – conecta las operaciones del portfolio_manager con eToro.

Cuando auto_execute está activo:
  • execute_buy → abre posición en eToro (por unidades o por importe)
  • execute_sell → cierra posición en eToro (por positionId)
  • sync_positions → sincroniza posiciones del broker con la BD local

El comportamiento de ejecución estricta se controla con:
  • ETORO_REQUIRE_EXECUTION=true  → broker-first (bloqueante para real)
  • ETORO_REQUIRE_EXECUTION=false → modo tracker (no bloqueante)

NOTA: eToro soporta órdenes por importe (by-amount) y por unidades (by-units).
      Para cerrar posiciones se necesita el positionId, no un SELL genérico.
"""

import logging
from typing import Any

from broker.etoro import (
    EtoroClient,
    get_etoro_client,
)
from broker.base import BrokerResult

logger = logging.getLogger(__name__)
_TRADABILITY_CACHE: dict[str, dict[str, Any]] = {}


def _detect_asset_type(ticker: str):
    """Detecta si un ticker es ETF conocido. Retorna AssetType o None."""
    try:
        from database.models import AssetType
        from strategy.etf_config import get_etf_category_for_ticker
        if get_etf_category_for_ticker(ticker.upper()) is not None:
            return AssetType.ETF
    except Exception:
        pass
    return None


def _check_broker_ready(require_auto_execute: bool = True) -> tuple[EtoroClient | None, str]:
    """Verifica que el broker esté configurado y auto-ejecución activa."""
    client = get_etoro_client()
    if client is None:
        return None, "Broker no configurado"

    from config.settings import ETORO_AUTO_EXECUTE
    if require_auto_execute and not ETORO_AUTO_EXECUTE:
        return None, "Auto-ejecución desactivada (ETORO_AUTO_EXECUTE=false)"

    return client, ""


async def get_etoro_tradability(
    ticker: str,
    market: str | None = None,
) -> dict[str, Any]:
    """
    Comprueba si un ticker es operable en eToro.
    Devuelve un dict compacto para enriquecer análisis y scans.
    """
    tk = ticker.strip().upper()
    market_norm = market.strip().upper() if market else None
    if not tk:
        return {"tradable": False, "reason": "Ticker vacío"}

    cache_key = f"{tk}|{market_norm}" if market_norm else tk
    if cache_key in _TRADABILITY_CACHE:
        return _TRADABILITY_CACHE[cache_key]

    client = get_etoro_client()
    if client is None:
        return {
            "tradable": None,
            "reason": "eToro no inicializado",
        }

    try:
        # Buscar instrumento en eToro
        result = await client.search_instrument(tk)
        if result.success and result.data:
            # Buscar match exacto
            for item in result.data:
                if item.get("symbol", "").upper() == tk:
                    info = {
                        "tradable": item.get("tradable", False) and item.get("buy_enabled", False),
                        "ticker": tk,
                        "instrument_id": item.get("instrument_id"),
                        "name": item.get("name", ""),
                        "type": item.get("type", ""),
                        "current_rate": item.get("current_rate"),
                    }
                    if market_norm:
                        info["requested_market"] = market_norm
                    _TRADABILITY_CACHE[cache_key] = info
                    return info

            # Si no hay match exacto, usar primer resultado
            first = result.data[0]
            info = {
                "tradable": first.get("tradable", False) and first.get("buy_enabled", False),
                "ticker": tk,
                "instrument_id": first.get("instrument_id"),
                "name": first.get("name", ""),
                "type": first.get("type", ""),
                "current_rate": first.get("current_rate"),
                "matched_symbol": first.get("symbol", ""),
            }
            if market_norm:
                info["requested_market"] = market_norm
            _TRADABILITY_CACHE[cache_key] = info
            return info

        info = {
            "tradable": False,
            "ticker": tk,
            "reason": "No encontrado en eToro",
        }
        if market_norm:
            info["requested_market"] = market_norm
        _TRADABILITY_CACHE[cache_key] = info
        return info
    except Exception as e:
        logger.debug(f"Error comprobando tradability de {tk}: {e}")
        info = {"tradable": None, "ticker": tk, "reason": str(e)}
        if market_norm:
            info["requested_market"] = market_norm
        _TRADABILITY_CACHE[cache_key] = info
        return info


async def broker_buy(
    ticker: str,
    shares: float,
    price: float,
    order_type: str = "market",
    limit_price: float | None = None,
    stop_price: float | None = None,
    time_validity: str = "GOOD_TILL_CANCEL",
) -> BrokerResult:
    """
    Ejecuta una compra en el broker conectado (eToro).
    order_type: "market" (por unidades), "amount" (por importe)

    eToro no soporta limit/stop como órdenes separadas.
    Para SL/TP, usar broker_buy_by_amount con parámetros adicionales.
    """
    client, error = _check_broker_ready()
    if client is None:
        return BrokerResult(success=False, error=error)

    try:
        if order_type == "amount":
            result = await client.place_market_order_by_amount(
                ticker, shares,
                stop_loss_rate=stop_price,
                take_profit_rate=limit_price,
            )
        elif order_type in ("limit", "stop", "stop_limit"):
            return BrokerResult(
                success=False,
                error=(
                    f"eToro no soporta órdenes '{order_type}' separadas vía API. "
                    "Usa orden de mercado con SL/TP integrados."
                ),
            )
        else:
            result = await client.place_market_order(ticker, shares, "BUY")

        if result.success:
            logger.info(
                f"✅ Broker BUY ejecutado: {ticker} x{shares} "
                f"[{client.mode.upper()}]"
            )
        else:
            logger.warning(
                f"⚠️ Broker BUY falló para {ticker}: {result.error}"
            )

        return result

    except Exception as e:
        logger.error(f"Error en broker_buy({ticker}): {e}")
        return BrokerResult(success=False, error=str(e))


async def broker_buy_by_amount(
    ticker: str,
    amount: float,
    leverage: int = 1,
    stop_loss_rate: float | None = None,
    take_profit_rate: float | None = None,
) -> BrokerResult:
    """
    Compra por importe en USD (método preferido en eToro para DCA).
    """
    client, error = _check_broker_ready()
    if client is None:
        return BrokerResult(success=False, error=error)

    try:
        result = await client.place_market_order_by_amount(
            ticker, amount, "BUY", leverage,
            stop_loss_rate=stop_loss_rate,
            take_profit_rate=take_profit_rate,
        )
        if result.success:
            logger.info(
                f"✅ Broker BUY (amount) ejecutado: {ticker} ${amount} "
                f"[{client.mode.upper()}]"
            )
        return result
    except Exception as e:
        logger.error(f"Error en broker_buy_by_amount({ticker}): {e}")
        return BrokerResult(success=False, error=str(e))


async def broker_sell(
    ticker: str,
    shares: float,
    price: float,
    order_type: str = "market",
    limit_price: float | None = None,
    stop_price: float | None = None,
    time_validity: str = "GOOD_TILL_CANCEL",
) -> BrokerResult:
    """
    Ejecuta una venta (cierre de posición) en eToro.
    En eToro, vender = cerrar posición por positionId.
    """
    client, error = _check_broker_ready()
    if client is None:
        return BrokerResult(success=False, error=error)

    try:
        result = await client.place_market_order(ticker, shares, "SELL")

        if result.success:
            logger.info(
                f"✅ Broker SELL ejecutado: {ticker} x{shares} "
                f"[{client.mode.upper()}]"
            )
        else:
            logger.warning(
                f"⚠️ Broker SELL falló para {ticker}: {result.error}"
            )

        return result

    except Exception as e:
        logger.error(f"Error en broker_sell({ticker}): {e}")
        return BrokerResult(success=False, error=str(e))


async def broker_cancel_order(order_id: str) -> BrokerResult:
    """Cancela una orden pendiente en el broker."""
    client, error = _check_broker_ready()
    if client is None:
        return BrokerResult(success=False, error=error)

    try:
        return await client.cancel_order(order_id)
    except Exception as e:
        logger.error(f"Error cancelando orden {order_id}: {e}")
        return BrokerResult(success=False, error=str(e))


async def get_broker_status() -> dict[str, Any]:
    """
    Devuelve el estado completo del broker:
    cuenta, posiciones, órdenes pendientes.
    """
    client = get_etoro_client()
    if client is None:
        return {
            "connected": False,
            "error": "Broker no configurado. Añade ETORO_API_KEY y ETORO_USER_KEY en .env",
        }

    from config.settings import ETORO_AUTO_EXECUTE, ETORO_REQUIRE_EXECUTION

    result: dict[str, Any] = {
        "connected": True,
        "broker": "eToro",
        "mode": client.mode,
        "auto_execute": ETORO_AUTO_EXECUTE,
        "require_execution": ETORO_REQUIRE_EXECUTION,
    }

    # Cuenta
    account_result = await client.get_account()
    if account_result.success:
        acc = account_result.data
        result["account"] = {
            "cash": acc.cash,
            "invested": acc.invested,
            "portfolio_value": acc.portfolio_value,
            "pnl": acc.pnl,
            "currency": acc.currency,
        }
    else:
        result["account_error"] = account_result.error

    # Posiciones
    positions_result = await client.get_positions()
    if positions_result.success:
        result["positions"] = [
            {
                "ticker": p.ticker,
                "name": p.frontend_name,
                "shares": p.shares,
                "avg_price": p.avg_price,
                "current_price": p.current_price,
                "pnl": p.pnl,
                "pnl_pct": round(p.pnl_pct, 2),
                "market_value": round(p.market_value, 2),
            }
            for p in positions_result.data
        ]
        result["num_positions"] = len(positions_result.data)
    else:
        result["positions_error"] = positions_result.error

    # Órdenes pendientes
    orders_result = await client.get_orders()
    if orders_result.success:
        result["pending_orders"] = [
            {
                "id": o.order_id,
                "ticker": o.ticker,
                "side": o.side,
                "shares": o.shares,
                "price": o.price,
                "status": o.status,
            }
            for o in orders_result.data
        ]
    else:
        result["orders_error"] = orders_result.error

    return result


async def sync_broker_positions(portfolio_id: int) -> dict[str, Any]:
    """
    Sincroniza las posiciones del broker con la BD local.
    """
    client = get_etoro_client()
    if client is None:
        return {"success": False, "error": "Broker no configurado"}

    from database import repository as repo

    broker_result = await client.get_positions()
    if not broker_result.success:
        return {"success": False, "error": broker_result.error}

    broker_positions = {p.ticker.upper(): p for p in broker_result.data}
    local_positions = list(await repo.get_open_positions(portfolio_id))
    local_map = {p.ticker.upper(): p for p in local_positions}

    only_broker = []
    only_local = []
    mismatched = []
    synced = []

    for ticker, bp in broker_positions.items():
        if ticker in local_map:
            lp = local_map[ticker]
            if abs(bp.shares - lp.shares) > 0.01:
                mismatched.append({
                    "ticker": ticker,
                    "broker_shares": bp.shares,
                    "local_shares": lp.shares,
                    "broker_price": bp.current_price,
                })
            else:
                synced.append(ticker)
        else:
            only_broker.append({
                "ticker": ticker,
                "shares": bp.shares,
                "avg_price": bp.avg_price,
                "current_price": bp.current_price,
            })

    for ticker in local_map:
        if ticker not in broker_positions:
            lp = local_map[ticker]
            only_local.append({
                "ticker": ticker,
                "shares": lp.shares,
                "avg_price": lp.avg_price,
            })

    return {
        "success": True,
        "mode": client.mode,
        "synced": synced,
        "only_broker": only_broker,
        "only_local": only_local,
        "mismatched": mismatched,
        "summary": (
            f"✅ Sincronizadas: {len(synced)} | "
            f"🔵 Solo broker: {len(only_broker)} | "
            f"🟡 Solo local: {len(only_local)} | "
            f"⚠️ Diferencias: {len(mismatched)}"
        ),
    }


async def import_broker_positions(portfolio_id: int) -> dict[str, Any]:
    """
    Importa TODAS las posiciones del broker a la BD local.
    """
    client = get_etoro_client()
    if client is None:
        return {"success": False, "error": "Broker no configurado"}

    from database import repository as repo
    from data.fundamentals import get_sector
    import asyncio

    broker_result = await client.get_positions()
    if not broker_result.success:
        return {"success": False, "error": broker_result.error}

    imported = 0
    updated = 0
    errors = []

    for bp in broker_result.data:
        ticker = bp.ticker.upper()
        try:
            market = "NASDAQ"
            sector = await asyncio.to_thread(get_sector, ticker, market)

            existing = await repo.get_position_by_ticker(
                portfolio_id, ticker, market=market
            )

            if existing is None:
                asset_type = _detect_asset_type(ticker)
                await repo.upsert_position(
                    portfolio_id=portfolio_id,
                    ticker=ticker,
                    market=market,
                    sector=sector,
                    shares=bp.shares,
                    avg_price=bp.avg_price,
                    asset_type=asset_type,
                )
                imported += 1
            else:
                await repo.update_position_price(existing.id, bp.current_price)
                updated += 1

        except Exception as e:
            errors.append(f"{ticker}: {e}")
            logger.error(f"Error importando {ticker}: {e}")

    return {
        "success": True,
        "imported": imported,
        "updated": updated,
        "errors": errors,
        "total": len(broker_result.data),
    }


# ── Funciones de datos del broker ────────────────────────────


async def get_broker_prices() -> dict[str, float]:
    """
    Obtiene precios actuales de todas las posiciones del broker.
    """
    client = get_etoro_client()
    if client is None:
        return {}
    try:
        return await client.get_positions_prices()
    except Exception as e:
        logger.debug(f"Error obteniendo precios del broker: {e}")
        return {}


async def get_broker_account_cash(mode: str | None = None) -> dict[str, Any] | None:
    """
    Obtiene información de la cuenta del broker.
    """
    client = get_etoro_client(mode)
    if client is None:
        return None
    try:
        result = await client.get_account()
        if result.success and result.data:
            acc = result.data
            return {
                "cash": acc.cash,
                "invested": acc.invested,
                "portfolio_value": acc.portfolio_value,
                "pnl": acc.pnl,
                "pnl_pct": acc.pnl_pct,
                "currency": acc.currency,
                "mode": acc.mode,
            }
    except Exception as e:
        logger.debug(f"Error obteniendo cuenta del broker ({mode}): {e}")
    return None


async def sync_cash_from_broker(
    portfolio_id: int, mode: str | None = None,
) -> dict[str, Any]:
    """
    Sincroniza el cash del portfolio local con el cash real del broker.
    """
    client = get_etoro_client(mode)
    if client is None:
        return {"success": False, "error": f"Broker no configurado (modo {mode})"}

    from database import repository as repo

    try:
        result = await client.get_account()
        if not result.success:
            return {"success": False, "error": result.error}

        broker_cash = result.data.cash
        broker_total = result.data.portfolio_value
        portfolio = await repo.get_portfolio(portfolio_id)
        if portfolio is None:
            return {"success": False, "error": "Portfolio no encontrado"}

        old_cash = portfolio.cash or 0
        diff = broker_cash - old_cash

        if abs(diff) > 0.01:
            await repo.set_cash(portfolio_id, broker_cash)
            logger.info(
                f"💰 Cash sincronizado [{client.mode}]: {old_cash:.2f} → {broker_cash:.2f} "
                f"(diff: {diff:+.2f})"
            )

        old_capital = portfolio.initial_capital or 0
        if old_capital == 0 and broker_total > 0:
            await repo.set_initial_capital_only(portfolio_id, broker_total)
            logger.info(
                f"💰 Capital inicial [{client.mode}]: establecido a {broker_total:.2f} "
                f"(portfolio_value del broker)"
            )

        return {
            "success": True,
            "old_cash": round(old_cash, 2),
            "new_cash": round(broker_cash, 2),
            "diff": round(diff, 2),
            "currency": result.data.currency,
            "broker_total": round(broker_total, 2),
            "mode": client.mode,
        }
    except Exception as e:
        logger.error(f"Error sincronizando cash [{mode}]: {e}")
        return {"success": False, "error": str(e)}


async def sync_all_capitals() -> dict[str, Any]:
    """
    Sincroniza el capital desde eToro para ambas carteras:
      REAL  ← eToro real
      BACKTEST ← eToro demo
    """
    from database import repository as repo
    from database.models import PortfolioType
    from broker.etoro import get_available_modes

    results: dict[str, Any] = {}
    mode_portfolio_map = {
        "real": PortfolioType.REAL,
        "demo": PortfolioType.BACKTEST,
    }

    available = get_available_modes()

    for mode, ptype in mode_portfolio_map.items():
        if mode not in available:
            results[mode] = {"skipped": True, "reason": f"Cliente {mode} no inicializado"}
            continue

        portfolio = await repo.get_portfolio_by_type(ptype)
        if portfolio is None:
            results[mode] = {"skipped": True, "reason": f"Portfolio {ptype.value} no existe"}
            continue

        r = await sync_cash_from_broker(portfolio.id, mode=mode)
        results[mode] = r
        if r.get("success"):
            logger.info(
                f"💰 Capital sync [{mode}→{ptype.value}]: "
                f"cash={r['new_cash']:.2f}, total={r.get('broker_total', 0):.2f}"
            )

    return results


async def get_broker_dividend_history(limit: int = 50) -> list[dict[str, Any]]:
    """
    eToro no expone historial de dividendos vía API pública.
    Los dividendos se detectan mediante yfinance.
    """
    return []


async def get_broker_transaction_history(limit: int = 50) -> list[dict[str, Any]]:
    """
    eToro no expone historial de transacciones vía API pública.
    """
    return []
