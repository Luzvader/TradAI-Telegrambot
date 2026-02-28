"""
Cliente Trading212 API v0 – integración completa.

Docs:  https://docs.trading212.com/api
Auth:  HTTP Basic Auth → Base64(API_KEY:API_SECRET)
Envs:  demo.trading212.com  |  live.trading212.com

Endpoints soportados:
  • GET  /equity/account/summary         → Cuenta
  • GET  /equity/positions               → Posiciones abiertas
  • GET  /equity/orders                  → Órdenes pendientes
  • POST /equity/orders/market           → Orden de mercado
  • POST /equity/orders/limit            → Orden limitada
  • POST /equity/orders/stop             → Orden stop
  • POST /equity/orders/stop_limit       → Orden stop-limit
  • DELETE /equity/orders/{id}           → Cancelar orden
  • GET  /equity/orders/{id}             → Detalle de orden
  • GET  /equity/metadata/instruments    → Instrumentos
  • GET  /equity/metadata/exchanges      → Exchanges
  • GET  /equity/history/orders          → Historial órdenes
  • GET  /equity/history/dividends       → Historial dividendos
  • GET  /equity/history/transactions    → Historial transacciones
"""

import asyncio
import base64
import logging
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

BASE_URLS = {
    "demo": "https://demo.trading212.com/api/v0",
    "live": "https://live.trading212.com/api/v0",
}

# Mapeo mercado TradAI → exchange suffix Trading212
MARKET_EXCHANGE_MAP = {
    "NASDAQ": "_US_EQ",
    "NYSE": "_US_EQ",
    "IBEX": "_ES_EQ",
    "LSE": "_UK_EQ",
    "XETRA": "_DE_EQ",
    "EURONEXT": "_FR_EQ",
}

# Rate limit delays por tipo de endpoint (conservadores)
_RATE_LIMITS = {
    "default": 1.1,       # ~1 req/s por defecto
    "account": 5.0,       # 1 req / 5s
    "positions": 1.0,     # 1 req / 1s
    "orders_get": 5.0,    # 1 req / 5s
    "orders_market": 1.2, # 50 req / 1min ≈ 1.2s
    "orders_limit": 2.0,  # 1 req / 2s
    "orders_stop": 2.0,   # 1 req / 2s
    "orders_cancel": 1.2, # 50 req / 1min
    "instruments": 1.0,   # 1 req / 1s
}


def _build_basic_auth(api_key: str, api_secret: str) -> str:
    """Construye el header Authorization: Basic <base64(key:secret)>."""
    credentials = f"{api_key}:{api_secret}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return f"Basic {encoded}"


class Trading212Client(BaseBroker):
    """
    Cliente para la API de Trading212.
    Soporta modo demo y live con la misma interfaz.
    Usa HTTP Basic Auth con API_KEY:API_SECRET.
    """

    def __init__(self, api_key: str, api_secret: str, mode: str = "demo"):
        if mode not in ("demo", "live"):
            raise ValueError(f"Modo inválido: {mode}. Usa 'demo' o 'live'.")
        if not api_key or not api_secret:
            raise ValueError("API key y API secret son obligatorios.")
        self.api_key = api_key
        self.api_secret = api_secret
        self.mode = mode
        self.base_url = BASE_URLS[mode]
        self._auth_header = _build_basic_auth(api_key, api_secret)
        self._session: aiohttp.ClientSession | None = None
        self._instruments_cache: dict[str, dict] = {}
        logger.info(f"🔗 Trading212 configurado en modo {mode.upper()}")

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": self._auth_header,
            "Content-Type": "application/json",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self.headers,
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
        json_data: dict | None = None,
        params: dict | None = None,
        rate_key: str = "default",
    ) -> BrokerResult:
        """Ejecuta una petición HTTP a la API de Trading212."""
        url = f"{self.base_url}{endpoint}"

        try:
            session = await self._get_session()
            delay = _RATE_LIMITS.get(rate_key, _RATE_LIMITS["default"])
            await asyncio.sleep(delay)

            async with session.request(
                method, url, json=json_data, params=params
            ) as resp:
                # Leer headers de rate limit para logging
                remaining = resp.headers.get("x-ratelimit-remaining")
                if remaining is not None and int(remaining) < 3:
                    logger.warning(
                        f"⚠️ Trading212 rate limit bajo: {remaining} restantes "
                        f"[{method} {endpoint}]"
                    )

                if resp.status == 200:
                    data = await resp.json()
                    return BrokerResult(success=True, data=data)
                elif resp.status == 204:
                    return BrokerResult(success=True, data=None)
                else:
                    text = await resp.text()
                    logger.error(
                        f"Trading212 API error {resp.status}: {text} "
                        f"[{method} {endpoint}]"
                    )
                    return BrokerResult(
                        success=False,
                        error=f"HTTP {resp.status}: {text}",
                    )
        except aiohttp.ClientError as e:
            logger.error(f"Trading212 connection error: {e}")
            return BrokerResult(success=False, error=f"Connection error: {e}")
        except Exception as e:
            logger.error(f"Trading212 unexpected error: {e}")
            return BrokerResult(success=False, error=str(e))

    # ── Account ──────────────────────────────────────────────

    async def get_account(self) -> BrokerResult:
        """
        Obtiene información de la cuenta.
        GET /equity/account/summary
        Response: {cash: {availableToTrade, inPies, reservedForOrders},
                   currency, id, investments: {currentValue, realizedProfitLoss,
                   totalCost, unrealizedProfitLoss}, totalValue}
        """
        result = await self._request(
            "GET", "/equity/account/summary", rate_key="account"
        )
        if not result.success:
            return result

        data = result.data
        cash_data = data.get("cash", {})
        investments = data.get("investments", {})

        account = BrokerAccount(
            cash=cash_data.get("availableToTrade", 0),
            invested=investments.get("totalCost", 0),
            portfolio_value=data.get("totalValue", 0),
            pnl=investments.get("unrealizedProfitLoss", 0),
            pnl_pct=(
                (investments.get("unrealizedProfitLoss", 0)
                 / investments.get("totalCost", 1) * 100)
                if investments.get("totalCost", 0) > 0 else 0
            ),
            currency=data.get("currency", "EUR"),
            mode=self.mode,
        )
        return BrokerResult(success=True, data=account)

    # ── Positions ────────────────────────────────────────────

    async def get_positions(self) -> BrokerResult:
        """
        Obtiene todas las posiciones abiertas.
        GET /equity/positions
        Response: [{averagePricePaid, createdAt, currentPrice,
                    instrument: {currency, isin, name, ticker},
                    quantity, quantityAvailableForTrading,
                    quantityInPies, walletImpact: {...}}]
        """
        result = await self._request(
            "GET", "/equity/positions", rate_key="positions"
        )
        if not result.success:
            return result

        positions = []
        for item in result.data or []:
            instrument = item.get("instrument", {})
            ticker_raw = instrument.get("ticker", "")
            ticker = self._clean_ticker(ticker_raw)

            avg_price = item.get("averagePricePaid", 0)
            current_price = item.get("currentPrice", 0)
            quantity = item.get("quantity", 0)
            pnl = (current_price - avg_price) * quantity
            pnl_pct = (
                (current_price - avg_price) / avg_price * 100
                if avg_price > 0 else 0
            )
            market_value = current_price * quantity

            positions.append(BrokerPosition(
                ticker=ticker,
                shares=quantity,
                avg_price=avg_price,
                current_price=current_price,
                pnl=round(pnl, 2),
                pnl_pct=round(pnl_pct, 2),
                market_value=round(market_value, 2),
                currency=instrument.get("currency", "USD"),
                frontend_name=instrument.get("name", ticker),
            ))

        return BrokerResult(success=True, data=positions)

    # ── Orders ───────────────────────────────────────────────

    async def place_market_order(
        self, ticker: str, shares: float, side: str
    ) -> BrokerResult:
        """
        Coloca una orden de mercado.
        POST /equity/orders/market
        Body: {quantity: float, ticker: str, extendedHours: bool}
        NOTA: Para SELL, quantity debe ser negativa.
        """
        t212_ticker = await self._resolve_ticker(ticker)
        if t212_ticker is None:
            return BrokerResult(
                success=False,
                error=f"No se encontró el instrumento '{ticker}' en Trading212",
            )

        quantity = abs(shares)
        if side.upper() == "SELL":
            quantity = -quantity

        payload = {
            "quantity": quantity,
            "ticker": t212_ticker,
            "extendedHours": False,
        }

        result = await self._request(
            "POST", "/equity/orders/market",
            json_data=payload, rate_key="orders_market",
        )
        if not result.success:
            return result

        order = self._parse_order_response(result.data, ticker, side)

        logger.info(
            f"📤 Trading212 [{self.mode.upper()}] "
            f"Market {side} {ticker}: {abs(shares)} acciones → {order.status}"
        )
        return BrokerResult(success=True, data=order)

    async def place_limit_order(
        self, ticker: str, shares: float, side: str, limit_price: float,
        time_validity: str = "GOOD_TILL_CANCEL",
    ) -> BrokerResult:
        """
        Coloca una orden limitada.
        POST /equity/orders/limit
        Body: {limitPrice, quantity, ticker, timeValidity}
        """
        t212_ticker = await self._resolve_ticker(ticker)
        if t212_ticker is None:
            return BrokerResult(
                success=False,
                error=f"No se encontró el instrumento '{ticker}' en Trading212",
            )

        quantity = abs(shares)
        if side.upper() == "SELL":
            quantity = -quantity

        payload = {
            "limitPrice": limit_price,
            "quantity": quantity,
            "ticker": t212_ticker,
            "timeValidity": time_validity,
        }

        result = await self._request(
            "POST", "/equity/orders/limit",
            json_data=payload, rate_key="orders_limit",
        )
        if not result.success:
            return result

        order = self._parse_order_response(result.data, ticker, side)

        logger.info(
            f"📤 Trading212 [{self.mode.upper()}] "
            f"Limit {side} {ticker}: {abs(shares)} @ {limit_price}$ → {order.status}"
        )
        return BrokerResult(success=True, data=order)

    async def place_stop_order(
        self, ticker: str, shares: float, side: str, stop_price: float,
        time_validity: str = "GOOD_TILL_CANCEL",
    ) -> BrokerResult:
        """
        Coloca una orden stop.
        POST /equity/orders/stop
        Body: {quantity, stopPrice, ticker, timeValidity}
        """
        t212_ticker = await self._resolve_ticker(ticker)
        if t212_ticker is None:
            return BrokerResult(
                success=False,
                error=f"No se encontró el instrumento '{ticker}' en Trading212",
            )

        quantity = abs(shares)
        if side.upper() == "SELL":
            quantity = -quantity

        payload = {
            "quantity": quantity,
            "stopPrice": stop_price,
            "ticker": t212_ticker,
            "timeValidity": time_validity,
        }

        result = await self._request(
            "POST", "/equity/orders/stop",
            json_data=payload, rate_key="orders_stop",
        )
        if not result.success:
            return result

        order = self._parse_order_response(result.data, ticker, side)

        logger.info(
            f"📤 Trading212 [{self.mode.upper()}] "
            f"Stop {side} {ticker}: {abs(shares)} @ stop {stop_price}$ → {order.status}"
        )
        return BrokerResult(success=True, data=order)

    async def place_stop_limit_order(
        self, ticker: str, shares: float, side: str,
        stop_price: float, limit_price: float,
        time_validity: str = "GOOD_TILL_CANCEL",
    ) -> BrokerResult:
        """
        Coloca una orden stop-limit.
        POST /equity/orders/stop_limit
        Body: {limitPrice, quantity, stopPrice, ticker, timeValidity}
        """
        t212_ticker = await self._resolve_ticker(ticker)
        if t212_ticker is None:
            return BrokerResult(
                success=False,
                error=f"No se encontró el instrumento '{ticker}' en Trading212",
            )

        quantity = abs(shares)
        if side.upper() == "SELL":
            quantity = -quantity

        payload = {
            "limitPrice": limit_price,
            "quantity": quantity,
            "stopPrice": stop_price,
            "ticker": t212_ticker,
            "timeValidity": time_validity,
        }

        result = await self._request(
            "POST", "/equity/orders/stop_limit",
            json_data=payload, rate_key="orders_stop",
        )
        if not result.success:
            return result

        order = self._parse_order_response(result.data, ticker, side)

        logger.info(
            f"📤 Trading212 [{self.mode.upper()}] "
            f"StopLimit {side} {ticker}: {abs(shares)} "
            f"stop {stop_price}$ limit {limit_price}$ → {order.status}"
        )
        return BrokerResult(success=True, data=order)

    async def place_value_order(
        self, ticker: str, amount: float, side: str
    ) -> BrokerResult:
        """
        Órdenes por valor monetario NO están soportadas por la API de Trading212.
        La API solo soporta órdenes por cantidad (QUANTITY).
        """
        return BrokerResult(
            success=False,
            error=(
                "Órdenes por valor (value orders) no están soportadas por la API "
                "de Trading212. Usa market/limit/stop con cantidad de acciones."
            ),
        )

    async def cancel_order(self, order_id: str) -> BrokerResult:
        """
        Cancela una orden pendiente.
        DELETE /equity/orders/{id}
        """
        result = await self._request(
            "DELETE", f"/equity/orders/{order_id}",
            rate_key="orders_cancel",
        )
        if result.success:
            logger.info(f"❌ Trading212 orden {order_id} cancelada")
        return result

    async def get_orders(self) -> BrokerResult:
        """
        Obtiene órdenes pendientes.
        GET /equity/orders
        """
        result = await self._request(
            "GET", "/equity/orders", rate_key="orders_get"
        )
        if not result.success:
            return result

        orders = []
        for item in result.data or []:
            instrument = item.get("instrument", {})
            orders.append(BrokerOrder(
                order_id=str(item.get("id", "")),
                ticker=self._clean_ticker(
                    instrument.get("ticker", item.get("ticker", ""))
                ),
                side=item.get("side", "BUY"),
                shares=abs(item.get("quantity", 0)),
                price=item.get("limitPrice"),
                status=item.get("status", "UNKNOWN"),
                filled_price=None,
                filled_shares=item.get("filledQuantity"),
                timestamp=item.get("createdAt", ""),
            ))

        return BrokerResult(success=True, data=orders)

    async def get_order_by_id(self, order_id: str) -> BrokerResult:
        """
        Obtiene detalle de una orden pendiente.
        GET /equity/orders/{id}
        """
        result = await self._request(
            "GET", f"/equity/orders/{order_id}", rate_key="default"
        )
        if not result.success:
            return result

        item = result.data
        instrument = item.get("instrument", {})
        order = BrokerOrder(
            order_id=str(item.get("id", "")),
            ticker=self._clean_ticker(
                instrument.get("ticker", item.get("ticker", ""))
            ),
            side=item.get("side", "BUY"),
            shares=abs(item.get("quantity", 0)),
            price=item.get("limitPrice"),
            status=item.get("status", "UNKNOWN"),
            filled_price=None,
            filled_shares=item.get("filledQuantity"),
            timestamp=item.get("createdAt", ""),
        )
        return BrokerResult(success=True, data=order)

    # ── Instruments ──────────────────────────────────────────

    async def search_instrument(self, query: str) -> BrokerResult:
        """
        Busca instrumentos por nombre o ticker.
        GET /equity/metadata/instruments
        Nota: la API devuelve TODOS los instrumentos; filtramos localmente.
        """
        result = await self._request(
            "GET", "/equity/metadata/instruments", rate_key="instruments"
        )
        if not result.success:
            return result

        instruments = result.data or []
        query_upper = query.upper()
        matches = []
        for inst in instruments:
            ticker = inst.get("ticker", "")
            name = inst.get("name", "")
            short = inst.get("shortName", "")
            if (
                query_upper in ticker.upper()
                or query_upper in name.upper()
                or query_upper in short.upper()
            ):
                matches.append({
                    "ticker_t212": ticker,
                    "ticker": self._clean_ticker(ticker),
                    "name": name,
                    "short_name": short,
                    "type": inst.get("type", ""),
                    "currency": inst.get("currencyCode", ""),
                    "isin": inst.get("isin", ""),
                    "min_trade_qty": inst.get("minTradeQuantity"),
                    "max_open_qty": inst.get("maxOpenQuantity"),
                })

        return BrokerResult(success=True, data=matches[:20])

    async def get_instrument_by_ticker(self, ticker: str) -> BrokerResult:
        """Obtiene info de un instrumento específico."""
        result = await self.search_instrument(ticker)
        if not result.success:
            return result

        for inst in result.data or []:
            if inst["ticker"].upper() == ticker.upper():
                return BrokerResult(success=True, data=inst)

        if result.data:
            return BrokerResult(success=True, data=result.data[0])

        return BrokerResult(
            success=False,
            error=f"Instrumento '{ticker}' no encontrado en Trading212",
        )

    # ── History (paginado con cursor) ────────────────────────

    async def get_order_history(self, limit: int = 20) -> BrokerResult:
        """
        Obtiene historial de órdenes ejecutadas.
        GET /equity/history/orders?limit=N
        """
        return await self._request(
            "GET", "/equity/history/orders",
            params={"limit": min(limit, 50)},
            rate_key="default",
        )

    async def get_dividend_history(self, limit: int = 20) -> BrokerResult:
        """
        Obtiene historial de dividendos recibidos.
        GET /equity/history/dividends?limit=N
        """
        return await self._request(
            "GET", "/equity/history/dividends",
            params={"limit": min(limit, 50)},
            rate_key="default",
        )

    async def get_transaction_history(self, limit: int = 20) -> BrokerResult:
        """
        Obtiene historial de transacciones.
        GET /equity/history/transactions?limit=N
        """
        return await self._request(
            "GET", "/equity/history/transactions",
            params={"limit": min(limit, 50)},
            rate_key="default",
        )

    # ── Metadata ─────────────────────────────────────────────

    async def get_exchanges(self) -> BrokerResult:
        """GET /equity/metadata/exchanges"""
        return await self._request(
            "GET", "/equity/metadata/exchanges", rate_key="instruments"
        )

    # ── Helpers ──────────────────────────────────────────────

    def _clean_ticker(self, raw: str) -> str:
        """
        Limpia ticker de Trading212 a formato estándar.
        Ej: "AAPL_US_EQ" → "AAPL", "SAN_ES_EQ" → "SAN"
        """
        if not raw:
            return raw
        for suffix in ("_US_EQ", "_ES_EQ", "_UK_EQ", "_DE_EQ", "_FR_EQ",
                        "_NL_EQ", "_IT_EQ", "_PT_EQ", "_EQ"):
            if raw.endswith(suffix):
                return raw[: -len(suffix)]
        if "_" in raw:
            return raw.split("_")[0]
        return raw

    async def _resolve_ticker(self, ticker: str) -> str | None:
        """
        Convierte un ticker estándar (ej: "AAPL") al formato Trading212
        (ej: "AAPL_US_EQ"). Cachea resultados.
        """
        ticker = ticker.upper().strip()

        if ticker in self._instruments_cache:
            return self._instruments_cache[ticker]["ticker_t212"]

        result = await self.search_instrument(ticker)
        if not result.success or not result.data:
            return None

        # Buscar match exacto
        for inst in result.data:
            if inst["ticker"].upper() == ticker:
                self._instruments_cache[ticker] = inst
                return inst["ticker_t212"]

        # Usar el primer resultado como fallback
        inst = result.data[0]
        self._instruments_cache[ticker] = inst
        return inst["ticker_t212"]

    def _parse_order_response(
        self, data: dict | None, ticker: str, side: str
    ) -> BrokerOrder:
        """Parsea la respuesta estándar de una orden."""
        data = data or {}
        instrument = data.get("instrument", {})
        return BrokerOrder(
            order_id=str(data.get("id", "")),
            ticker=self._clean_ticker(
                instrument.get("ticker", data.get("ticker", ticker))
            ),
            side=data.get("side", side.upper()),
            shares=abs(data.get("quantity", 0)),
            price=data.get("limitPrice"),
            status=data.get("status", "NEW"),
            filled_price=None,
            filled_shares=data.get("filledQuantity"),
            timestamp=data.get("createdAt", ""),
        )


# ── Singleton global ─────────────────────────────────────────

_client: Trading212Client | None = None


def get_trading212_client() -> Trading212Client | None:
    """Devuelve el cliente singleton de Trading212 (None si no configurado)."""
    return _client


def init_trading212(
    api_key: str, api_secret: str, mode: str = "demo"
) -> Trading212Client:
    """Inicializa el cliente global de Trading212."""
    global _client
    if _client is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_client.close())
        except RuntimeError:
            pass
    _client = Trading212Client(api_key=api_key, api_secret=api_secret, mode=mode)
    return _client


async def shutdown_trading212() -> None:
    """Cierra la conexión del cliente."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
