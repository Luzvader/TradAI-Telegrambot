"""
Cliente eToro API – integración completa.

Docs:  https://api-portal.etoro.com/
Auth:  Headers x-api-key + x-user-key + x-request-id (UUID)
Base:  https://public-api.etoro.com/api/v1

Endpoints soportados:
  ── Trading ────────────────────────────────────────────────
  • POST /trading/execution/market-open-orders/by-amount         → Comprar por importe
  • POST /trading/execution/market-open-orders/by-units          → Comprar por unidades
  • POST /trading/execution/market-close-orders/positions/{id}   → Cerrar posición
  • POST /trading/execution/demo/market-open-orders/by-amount    → (demo) Comprar por importe
  • POST /trading/execution/demo/market-open-orders/by-units     → (demo) Comprar por unidades
  • POST /trading/execution/demo/market-close-orders/positions/{id} → (demo) Cerrar posición
  • GET  /trading/info/real/pnl                                  → P&L cuenta real
  • GET  /trading/info/demo/pnl                                  → P&L cuenta demo

  ── Market Data ────────────────────────────────────────────
  • GET  /market-data/search                                     → Buscar instrumentos
  • GET  /market-data/instruments                                → Metadata de instrumentos
  • GET  /market-data/instruments/rates                          → Precios en tiempo real
  • GET  /market-data/instruments/{id}/history/candles/...       → Velas históricas
  • GET  /market-data/instruments/history/closing-price          → Precios de cierre
  • GET  /market-data/exchanges                                  → Exchanges soportados
  • GET  /market-data/instrument-types                           → Tipos de activos
  • GET  /market-data/stocks-industries                          → Industrias

  ── Watchlists ─────────────────────────────────────────────
  • GET    /watchlists                                           → Obtener watchlists
  • POST   /watchlists                                           → Crear watchlist
  • POST   /watchlists/{id}/items                                → Añadir instrumentos
  • DELETE /watchlists/{id}/items                                → Quitar instrumentos
  • DELETE /watchlists/{id}                                      → Eliminar watchlist
  • GET    /curated-lists                                        → Listas curadas
  • GET    /market-recommendations/{count}                       → Recomendaciones

  ── Feeds ──────────────────────────────────────────────────
  • GET  /feeds/instrument/{marketId}                            → Feed de instrumento
  • GET  /feeds/user/{userId}                                    → Feed de usuario
  • POST /feeds/post                                             → Crear publicación

  ── Social (PI Data) ──────────────────────────────────────
  • GET  /pi-data/copiers-public-info                            → Info de copiers
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any

import aiohttp

from broker.base import (
    BaseBroker,
    BrokerAccount,
    BrokerOrder,
    BrokerPosition,
    BrokerResult,
)

logger = logging.getLogger(__name__)

# ── Constantes ───────────────────────────────────────────────

BASE_URL = "https://public-api.etoro.com/api/v1"

# Prefijo de ejecución según modo
_EXECUTION_PREFIX = {
    "demo": "/trading/execution/demo",
    "real": "/trading/execution",
}

# Prefijo de info según modo
_INFO_PREFIX = {
    "demo": "/trading/info/demo",
    "real": "/trading/info/real",
}

# Rate limit delays conservadores (segundos entre llamadas del mismo tipo)
_RATE_LIMITS = {
    "default": 0.5,
    "account": 2.0,
    "positions": 1.0,
    "orders_open": 1.0,
    "orders_close": 1.0,
    "search": 0.5,
    "instruments": 2.0,
    "rates": 1.0,
    "candles": 1.0,
    "watchlists": 1.0,
    "feeds": 1.0,
}

# TTL del catálogo de instrumentos en segundos (24h)
_INSTRUMENTS_CATALOG_TTL = 86_400


class EtoroClient(BaseBroker):
    """
    Cliente para la API pública de eToro.
    Soporta modo demo y real con la misma interfaz.
    Usa x-api-key + x-user-key headers para autenticación.
    """

    def __init__(self, api_key: str, user_key: str, mode: str = "demo"):
        if mode not in ("demo", "real"):
            raise ValueError(f"Modo inválido: {mode}. Usa 'demo' o 'real'.")
        if not api_key:
            raise ValueError("ETORO_API_KEY es obligatorio.")
        if not user_key:
            raise ValueError("ETORO_USER_KEY es obligatorio.")

        self.api_key = api_key
        self.user_key = user_key
        self.mode = mode
        self.base_url = BASE_URL
        self._execution_prefix = _EXECUTION_PREFIX[mode]
        self._info_prefix = _INFO_PREFIX[mode]
        self._session: aiohttp.ClientSession | None = None

        # Caché de instrumentos: symbol → instrument_id
        self._instrument_id_cache: dict[str, int] = {}
        # Catálogo completo de instrumentos con TTL
        self._catalog: list[dict] = []
        self._catalog_by_id: dict[int, dict] = {}
        self._catalog_by_symbol: dict[str, dict] = {}
        self._catalog_ts: float = 0.0

        # Caché de posiciones (TTL corto)
        self._positions_cache: list[dict] = []
        self._positions_ts: float = 0.0
        self._positions_ttl: float = 60.0

        # Control de rate limit por tipo de endpoint
        self._last_call_ts: dict[str, float] = {}

        logger.info(f"🔗 eToro configurado en modo {mode.upper()}")

    def _make_headers(self) -> dict[str, str]:
        """Genera headers de autenticación con un UUID único por request."""
        return {
            "x-api-key": self.api_key,
            "x-user-key": self.user_key,
            "x-request-id": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def close(self) -> None:
        """Cierra la sesión HTTP."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Any = None,
        params: dict | None = None,
        rate_key: str = "default",
    ) -> BrokerResult:
        """Ejecuta una petición HTTP a la API de eToro."""
        url = f"{self.base_url}{endpoint}"

        try:
            session = await self._get_session()

            # Rate limiting
            delay = _RATE_LIMITS.get(rate_key, _RATE_LIMITS["default"])
            now = time.monotonic()
            last = self._last_call_ts.get(rate_key)
            if last is not None:
                wait_for = delay - (now - last)
                if wait_for > 0:
                    await asyncio.sleep(wait_for)
            self._last_call_ts[rate_key] = time.monotonic()

            headers = self._make_headers()

            async with session.request(
                method, url, json=json_data, params=params, headers=headers
            ) as resp:
                if 200 <= resp.status < 300:
                    if resp.status == 204:
                        return BrokerResult(success=True, data=None)

                    raw = await resp.text()
                    if not raw.strip():
                        return BrokerResult(success=True, data=None)

                    content_type = (resp.headers.get("Content-Type") or "").lower()
                    if "application/json" in content_type:
                        try:
                            return BrokerResult(success=True, data=json.loads(raw))
                        except json.JSONDecodeError:
                            logger.debug(
                                f"Respuesta 2xx con Content-Type JSON pero body no parseable "
                                f"[{method} {endpoint}]"
                            )

                    # Fallback: intentar parsear JSON
                    try:
                        return BrokerResult(success=True, data=json.loads(raw))
                    except json.JSONDecodeError:
                        return BrokerResult(success=True, data=raw)

                else:
                    text = await resp.text()
                    logger.error(
                        f"eToro API error {resp.status}: {text} "
                        f"[{method} {endpoint}]"
                    )
                    return BrokerResult(
                        success=False,
                        error=f"HTTP {resp.status}: {text}",
                    )
        except aiohttp.ClientError as e:
            logger.error(f"eToro connection error: {e}")
            return BrokerResult(success=False, error=f"Connection error: {e}")
        except Exception as e:
            logger.error(f"eToro unexpected error: {e}")
            return BrokerResult(success=False, error=str(e))

    # ══════════════════════════════════════════════════════════
    # Account / P&L
    # ══════════════════════════════════════════════════════════

    async def get_account(self) -> BrokerResult:
        """
        Obtiene P&L e info de la cuenta.
        Demo: GET /trading/info/demo/pnl
        Real: GET /trading/info/real/pnl

        Response incluye: credits, equity, openPositions con P&L,
        ordersForOpen, orders, etc.
        """
        result = await self._request(
            "GET", f"{self._info_prefix}/pnl", rate_key="account"
        )
        if not result.success:
            return result

        data = result.data or {}

        # Extraer datos del P&L de eToro
        credits = self._to_float(data.get("credits")) or 0
        equity = self._to_float(data.get("equity")) or 0

        # Calcular invertido y P&L desde posiciones abiertas
        positions = data.get("openPositions", [])
        total_invested = 0.0
        total_pnl = 0.0
        for pos in positions:
            amount = self._to_float(pos.get("amount")) or 0
            net_profit = self._to_float(pos.get("netProfit")) or 0
            total_invested += amount
            total_pnl += net_profit

        # Calcular cash disponible
        # Available Cash = credits - (Σ manual ordersForOpen + Σ orders)
        orders_for_open = data.get("ordersForOpen", [])
        pending_orders = data.get("orders", [])
        pending_amount = sum(
            self._to_float(o.get("amount")) or 0
            for o in orders_for_open
            if self._to_float(o.get("mirrorID")) == 0
        )
        pending_amount += sum(
            self._to_float(o.get("amount")) or 0
            for o in pending_orders
        )
        available_cash = credits - pending_amount

        portfolio_value = equity if equity > 0 else (credits + total_invested + total_pnl)
        pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0

        account = BrokerAccount(
            cash=available_cash,
            invested=total_invested,
            portfolio_value=portfolio_value,
            pnl=total_pnl,
            pnl_pct=round(pnl_pct, 2),
            currency="USD",  # eToro opera en USD
            mode=self.mode,
        )
        return BrokerResult(success=True, data=account)

    # ══════════════════════════════════════════════════════════
    # Positions
    # ══════════════════════════════════════════════════════════

    async def get_positions(self) -> BrokerResult:
        """
        Obtiene posiciones abiertas desde el endpoint P&L.
        Las posiciones vienen en openPositions dentro del P&L response.
        """
        result = await self._request(
            "GET", f"{self._info_prefix}/pnl", rate_key="positions"
        )
        if not result.success:
            return result

        data = result.data or {}
        raw_positions = data.get("openPositions", [])

        # Necesitamos resolver instrument IDs a tickers
        # Recopilar todos los instrument IDs de las posiciones
        instrument_ids = set()
        for pos in raw_positions:
            iid = pos.get("instrumentId") or pos.get("InstrumentId")
            if iid:
                instrument_ids.add(int(iid))

        # Resolver nombres de instrumentos
        id_to_info = await self._resolve_instrument_ids(list(instrument_ids))

        positions = []
        for pos in raw_positions:
            iid = pos.get("instrumentId") or pos.get("InstrumentId")
            position_id = pos.get("positionId") or pos.get("PositionId") or ""
            amount = self._to_float(pos.get("amount")) or 0
            units = self._to_float(pos.get("units")) or 0
            net_profit = self._to_float(pos.get("netProfit")) or 0
            leverage = self._to_float(pos.get("leverage")) or 1
            is_buy = pos.get("isBuy", True)
            open_rate = self._to_float(pos.get("openRate")) or 0
            current_rate = self._to_float(pos.get("currentRate")) or 0

            info = id_to_info.get(int(iid)) if iid else {}
            symbol = info.get("symbol", str(iid))
            name = info.get("name", symbol)

            # Calcular avg_price y current_price
            avg_price = open_rate
            current_price = current_rate
            pnl_pct = (net_profit / amount * 100) if amount > 0 else 0
            market_value = amount + net_profit

            positions.append(BrokerPosition(
                ticker=symbol,
                shares=units,
                avg_price=round(avg_price, 4),
                current_price=round(current_price, 4),
                pnl=round(net_profit, 2),
                pnl_pct=round(pnl_pct, 2),
                market_value=round(market_value, 2),
                currency="USD",
                frontend_name=name,
            ))

        # Guardar datos crudos en caché para el cierre de posiciones
        self._positions_cache = raw_positions
        self._positions_ts = time.monotonic()

        return BrokerResult(success=True, data=positions)

    async def _resolve_instrument_ids(
        self, instrument_ids: list[int]
    ) -> dict[int, dict]:
        """
        Resuelve una lista de instrument IDs a sus símbolos y nombres
        usando el catálogo cacheado o el endpoint de metadata.
        """
        result: dict[int, dict] = {}
        if not instrument_ids:
            return result

        # Intentar desde catálogo cacheado
        await self._ensure_catalog()
        missing = []
        for iid in instrument_ids:
            if iid in self._catalog_by_id:
                info = self._catalog_by_id[iid]
                result[iid] = {
                    "symbol": info.get("symbolFull", str(iid)),
                    "name": info.get("displayName", ""),
                    "type": info.get("instrumentType", ""),
                }
            else:
                missing.append(iid)

        # Si faltan, obtener por metadata endpoint
        if missing:
            ids_str = ",".join(str(i) for i in missing)
            meta_result = await self._request(
                "GET",
                "/market-data/instruments",
                params={"instrumentIds": ids_str},
                rate_key="instruments",
            )
            if meta_result.success and meta_result.data:
                items = meta_result.data
                if isinstance(items, dict):
                    items = items.get("instrumentDisplayDatas", [])
                for item in items:
                    iid = item.get("instrumentId")
                    if iid:
                        result[int(iid)] = {
                            "symbol": item.get("symbolFull", str(iid)),
                            "name": item.get("instrumentDisplayName", ""),
                            "type": item.get("instrumentTypeId", ""),
                        }

        return result

    # ══════════════════════════════════════════════════════════
    # Trading – Open / Close Positions
    # ══════════════════════════════════════════════════════════

    async def place_market_order(
        self, ticker: str, shares: float, side: str
    ) -> BrokerResult:
        """
        Abre una posición de mercado por unidades.
        POST /trading/execution/[demo/]market-open-orders/by-units

        En eToro, para "vender" se cierra la posición existente.
        Si side=="SELL", busca la posición abierta y la cierra.
        """
        if side.upper() == "SELL":
            return await self._close_position_by_ticker(ticker, shares)

        # Resolver ticker a instrument ID
        instrument_id = await self._resolve_ticker_to_id(ticker)
        if instrument_id is None:
            return BrokerResult(
                success=False,
                error=f"No se encontró el instrumento '{ticker}' en eToro",
            )

        payload = {
            "InstrumentId": instrument_id,
            "Units": abs(shares),
            "IsBuy": True,
            "Leverage": 1,
        }

        result = await self._request(
            "POST",
            f"{self._execution_prefix}/market-open-orders/by-units",
            json_data=payload,
            rate_key="orders_open",
        )
        if not result.success:
            return result

        order = self._parse_open_order_response(result.data, ticker, "BUY")
        logger.info(
            f"📤 eToro [{self.mode.upper()}] "
            f"Market BUY {ticker}: {abs(shares)} unidades → {order.status}"
        )
        return BrokerResult(success=True, data=order)

    async def place_market_order_by_amount(
        self, ticker: str, amount: float, side: str = "BUY",
        leverage: int = 1,
        stop_loss_rate: float | None = None,
        take_profit_rate: float | None = None,
    ) -> BrokerResult:
        """
        Abre una posición de mercado por importe (USD).
        POST /trading/execution/[demo/]market-open-orders/by-amount

        Este es el método preferido para DCA o estrategias de presupuesto fijo.
        """
        if side.upper() == "SELL":
            return BrokerResult(
                success=False,
                error="Para vender en eToro, usa close_position() con el positionId.",
            )

        instrument_id = await self._resolve_ticker_to_id(ticker)
        if instrument_id is None:
            return BrokerResult(
                success=False,
                error=f"No se encontró el instrumento '{ticker}' en eToro",
            )

        payload: dict[str, Any] = {
            "InstrumentId": instrument_id,
            "Amount": abs(amount),
            "IsBuy": True,
            "Leverage": leverage,
        }
        if stop_loss_rate is not None:
            payload["StopLossRate"] = stop_loss_rate
        if take_profit_rate is not None:
            payload["TakeProfitRate"] = take_profit_rate

        result = await self._request(
            "POST",
            f"{self._execution_prefix}/market-open-orders/by-amount",
            json_data=payload,
            rate_key="orders_open",
        )
        if not result.success:
            return result

        order = self._parse_open_order_response(result.data, ticker, "BUY")
        logger.info(
            f"📤 eToro [{self.mode.upper()}] "
            f"Market BUY (amount) {ticker}: ${abs(amount)} → {order.status}"
        )
        return BrokerResult(success=True, data=order)

    async def close_position(
        self, position_id: int | str, units_to_deduct: float | None = None
    ) -> BrokerResult:
        """
        Cierra una posición por su positionId.
        POST /trading/execution/[demo/]market-close-orders/positions/{positionId}

        units_to_deduct=None → cierre total
        units_to_deduct=X   → cierre parcial
        """
        payload: dict[str, Any] = {}
        if units_to_deduct is not None:
            payload["UnitsToDeduct"] = units_to_deduct

        result = await self._request(
            "POST",
            f"{self._execution_prefix}/market-close-orders/positions/{position_id}",
            json_data=payload if payload else None,
            rate_key="orders_close",
        )
        if result.success:
            close_type = "parcial" if units_to_deduct else "total"
            logger.info(
                f"📤 eToro [{self.mode.upper()}] "
                f"Posición {position_id} cerrada ({close_type})"
            )
        return result

    async def _close_position_by_ticker(
        self, ticker: str, shares: float | None = None
    ) -> BrokerResult:
        """
        Cierra la posición de un ticker buscando su positionId.
        Si shares es None, cierre total. Si shares > 0, cierre parcial.
        """
        # Obtener posiciones actuales desde P&L
        pnl_result = await self._request(
            "GET", f"{self._info_prefix}/pnl", rate_key="positions"
        )
        if not pnl_result.success:
            return pnl_result

        data = pnl_result.data or {}
        raw_positions = data.get("openPositions", [])

        # Resolver el ticker a instrument ID
        instrument_id = await self._resolve_ticker_to_id(ticker)
        if instrument_id is None:
            return BrokerResult(
                success=False,
                error=f"No se encontró el instrumento '{ticker}' en eToro",
            )

        # Buscar la posición con ese instrument ID
        target_position = None
        for pos in raw_positions:
            pos_iid = pos.get("instrumentId") or pos.get("InstrumentId")
            if pos_iid and int(pos_iid) == instrument_id:
                target_position = pos
                break

        if target_position is None:
            return BrokerResult(
                success=False,
                error=f"No se encontró posición abierta de '{ticker}' en eToro",
            )

        position_id = target_position.get("positionId") or target_position.get("PositionId")
        if not position_id:
            return BrokerResult(
                success=False,
                error=f"No se pudo obtener positionId para '{ticker}'",
            )

        # Determinar si es cierre parcial o total
        total_units = self._to_float(target_position.get("units")) or 0
        units_to_deduct = None
        if shares is not None and shares > 0 and shares < total_units:
            units_to_deduct = shares

        result = await self.close_position(position_id, units_to_deduct)
        if result.success:
            close_type = f"parcial ({shares} units)" if units_to_deduct else "total"
            order = BrokerOrder(
                order_id=str(position_id),
                ticker=ticker,
                side="SELL",
                shares=shares or total_units,
                price=None,
                status="CLOSED",
                filled_price=self._to_float(target_position.get("currentRate")),
                filled_shares=shares or total_units,
                timestamp="",
            )
            return BrokerResult(success=True, data=order)
        return result

    # ── Limit/Stop orders (eToro implementa SL/TP en la apertura) ──

    async def place_limit_order(
        self, ticker: str, shares: float, side: str, limit_price: float,
        time_validity: str = "GOOD_TILL_CANCEL",
    ) -> BrokerResult:
        """
        eToro no tiene órdenes limit separadas como otros brokers.
        Las órdenes pendientes se gestionan como "Entry Orders" con rates.
        Por ahora, abrir por unidades con Rate especificado.
        """
        return BrokerResult(
            success=False,
            error=(
                "eToro no soporta órdenes limit al estilo tradicional via API pública. "
                "Usa place_market_order o place_market_order_by_amount con SL/TP."
            ),
        )

    async def place_stop_order(
        self, ticker: str, shares: float, side: str, stop_price: float,
        time_validity: str = "GOOD_TILL_CANCEL",
    ) -> BrokerResult:
        """eToro gestiona stop-loss como parámetro de la posición abierta."""
        return BrokerResult(
            success=False,
            error=(
                "eToro gestiona stop-loss como parámetro al abrir posición. "
                "Usa place_market_order_by_amount con stop_loss_rate."
            ),
        )

    async def place_stop_limit_order(
        self, ticker: str, shares: float, side: str,
        stop_price: float, limit_price: float,
        time_validity: str = "GOOD_TILL_CANCEL",
    ) -> BrokerResult:
        """eToro no soporta órdenes stop-limit separadas."""
        return BrokerResult(
            success=False,
            error="eToro no soporta órdenes stop-limit separadas vía la API pública.",
        )

    async def cancel_order(self, order_id: str) -> BrokerResult:
        """
        En eToro, para cancelar una orden pendiente se debe cerrar
        la posición u orden asociada. No hay endpoint genérico de cancel.
        """
        return BrokerResult(
            success=False,
            error="eToro no soporta cancelación de órdenes pendientes como endpoint separado.",
        )

    async def get_orders(self) -> BrokerResult:
        """
        Obtiene órdenes pendientes desde el endpoint P&L.
        Las órdenes pendientes vienen en 'ordersForOpen' y 'orders'.
        Resuelve instrument IDs a símbolos legibles.
        """
        result = await self._request(
            "GET", f"{self._info_prefix}/pnl", rate_key="account"
        )
        if not result.success:
            return result

        data = result.data or {}
        orders_for_open = data.get("ordersForOpen", [])
        pending_orders = data.get("orders", [])

        # Recopilar instrument IDs para resolverlos a símbolos
        all_items = list(orders_for_open) + list(pending_orders)
        instrument_ids = set()
        for item in all_items:
            iid = item.get("instrumentId") or item.get("InstrumentId")
            if iid:
                instrument_ids.add(int(iid))
        id_to_info = await self._resolve_instrument_ids(list(instrument_ids))

        orders = []
        for item in orders_for_open:
            iid = item.get("instrumentId") or item.get("InstrumentId")
            symbol = id_to_info.get(int(iid), {}).get("symbol", str(iid)) if iid else str(iid)
            orders.append(BrokerOrder(
                order_id=str(item.get("orderId", item.get("positionId", ""))),
                ticker=symbol,
                side="BUY" if item.get("isBuy", True) else "SELL",
                shares=self._to_float(item.get("units")) or 0,
                price=self._to_float(item.get("rate")),
                status="PENDING",
                timestamp="",
            ))
        for item in pending_orders:
            iid = item.get("instrumentId") or item.get("InstrumentId")
            symbol = id_to_info.get(int(iid), {}).get("symbol", str(iid)) if iid else str(iid)
            orders.append(BrokerOrder(
                order_id=str(item.get("orderId", "")),
                ticker=symbol,
                side="BUY" if item.get("isBuy", True) else "SELL",
                shares=self._to_float(item.get("units")) or 0,
                price=self._to_float(item.get("rate")),
                status="PENDING",
                timestamp="",
            ))

        return BrokerResult(success=True, data=orders)

    async def get_order_by_id(self, order_id: str) -> BrokerResult:
        """
        Busca una orden por su ID en las órdenes pendientes (P&L).
        eToro no tiene un endpoint GET /orders/{id}, así que se filtra
        desde el P&L. Resuelve instrument IDs a símbolos.
        """
        pnl = await self._request(
            "GET", f"{self._info_prefix}/pnl", rate_key="account"
        )
        if not pnl.success:
            return pnl

        data = pnl.data or {}
        all_orders = list(data.get("ordersForOpen", [])) + list(data.get("orders", []))

        for item in all_orders:
            item_id = str(
                item.get("orderId", item.get("positionId", ""))
            )
            if item_id == str(order_id):
                is_buy = item.get("isBuy", True)
                status_str = "PENDING"
                iid = item.get("instrumentId") or item.get("InstrumentId")
                symbol = str(iid)
                if iid:
                    info = await self._resolve_instrument_ids([int(iid)])
                    symbol = info.get(int(iid), {}).get("symbol", str(iid))
                return BrokerResult(
                    success=True,
                    data=BrokerOrder(
                        order_id=item_id,
                        ticker=symbol,
                        side="BUY" if is_buy else "SELL",
                        shares=self._to_float(item.get("units")) or 0,
                        price=self._to_float(item.get("rate")),
                        status=status_str,
                        timestamp="",
                    ),
                )

        # Buscar en posiciones abiertas (la orden se ejecutó y es ahora una posición)
        for pos in data.get("openPositions", []):
            pos_id = str(pos.get("positionId") or pos.get("PositionId") or "")
            if pos_id == str(order_id):
                iid = pos.get("instrumentId") or pos.get("InstrumentId")
                symbol = str(iid)
                if iid:
                    info = await self._resolve_instrument_ids([int(iid)])
                    symbol = info.get(int(iid), {}).get("symbol", str(iid))
                return BrokerResult(
                    success=True,
                    data=BrokerOrder(
                        order_id=pos_id,
                        ticker=symbol,
                        side="BUY" if pos.get("isBuy", True) else "SELL",
                        shares=self._to_float(pos.get("units")) or 0,
                        price=self._to_float(pos.get("openRate")),
                        status="FILLED",
                        filled_price=self._to_float(pos.get("openRate")),
                        filled_shares=self._to_float(pos.get("units")),
                        timestamp="",
                    ),
                )

        return BrokerResult(
            success=False,
            error=f"HTTP 404: Orden '{order_id}' no encontrada",
        )

    async def get_historical_order_by_id(self, order_id: str) -> BrokerResult:
        """
        Fallback: busca una orden histórica por ID.
        eToro no tiene un endpoint de historial de órdenes separado,
        así que re-consultamos el P&L buscando posiciones ejecutadas
        cuyo positionId coincida.
        """
        return await self.get_order_by_id(order_id)

    async def get_instrument_by_ticker(self, ticker: str) -> BrokerResult:
        """Busca info de un instrumento por ticker. Implementa abstract de BaseBroker."""
        info = await self.get_instrument_info(ticker)
        if info:
            return BrokerResult(success=True, data=info)
        # Fallback a búsqueda
        result = await self.search_instrument(ticker)
        if result.success and result.data:
            for item in result.data:
                if item.get("symbol", "").upper() == ticker.upper():
                    return BrokerResult(success=True, data=item)
            return BrokerResult(success=True, data=result.data[0])
        return BrokerResult(
            success=False,
            error=f"Instrumento '{ticker}' no encontrado en eToro",
        )

    # ══════════════════════════════════════════════════════════
    # Market Data – Search / Instruments
    # ══════════════════════════════════════════════════════════

    async def search_instrument(
        self, query: str, page_size: int = 20
    ) -> BrokerResult:
        """
        Busca instrumentos en eToro.
        GET /market-data/search?internalSymbolFull=AAPL
        o GET /market-data/search?searchText=Apple

        Devuelve lista de coincidencias con instrumentId, symbol, name, etc.
        """
        # Primero intentar búsqueda exacta por símbolo
        params: dict[str, Any] = {
            "internalSymbolFull": query.upper(),
            "fields": "instrumentId,displayname,internalSymbolFull,instrumentType,exchangeID,isCurrentlyTradable,isBuyEnabled,currentRate",
            "pageSize": page_size,
        }

        result = await self._request(
            "GET", "/market-data/search",
            params=params, rate_key="search",
        )
        if not result.success:
            return result

        data = result.data or {}
        items = data.get("items", [])

        # Si no hay resultados con símbolo exacto, buscar por texto libre
        if not items:
            params = {
                "searchText": query,
                "fields": "instrumentId,displayname,internalSymbolFull,instrumentType,exchangeID,isCurrentlyTradable,isBuyEnabled,currentRate",
                "pageSize": page_size,
            }
            result = await self._request(
                "GET", "/market-data/search",
                params=params, rate_key="search",
            )
            if not result.success:
                return result
            data = result.data or {}
            items = data.get("items", [])

        matches = []
        for item in items:
            matches.append({
                "instrument_id": item.get("instrumentId"),
                "symbol": item.get("internalSymbolFull", ""),
                "name": item.get("displayname", ""),
                "type": item.get("instrumentType", ""),
                "exchange_id": item.get("exchangeID"),
                "tradable": item.get("isCurrentlyTradable", False),
                "buy_enabled": item.get("isBuyEnabled", False),
                "current_rate": item.get("currentRate"),
            })

        return BrokerResult(success=True, data=matches)

    async def get_instrument_rates(
        self, instrument_ids: list[int]
    ) -> BrokerResult:
        """
        Obtiene precios en tiempo real para instrumentos específicos.
        GET /market-data/instruments/rates?instrumentIds=1001,1002
        Máximo 100 IDs por llamada.
        """
        if not instrument_ids:
            return BrokerResult(success=True, data=[])

        ids_str = ",".join(str(i) for i in instrument_ids[:100])
        result = await self._request(
            "GET",
            "/market-data/instruments/rates",
            params={"instrumentIds": ids_str},
            rate_key="rates",
        )
        if not result.success:
            return result

        data = result.data or {}
        rates = data.get("rates", data) if isinstance(data, dict) else data
        return BrokerResult(success=True, data=rates if isinstance(rates, list) else [])

    async def get_historical_candles(
        self,
        instrument_id: int,
        interval: str = "OneDay",
        count: int = 100,
        direction: str = "desc",
    ) -> BrokerResult:
        """
        Obtiene velas históricas OHLCV.
        GET /market-data/instruments/{id}/history/candles/{direction}/{interval}/{count}

        Intervalos: OneMinute, FiveMinutes, FifteenMinutes, ThirtyMinutes,
                    OneHour, FourHours, OneDay, OneWeek
        """
        result = await self._request(
            "GET",
            f"/market-data/instruments/{instrument_id}/history/candles"
            f"/{direction}/{interval}/{min(count, 1000)}",
            rate_key="candles",
        )
        return result

    async def get_closing_prices(self) -> BrokerResult:
        """
        Obtiene precios de cierre históricos para todos los instrumentos.
        GET /market-data/instruments/history/closing-price
        """
        return await self._request(
            "GET",
            "/market-data/instruments/history/closing-price",
            rate_key="instruments",
        )

    async def get_exchanges(self) -> BrokerResult:
        """GET /market-data/exchanges"""
        return await self._request(
            "GET", "/market-data/exchanges", rate_key="instruments"
        )

    async def get_instrument_types(self) -> BrokerResult:
        """GET /market-data/instrument-types"""
        return await self._request(
            "GET", "/market-data/instrument-types", rate_key="instruments"
        )

    async def get_stock_industries(self) -> BrokerResult:
        """GET /market-data/stocks-industries"""
        return await self._request(
            "GET", "/market-data/stocks-industries", rate_key="instruments"
        )

    async def get_instruments_metadata(
        self, instrument_ids: list[int] | None = None
    ) -> BrokerResult:
        """
        Obtiene metadata de instrumentos.
        GET /market-data/instruments
        """
        params: dict[str, Any] = {}
        if instrument_ids:
            params["instrumentIds"] = ",".join(str(i) for i in instrument_ids)

        return await self._request(
            "GET", "/market-data/instruments",
            params=params, rate_key="instruments",
        )

    # ══════════════════════════════════════════════════════════
    # Watchlists
    # ══════════════════════════════════════════════════════════

    async def get_watchlists(self) -> BrokerResult:
        """GET /watchlists – obtiene todas las watchlists del usuario."""
        return await self._request(
            "GET", "/watchlists",
            params={"ensureBuiltinWatchlists": "true"},
            rate_key="watchlists",
        )

    async def create_watchlist(self, name: str) -> BrokerResult:
        """POST /watchlists?name=... – crea una nueva watchlist."""
        return await self._request(
            "POST", "/watchlists",
            params={"name": name},
            rate_key="watchlists",
        )

    async def add_to_watchlist(
        self, watchlist_id: str, instrument_ids: list[int]
    ) -> BrokerResult:
        """POST /watchlists/{id}/items – añade instrumentos a una watchlist."""
        return await self._request(
            "POST", f"/watchlists/{watchlist_id}/items",
            json_data=instrument_ids,
            rate_key="watchlists",
        )

    async def remove_from_watchlist(
        self, watchlist_id: str, items: list[dict]
    ) -> BrokerResult:
        """DELETE /watchlists/{id}/items – elimina instrumentos de una watchlist."""
        return await self._request(
            "DELETE", f"/watchlists/{watchlist_id}/items",
            json_data=items,
            rate_key="watchlists",
        )

    async def delete_watchlist(self, watchlist_id: str) -> BrokerResult:
        """DELETE /watchlists/{id} – elimina una watchlist."""
        return await self._request(
            "DELETE", f"/watchlists/{watchlist_id}",
            rate_key="watchlists",
        )

    async def get_curated_lists(self) -> BrokerResult:
        """GET /curated-lists – listas curadas de eToro."""
        return await self._request(
            "GET", "/curated-lists", rate_key="watchlists"
        )

    async def get_market_recommendations(self, count: int = 10) -> BrokerResult:
        """GET /market-recommendations/{count} – recomendaciones personalizadas."""
        return await self._request(
            "GET", f"/market-recommendations/{count}", rate_key="watchlists"
        )

    # ══════════════════════════════════════════════════════════
    # Feeds / Social
    # ══════════════════════════════════════════════════════════

    async def get_instrument_feed(
        self, market_id: str, take: int = 20
    ) -> BrokerResult:
        """GET /feeds/instrument/{marketId} – feed de un instrumento."""
        return await self._request(
            "GET", f"/feeds/instrument/{market_id}",
            params={"take": take},
            rate_key="feeds",
        )

    async def get_user_feed(
        self, user_id: str, take: int = 20
    ) -> BrokerResult:
        """GET /feeds/user/{userId} – feed de un usuario."""
        return await self._request(
            "GET", f"/feeds/user/{user_id}",
            params={"take": take},
            rate_key="feeds",
        )

    async def create_feed_post(
        self, owner_id: int, message: str, tags: list[dict] | None = None
    ) -> BrokerResult:
        """POST /feeds/post – crear una publicación en el feed."""
        payload: dict[str, Any] = {
            "owner": owner_id,
            "message": message,
        }
        if tags:
            payload["tags"] = {"tags": tags}

        return await self._request(
            "POST", "/feeds/post",
            json_data=payload,
            rate_key="feeds",
        )

    # ══════════════════════════════════════════════════════════
    # Catálogo de instrumentos (cacheado)
    # ══════════════════════════════════════════════════════════

    async def _ensure_catalog(self, force: bool = False) -> bool:
        """
        Carga el catálogo de instrumentos de eToro usando el endpoint search.
        Cachea por TTL.
        """
        now = time.monotonic()
        if not force and self._catalog and (now - self._catalog_ts) < _INSTRUMENTS_CATALOG_TTL:
            return True

        # eToro no tiene un endpoint que devuelva todos los instrumentos de golpe
        # Usamos /market-data/instruments para obtener metadata general
        result = await self._request(
            "GET", "/market-data/instruments",
            rate_key="instruments",
        )
        if not result.success:
            logger.error(f"Error cargando catálogo de instrumentos eToro: {result.error}")
            return bool(self._catalog)

        data = result.data or {}
        instruments = data.get("instrumentDisplayDatas", []) if isinstance(data, dict) else data

        self._catalog = instruments
        self._catalog_by_id = {}
        self._catalog_by_symbol = {}

        for inst in instruments:
            iid = inst.get("instrumentId")
            symbol = inst.get("symbolFull", "")
            display_name = inst.get("instrumentDisplayName", "")
            type_id = inst.get("instrumentTypeId")
            exchange_id = inst.get("exchangeId")

            entry = {
                "instrumentId": iid,
                "symbolFull": symbol,
                "displayName": display_name,
                "instrumentTypeId": type_id,
                "exchangeId": exchange_id,
                "stocksIndustryId": inst.get("stocksIndustryId"),
                "priceSource": inst.get("priceSource", ""),
                "isInternal": inst.get("isInternalInstrument", False),
            }
            if iid:
                self._catalog_by_id[int(iid)] = entry
            if symbol:
                self._catalog_by_symbol[symbol.upper()] = entry

        self._catalog_ts = now
        logger.info(
            f"📦 Catálogo eToro cargado: {len(instruments)} instrumentos"
        )
        return True

    async def get_all_instruments(self, force_refresh: bool = False) -> list[dict]:
        """Devuelve el catálogo completo de instrumentos (cacheado)."""
        await self._ensure_catalog(force=force_refresh)
        return list(self._catalog_by_id.values())

    async def get_instrument_info(self, ticker: str) -> dict | None:
        """
        Obtiene info de un instrumento por símbolo (e.g. 'AAPL').
        Usa catálogo cacheado. Devuelve None si no existe.
        """
        await self._ensure_catalog()
        return self._catalog_by_symbol.get(ticker.upper().strip())

    async def get_instrument_by_id(self, instrument_id: int) -> dict | None:
        """Obtiene info de un instrumento por su ID numérico."""
        await self._ensure_catalog()
        return self._catalog_by_id.get(instrument_id)

    async def is_tradable(self, ticker: str) -> bool:
        """Comprueba si un ticker es operable en eToro."""
        # Primero check rápido en catálogo
        info = await self.get_instrument_info(ticker)
        if info:
            return True

        # Fallback: búsqueda explícita
        result = await self.search_instrument(ticker)
        if result.success and result.data:
            for item in result.data:
                if item.get("symbol", "").upper() == ticker.upper():
                    return item.get("tradable", False) and item.get("buy_enabled", False)
        return False

    async def get_tradable_tickers(
        self, asset_type: str | None = None
    ) -> list[str]:
        """
        Devuelve lista de símbolos operables en eToro.
        asset_type no aplica directamente (eToro usa instrumentTypeId).
        """
        await self._ensure_catalog()
        return [
            info.get("symbolFull", "")
            for info in self._catalog_by_symbol.values()
            if info.get("symbolFull")
        ]

    async def _resolve_ticker_to_id(self, ticker: str) -> int | None:
        """
        Convierte un ticker (e.g. 'AAPL') a un instrument ID numérico de eToro.
        Usa caché para máxima eficiencia.
        """
        ticker = ticker.upper().strip()

        # Check caché directo
        if ticker in self._instrument_id_cache:
            return self._instrument_id_cache[ticker]

        # Check catálogo
        info = await self.get_instrument_info(ticker)
        if info and info.get("instrumentId"):
            iid = int(info["instrumentId"])
            self._instrument_id_cache[ticker] = iid
            return iid

        # Búsqueda explícita en eToro
        result = await self.search_instrument(ticker)
        if not result.success or not result.data:
            return None

        # Buscar match exacto
        for item in result.data:
            if item.get("symbol", "").upper() == ticker:
                iid = item.get("instrument_id")
                if iid:
                    self._instrument_id_cache[ticker] = int(iid)
                    return int(iid)

        # Usar primer resultado como fallback
        first = result.data[0]
        iid = first.get("instrument_id")
        if iid:
            self._instrument_id_cache[ticker] = int(iid)
            return int(iid)

        return None

    # ══════════════════════════════════════════════════════════
    # Precios desde posiciones (caché corto)
    # ══════════════════════════════════════════════════════════

    async def get_positions_prices(self) -> dict[str, float]:
        """
        Devuelve {symbol: current_rate} de todas las posiciones.
        Útil para obtener precios sin usar yfinance.
        """
        result = await self.get_positions()
        if result.success and result.data:
            return {p.ticker.upper(): p.current_price for p in result.data}
        return {}

    async def get_positions_details(self) -> list[BrokerPosition]:
        """Devuelve posiciones con caché corto."""
        result = await self.get_positions()
        if result.success and result.data:
            return result.data
        return []

    # ══════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════

    def _parse_open_order_response(
        self, data: Any, ticker: str, side: str
    ) -> BrokerOrder:
        """Parsea la respuesta de apertura de posición."""
        if isinstance(data, dict):
            position_id = data.get("positionId") or data.get("PositionId") or ""
            rate = self._to_float(data.get("rate") or data.get("openRate"))
            units = self._to_float(data.get("units")) or 0
            return BrokerOrder(
                order_id=str(position_id),
                ticker=ticker,
                side=side.upper(),
                shares=abs(units),
                price=rate,
                status="FILLED",
                filled_price=rate,
                filled_shares=abs(units),
                timestamp="",
            )
        return BrokerOrder(
            order_id="",
            ticker=ticker,
            side=side.upper(),
            shares=0,
            price=None,
            status="UNKNOWN",
            timestamp="",
        )

    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None


# ══════════════════════════════════════════════════════════════
# Singleton global (soporta dual: demo + real)
# ══════════════════════════════════════════════════════════════

_clients: dict[str, EtoroClient] = {}
_default_mode: str = "demo"


def get_etoro_client(mode: str | None = None) -> EtoroClient | None:
    """
    Devuelve el cliente eToro para el modo dado.
    Si mode=None, usa el modo por defecto (ETORO_MODE).
    """
    m = (mode or _default_mode).lower()
    return _clients.get(m)


def get_available_modes() -> list[str]:
    """Devuelve los modos con cliente inicializado ('demo', 'real', o ambos)."""
    return list(_clients.keys())


def init_etoro(
    api_key: str, user_key: str, mode: str = "demo"
) -> EtoroClient:
    """Inicializa un cliente global de eToro para un modo concreto."""
    global _default_mode
    m = mode.lower()
    old = _clients.get(m)
    if old is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(old.close())
        except RuntimeError:
            pass
    client = EtoroClient(api_key=api_key, user_key=user_key, mode=m)
    _clients[m] = client
    _default_mode = m
    return client


def init_etoro_from_credentials(
    credentials: dict[str, tuple[str, str]],
    primary_mode: str = "demo",
) -> dict[str, EtoroClient]:
    """
    Inicializa clientes eToro a partir de un dict de credenciales por modo.

    credentials = {"demo": (api_key, user_key), "real": (api_key, user_key)}
    Solo se crean clientes para los modos con credenciales.
    """
    global _default_mode
    requested_primary = primary_mode.lower()

    for mode, (api_key, user_key) in credentials.items():
        init_etoro(api_key, user_key, mode)

    if requested_primary in _clients:
        _default_mode = requested_primary
    elif _clients:
        _default_mode = next(iter(_clients))

    modes = ", ".join(m.upper() for m in _clients)
    logger.info(
        f"🔗 eToro inicializado: {modes} "
        f"(default={_default_mode.upper()})"
    )
    return dict(_clients)


async def shutdown_etoro() -> None:
    """Cierra la conexión de todos los clientes."""
    for m, client in list(_clients.items()):
        await client.close()
    _clients.clear()
