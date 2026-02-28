"""
Broker bridge – conecta las operaciones del portfolio_manager con Trading212.

Cuando auto_execute está activo:
  • execute_buy → coloca orden de compra en Trading212
  • execute_sell → coloca orden de venta en Trading212
  • sync_positions → sincroniza posiciones del broker con la BD local

El comportamiento de ejecución estricta se controla con:
  • TRADING212_REQUIRE_EXECUTION=true  → broker-first (bloqueante para real)
  • TRADING212_REQUIRE_EXECUTION=false → modo tracker (no bloqueante)

NOTE: Value orders (comprar por importe) no están soportadas por la API
      de Trading212. Solo se soportan órdenes por cantidad (QUANTITY).
"""

import logging
from typing import Any

from broker.trading212 import Trading212Client, get_trading212_client
from broker.base import BrokerResult

logger = logging.getLogger(__name__)
_TRADABILITY_CACHE: dict[str, dict[str, Any]] = {}


def _check_broker_ready(require_auto_execute: bool = True) -> tuple[Trading212Client | None, str]:
    """Verifica que el broker esté configurado y auto-ejecución activa."""
    client = get_trading212_client()
    if client is None:
        return None, "Broker no configurado"

    from config.settings import TRADING212_AUTO_EXECUTE
    if require_auto_execute and not TRADING212_AUTO_EXECUTE:
        return None, "Auto-ejecución desactivada (TRADING212_AUTO_EXECUTE=false)"

    return client, ""


async def get_trading212_tradability(ticker: str) -> dict[str, Any]:
    """
    Comprueba si un ticker es operable en Trading212.
    Devuelve un dict compacto para enriquecer análisis y scans.
    """
    tk = ticker.strip().upper()
    if not tk:
        return {"tradable": False, "reason": "Ticker vacío"}

    if tk in _TRADABILITY_CACHE:
        return _TRADABILITY_CACHE[tk]

    client = get_trading212_client()
    if client is None:
        return {
            "tradable": None,
            "reason": "Trading212 no inicializado",
        }

    try:
        result = await client.get_instrument_by_ticker(tk)
        if result.success and result.data:
            inst = result.data
            info = {
                "tradable": True,
                "ticker": tk,
                "instrument_ticker": inst.get("ticker_t212", inst.get("ticker", tk)),
                "name": inst.get("name", ""),
                "currency": inst.get("currency", ""),
            }
            _TRADABILITY_CACHE[tk] = info
            return info

        info = {
            "tradable": False,
            "ticker": tk,
            "reason": result.error or "No encontrado en Trading212",
        }
        _TRADABILITY_CACHE[tk] = info
        return info
    except Exception as e:
        logger.debug(f"Error comprobando tradability de {tk}: {e}")
        info = {"tradable": None, "ticker": tk, "reason": str(e)}
        _TRADABILITY_CACHE[tk] = info
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
    Ejecuta una compra en el broker conectado (Trading212).
    order_type: "market", "limit", "stop", "stop_limit"
    """
    client, error = _check_broker_ready()
    if client is None:
        return BrokerResult(success=False, error=error)

    try:
        if order_type == "limit" and limit_price is not None:
            result = await client.place_limit_order(
                ticker, shares, "BUY", limit_price, time_validity
            )
        elif order_type == "stop" and stop_price is not None:
            result = await client.place_stop_order(
                ticker, shares, "BUY", stop_price, time_validity
            )
        elif order_type == "stop_limit" and stop_price is not None and limit_price is not None:
            result = await client.place_stop_limit_order(
                ticker, shares, "BUY", stop_price, limit_price, time_validity
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
    Ejecuta una venta en el broker conectado (Trading212).
    order_type: "market", "limit", "stop", "stop_limit"
    """
    client, error = _check_broker_ready()
    if client is None:
        return BrokerResult(success=False, error=error)

    try:
        if order_type == "limit" and limit_price is not None:
            result = await client.place_limit_order(
                ticker, shares, "SELL", limit_price, time_validity
            )
        elif order_type == "stop" and stop_price is not None:
            result = await client.place_stop_order(
                ticker, shares, "SELL", stop_price, time_validity
            )
        elif order_type == "stop_limit" and stop_price is not None and limit_price is not None:
            result = await client.place_stop_limit_order(
                ticker, shares, "SELL", stop_price, limit_price, time_validity
            )
        else:
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
    client = get_trading212_client()
    if client is None:
        return {
            "connected": False,
            "error": "Broker no configurado. Añade TRADING212_API_KEY y API_SECRET en .env",
        }

    from config.settings import TRADING212_AUTO_EXECUTE, TRADING212_REQUIRE_EXECUTION

    result: dict[str, Any] = {
        "connected": True,
        "mode": client.mode,
        "auto_execute": TRADING212_AUTO_EXECUTE,
        "require_execution": TRADING212_REQUIRE_EXECUTION,
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
    Compara posiciones de Trading212 con las de TradAI y muestra diferencias.
    """
    client = get_trading212_client()
    if client is None:
        return {"success": False, "error": "Broker no configurado"}

    from database import repository as repo

    # Obtener posiciones del broker
    broker_result = await client.get_positions()
    if not broker_result.success:
        return {"success": False, "error": broker_result.error}

    broker_positions = {p.ticker.upper(): p for p in broker_result.data}

    # Obtener posiciones locales
    local_positions = list(await repo.get_open_positions(portfolio_id))
    local_map = {p.ticker.upper(): p for p in local_positions}

    # Comparar
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
    Crea posiciones nuevas y actualiza existentes.
    """
    client = get_trading212_client()
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
            # Obtener sector
            sector = await asyncio.to_thread(get_sector, ticker, "NASDAQ")

            # Check si ya existe
            existing = await repo.get_position_by_ticker(
                portfolio_id, ticker
            )

            if existing is None:
                # Crear nueva posición
                await repo.upsert_position(
                    portfolio_id=portfolio_id,
                    ticker=ticker,
                    market="NASDAQ",
                    sector=sector,
                    shares=bp.shares,
                    avg_price=bp.avg_price,
                )
                imported += 1
            else:
                # Actualizar precio
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
