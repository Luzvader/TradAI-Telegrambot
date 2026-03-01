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
from datetime import datetime, UTC
from typing import Any

from broker.trading212 import (
    MARKET_EXCHANGE_MAP,
    Trading212Client,
    get_trading212_client,
)
from broker.base import BrokerResult

logger = logging.getLogger(__name__)
_TRADABILITY_CACHE: dict[str, dict[str, Any]] = {}
_CATALOG_REFRESHED_ON_MISS = False


def _check_broker_ready(require_auto_execute: bool = True) -> tuple[Trading212Client | None, str]:
    """Verifica que el broker esté configurado y auto-ejecución activa."""
    client = get_trading212_client()
    if client is None:
        return None, "Broker no configurado"

    from config.settings import TRADING212_AUTO_EXECUTE
    if require_auto_execute and not TRADING212_AUTO_EXECUTE:
        return None, "Auto-ejecución desactivada (TRADING212_AUTO_EXECUTE=false)"

    return client, ""


def _tradability_cache_key(ticker: str, market: str | None = None) -> str:
    tk = ticker.strip().upper()
    mkt = (market or "").strip().upper()
    return f"{tk}|{mkt}" if mkt else tk


def _select_best_t212_match(
    ticker: str,
    candidates: list[dict[str, Any]],
    market: str | None = None,
) -> dict[str, Any] | None:
    """Selecciona el mejor candidato de Trading212 para un ticker/mercado."""
    if not candidates:
        return None

    tk = ticker.strip().upper()
    mkt = (market or "").strip().upper()
    preferred_suffix = MARKET_EXCHANGE_MAP.get(mkt, "")

    def _clean(value: Any) -> str:
        return str(value or "").strip().upper()

    if preferred_suffix:
        for inst in candidates:
            clean = _clean(inst.get("ticker"))
            t212 = _clean(inst.get("ticker_t212"))
            if clean == tk and t212.endswith(preferred_suffix):
                return inst

    for inst in candidates:
        if _clean(inst.get("ticker")) == tk:
            return inst

    if preferred_suffix:
        for inst in candidates:
            clean = _clean(inst.get("ticker"))
            t212 = _clean(inst.get("ticker_t212"))
            if t212.endswith(preferred_suffix) and (
                clean.startswith(tk) or tk in clean or tk in t212
            ):
                return inst
        for inst in candidates:
            if _clean(inst.get("ticker_t212")).endswith(preferred_suffix):
                return inst

    for inst in candidates:
        clean = _clean(inst.get("ticker"))
        t212 = _clean(inst.get("ticker_t212"))
        if tk in clean or tk in t212:
            return inst

    return candidates[0]


def _build_tradability_info(
    ticker: str,
    inst: dict[str, Any],
    market: str | None = None,
) -> dict[str, Any]:
    info: dict[str, Any] = {
        "tradable": True,
        "ticker": ticker,
        "instrument_ticker": inst.get("ticker_t212", ticker),
        "name": inst.get("name", ""),
        "type": inst.get("type", ""),
        "currency": inst.get("currency", ""),
        "isin": inst.get("isin", ""),
    }
    if market:
        info["requested_market"] = market
    return info


async def get_trading212_tradability(
    ticker: str,
    market: str | None = None,
) -> dict[str, Any]:
    """
    Comprueba si un ticker es operable en Trading212.
    Usa catálogo cacheado para máxima eficiencia.
    Devuelve un dict compacto para enriquecer análisis y scans.
    """
    tk = ticker.strip().upper()
    market_norm = market.strip().upper() if market else None
    if not tk:
        return {"tradable": False, "reason": "Ticker vacío"}

    cache_key = _tradability_cache_key(tk, market_norm)
    if cache_key in _TRADABILITY_CACHE:
        return _TRADABILITY_CACHE[cache_key]

    client = get_trading212_client()
    if client is None:
        return {
            "tradable": None,
            "reason": "Trading212 no inicializado",
        }

    global _CATALOG_REFRESHED_ON_MISS
    try:
        inst = await client.get_instrument_info(tk)

        if inst is None:
            search = await client.search_instrument(tk)
            if search.success and search.data:
                inst = _select_best_t212_match(tk, search.data, market_norm)

        if inst is None and not _CATALOG_REFRESHED_ON_MISS:
            await client.get_all_instruments(force_refresh=True)
            _CATALOG_REFRESHED_ON_MISS = True

            inst = await client.get_instrument_info(tk)
            if inst is None:
                search = await client.search_instrument(tk)
                if search.success and search.data:
                    inst = _select_best_t212_match(tk, search.data, market_norm)

        if inst:
            info = _build_tradability_info(tk, inst, market_norm)
            _TRADABILITY_CACHE[cache_key] = info
            return info

        info = {
            "tradable": False,
            "ticker": tk,
            "reason": "No encontrado en Trading212",
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
    Infere el mercado correcto a partir del ticker T212.
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

    # Pre-cargar catálogo para inferir mercados
    await client._ensure_catalog()

    imported = 0
    updated = 0
    errors = []

    for bp in broker_result.data:
        ticker = bp.ticker.upper()
        try:
            # Inferir mercado desde el catálogo T212
            market = "NASDAQ"  # fallback
            inst = await client.get_instrument_info(ticker)
            if inst:
                market = client.infer_market_from_t212_ticker(inst["ticker_t212"])

            # Obtener sector
            sector = await asyncio.to_thread(get_sector, ticker, market)

            # Check si ya existe
            existing = await repo.get_position_by_ticker(
                portfolio_id, ticker, market=market
            )

            if existing is None:
                # Crear nueva posición
                await repo.upsert_position(
                    portfolio_id=portfolio_id,
                    ticker=ticker,
                    market=market,
                    sector=sector,
                    shares=bp.shares,
                    avg_price=bp.avg_price,
                )
                imported += 1
            else:
                # Actualizar precio y shares si hay discrepancia
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
    Devuelve {TICKER: current_price}. Útil para sustituir yfinance
    en posiciones que ya están en el broker.
    """
    client = get_trading212_client()
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
    Devuelve {cash, invested, portfolio_value, pnl, currency, mode} o None.
    Si mode=None usa el modo por defecto.
    """
    client = get_trading212_client(mode)
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
    Devuelve {success, old_cash, new_cash, diff}.
    Si mode=None usa el modo por defecto.
    """
    client = get_trading212_client(mode)
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

        # Sincronizar initial_capital con el totalValue del broker
        # si aún no se ha establecido manualmente
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
    Sincroniza el capital desde Trading212 para ambas carteras:
      REAL  ← T212 live
      BACKTEST ← T212 demo
    Devuelve resumen de la sincronización.
    """
    from database import repository as repo
    from database.models import PortfolioType
    from broker.trading212 import get_available_modes

    results: dict[str, Any] = {}
    mode_portfolio_map = {
        "live": PortfolioType.REAL,
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
    Obtiene el historial de dividendos cobrados en el broker.
    Devuelve lista de dicts con datos del dividendo.
    """
    client = get_trading212_client()
    if client is None:
        return []
    try:
        result = await client.get_dividend_history_all()
        if not result.success:
            return []

        items = result.data or []
        parsed = []
        for item in items[:limit]:
            ticker_raw = item.get("ticker", "")
            parsed.append({
                "ticker": client._clean_ticker(ticker_raw),
                "ticker_t212": ticker_raw,
                "amount": item.get("amount", 0),
                "quantity": item.get("quantity", 0),
                "amount_per_share": (
                    item.get("amount", 0) / item.get("quantity", 1)
                    if item.get("quantity", 0) > 0 else 0
                ),
                "paid_on": item.get("paidOn", ""),
                "reference": item.get("reference", ""),
            })
        return parsed
    except Exception as e:
        logger.debug(f"Error obteniendo historial dividendos: {e}")
        return []


async def get_broker_transaction_history(limit: int = 50) -> list[dict[str, Any]]:
    """
    Obtiene el historial de transacciones del broker.
    """
    client = get_trading212_client()
    if client is None:
        return []
    try:
        result = await client.get_transaction_history(limit=limit)
        if not result.success:
            return []

        data = result.data
        items = data.get("items", data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []

        parsed = []
        for item in items:
            parsed.append({
                "type": item.get("type", ""),
                "amount": item.get("amount", 0),
                "date": item.get("dateTime", item.get("dateExecuted", "")),
                "reference": item.get("reference", ""),
            })
        return parsed
    except Exception as e:
        logger.debug(f"Error obteniendo transacciones: {e}")
        return []
