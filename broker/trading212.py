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
import json
import logging
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

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
    "EURONEXT_PARIS": "_FR_EQ",
    "EURONEXT_AMSTERDAM": "_NL_EQ",
    "BORSA_ITALIANA": "_IT_EQ",
    "BOLSA_LISBOA": "_PT_EQ",
}

# Mapeo inverso: suffix T212 → mercado TradAI
_SUFFIX_TO_MARKET: dict[str, str] = {
    "_US_EQ": "NASDAQ",
    "_ES_EQ": "IBEX",
    "_UK_EQ": "LSE",
    "_DE_EQ": "XETRA",
    "_FR_EQ": "EURONEXT",
    "_NL_EQ": "EURONEXT_AMSTERDAM",
    "_IT_EQ": "BORSA_ITALIANA",
    "_PT_EQ": "BOLSA_LISBOA",
}

# TTL del catálogo de instrumentos en segundos (24 horas)
_INSTRUMENTS_CATALOG_TTL = 86_400

# Rate limit delays por tipo de endpoint (conservadores)
_RATE_LIMITS = {
    "default": 1.1,       # ~1 req/s por defecto
    "account": 5.0,       # 1 req / 5s
    "positions": 1.0,     # 1 req / 1s
    "orders_get": 5.0,    # 1 req / 5s
    "orders_by_id": 1.0,  # 1 req / 1s
    "orders_market": 1.2, # 50 req / 1min ≈ 1.2s
    "orders_limit": 2.0,  # 1 req / 2s
    "orders_stop": 2.0,   # 1 req / 2s
    "orders_cancel": 1.2, # 50 req / 1min
    "history": 10.0,      # 6 req / 1min
    "instruments": 50.0,  # 1 req / 50s
    "exchanges": 30.0,    # 1 req / 30s
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
        # Caché de resolución ticker → instrumento (para órdenes)
        self._instruments_cache: dict[str, dict] = {}
        # Catálogo completo de instrumentos con TTL
        self._catalog: list[dict] = []
        self._catalog_by_ticker: dict[str, dict] = {}   # ticker limpio → inst
        self._catalog_by_t212: dict[str, dict] = {}      # ticker T212 → inst
        self._catalog_by_isin: dict[str, dict] = {}      # ISIN → inst
        self._catalog_ts: float = 0.0                     # timestamp de última carga
        # Caché de posiciones para precios (TTL corto)
        self._positions_cache: list[BrokerPosition] = []
        self._positions_ts: float = 0.0
        self._positions_ttl: float = 60.0  # 60 segundos
        # Control de rate limit por key (timestamp monotónico de última llamada).
        self._last_call_ts: dict[str, float] = {}
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
            now = time.monotonic()
            last = self._last_call_ts.get(rate_key)
            if last is not None:
                wait_for = delay - (now - last)
                if wait_for > 0:
                    await asyncio.sleep(wait_for)
            self._last_call_ts[rate_key] = time.monotonic()

            async with session.request(
                method, url, json=json_data, params=params
            ) as resp:
                # Leer headers de rate limit para logging
                remaining = resp.headers.get("x-ratelimit-remaining")
                if remaining is not None:
                    try:
                        if int(remaining) < 3:
                            logger.warning(
                                f"⚠️ Trading212 rate limit bajo: {remaining} restantes "
                                f"[{method} {endpoint}]"
                            )
                    except ValueError:
                        logger.debug(
                            f"Header x-ratelimit-remaining no numérico: {remaining}"
                        )

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
                                "Respuesta 2xx con Content-Type JSON pero body no parseable "
                                f"[{method} {endpoint}]"
                            )

                    # Fallback: intentar parsear JSON aunque el content-type no sea correcto.
                    try:
                        return BrokerResult(success=True, data=json.loads(raw))
                    except json.JSONDecodeError:
                        return BrokerResult(success=True, data=raw)

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
            if not isinstance(item, dict):
                continue
            orders.append(self._build_broker_order(item, status_default="UNKNOWN"))

        return BrokerResult(success=True, data=orders)

    async def get_order_by_id(self, order_id: str) -> BrokerResult:
        """
        Obtiene detalle de una orden pendiente.
        GET /equity/orders/{id}
        """
        result = await self._request(
            "GET", f"/equity/orders/{order_id}", rate_key="orders_by_id"
        )
        if not result.success:
            return result

        item = result.data
        if not isinstance(item, dict):
            return BrokerResult(
                success=False,
                error=f"Respuesta inválida para order_id={order_id}",
            )

        return BrokerResult(
            success=True,
            data=self._build_broker_order(item, status_default="UNKNOWN"),
        )

    async def get_historical_order_by_id(
        self, order_id: str, max_pages: int = 5
    ) -> BrokerResult:
        """
        Busca una orden en el histórico paginado (/equity/history/orders).
        Útil cuando el endpoint /equity/orders/{id} devuelve 404 porque la orden
        ya no está pendiente (p.ej. FILLED/CANCELLED).
        """
        target_id = str(order_id).strip()
        if not target_id:
            return BrokerResult(success=False, error="order_id vacío")

        params: dict[str, Any] = {"limit": 50}
        for _ in range(max_pages):
            result = await self._request(
                "GET",
                "/equity/history/orders",
                params=params,
                rate_key="history",
            )
            if not result.success:
                return result

            data = result.data or {}
            if not isinstance(data, dict):
                break

            items = data.get("items", [])
            if not isinstance(items, list):
                break

            for item in items:
                if not isinstance(item, dict):
                    continue

                order_data = item.get("order", item)
                if not isinstance(order_data, dict):
                    continue

                if str(order_data.get("id", "")) != target_id:
                    continue

                fill = item.get("fill")
                if isinstance(fill, dict) and fill:
                    merged = dict(order_data)
                    merged["fill"] = fill
                else:
                    merged = dict(order_data)

                return BrokerResult(
                    success=True,
                    data=self._build_broker_order(merged, status_default="UNKNOWN"),
                )

            cursor = self._extract_cursor(data.get("nextPagePath"))
            if not cursor:
                break
            params = {"limit": 50, "cursor": cursor}

        return BrokerResult(
            success=False,
            error=f"Orden {target_id} no encontrada en histórico",
        )

    # ── Instruments ──────────────────────────────────────────

    async def _ensure_catalog(self, force: bool = False) -> bool:
        """
        Carga el catálogo completo de instrumentos de T212 si no está cacheado
        o si el TTL ha expirado.  Devuelve True si el catálogo está disponible.
        """
        now = time.monotonic()
        if not force and self._catalog and (now - self._catalog_ts) < _INSTRUMENTS_CATALOG_TTL:
            return True  # catálogo vigente

        result = await self._request(
            "GET", "/equity/metadata/instruments", rate_key="instruments"
        )
        if not result.success:
            logger.error(f"Error cargando catálogo de instrumentos: {result.error}")
            return bool(self._catalog)  # devuelve True si hay catálogo viejo

        instruments = result.data or []
        self._catalog = instruments
        self._catalog_by_ticker = {}
        self._catalog_by_t212 = {}
        self._catalog_by_isin = {}

        for inst in instruments:
            t212_ticker = inst.get("ticker", "")
            clean = self._clean_ticker(t212_ticker)
            isin = inst.get("isin", "")
            entry = {
                "ticker_t212": t212_ticker,
                "ticker": clean,
                "name": inst.get("name", ""),
                "short_name": inst.get("shortName", ""),
                "type": inst.get("type", ""),          # STOCK, ETF, etc.
                "currency": inst.get("currencyCode", ""),
                "isin": isin,
                "max_open_qty": inst.get("maxOpenQuantity"),
                "added_on": inst.get("addedOn", ""),
                "working_schedule_id": inst.get("workingScheduleId"),
            }
            self._catalog_by_ticker[clean.upper()] = entry
            self._catalog_by_t212[t212_ticker] = entry
            if isin:
                self._catalog_by_isin[isin] = entry

        self._catalog_ts = now
        logger.info(
            f"📦 Catálogo T212 cargado: {len(instruments)} instrumentos "
            f"({sum(1 for i in instruments if i.get('type') == 'STOCK')} stocks, "
            f"{sum(1 for i in instruments if i.get('type') == 'ETF')} ETFs)"
        )
        return True

    async def get_all_instruments(self, force_refresh: bool = False) -> list[dict]:
        """Devuelve el catálogo completo de instrumentos (cacheado)."""
        await self._ensure_catalog(force=force_refresh)
        return [self._catalog_by_t212[k] for k in self._catalog_by_t212]

    async def get_instrument_info(self, ticker: str) -> dict | None:
        """
        Obtiene info de un instrumento por ticker limpio (ej: 'AAPL').
        Usa el catálogo cacheado. Devuelve None si no existe.
        """
        await self._ensure_catalog()
        return self._catalog_by_ticker.get(ticker.upper().strip())

    async def get_instrument_by_isin(self, isin: str) -> dict | None:
        """Obtiene info de un instrumento por ISIN."""
        await self._ensure_catalog()
        return self._catalog_by_isin.get(isin.upper().strip())

    async def is_tradable(self, ticker: str) -> bool:
        """Comprueba rápidamente si un ticker es operable en T212."""
        await self._ensure_catalog()
        return ticker.upper().strip() in self._catalog_by_ticker

    async def get_tradable_tickers(
        self, asset_type: str | None = None
    ) -> list[str]:
        """
        Devuelve lista de tickers operables en T212.
        asset_type: "STOCK", "ETF", None (todos).
        """
        await self._ensure_catalog()
        result = []
        for tk, info in self._catalog_by_ticker.items():
            if asset_type and info.get("type", "").upper() != asset_type.upper():
                continue
            result.append(tk)
        return result

    def infer_market_from_t212_ticker(self, t212_ticker: str) -> str:
        """
        Infiere el mercado TradAI a partir del ticker T212.
        Ej: 'AAPL_US_EQ' → 'NASDAQ', 'SAN_ES_EQ' → 'IBEX'
        """
        for suffix, market in _SUFFIX_TO_MARKET.items():
            if t212_ticker.endswith(suffix):
                return market
        return "NASDAQ"  # fallback

    async def search_instrument(self, query: str) -> BrokerResult:
        """
        Busca instrumentos por nombre o ticker.
        Usa catálogo cacheado en lugar de llamar a la API cada vez.
        """
        ok = await self._ensure_catalog()
        if not ok:
            return BrokerResult(success=False, error="No se pudo cargar catálogo de instrumentos")

        query_upper = query.upper().strip()
        matches = []
        for inst in self._catalog_by_t212.values():
            ticker = inst.get("ticker", "")
            t212 = inst.get("ticker_t212", "")
            name = inst.get("name", "")
            short = inst.get("short_name", "")
            if (
                query_upper in ticker.upper()
                or query_upper in t212.upper()
                or query_upper in name.upper()
                or query_upper in short.upper()
            ):
                matches.append({
                    "ticker_t212": t212,
                    "ticker": ticker,
                    "name": name,
                    "short_name": short,
                    "type": inst.get("type", ""),
                    "currency": inst.get("currency", ""),
                    "isin": inst.get("isin", ""),
                    "min_trade_qty": inst.get("min_trade_qty"),
                    "max_open_qty": inst.get("max_open_qty"),
                })

        return BrokerResult(success=True, data=matches[:20])

    async def get_instrument_by_ticker(self, ticker: str) -> BrokerResult:
        """Obtiene info de un instrumento específico usando catálogo cacheado."""
        info = await self.get_instrument_info(ticker)
        if info:
            return BrokerResult(success=True, data=info)

        # Fallback: buscar por coincidencia parcial
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
            rate_key="history",
        )

    async def get_dividend_history(self, limit: int = 20) -> BrokerResult:
        """
        Obtiene historial de dividendos recibidos.
        GET /equity/history/dividends?limit=N
        """
        return await self._request(
            "GET", "/equity/history/dividends",
            params={"limit": min(limit, 50)},
            rate_key="history",
        )

    async def get_dividend_history_all(self) -> BrokerResult:
        """
        Obtiene el historial COMPLETO de dividendos con paginación cursor-based.
        Devuelve lista de todos los dividendos recibidos en la cuenta.
        """
        all_items: list[dict] = []
        params: dict[str, Any] = {"limit": 50}
        max_pages = 20  # seguridad contra bucle infinito

        for _ in range(max_pages):
            result = await self._request(
                "GET", "/equity/history/dividends",
                params=params, rate_key="history",
            )
            if not result.success:
                if all_items:
                    return BrokerResult(success=True, data=all_items)
                return result

            data = result.data
            if isinstance(data, dict):
                items = data.get("items", [])
                next_path = data.get("nextPagePath")
            elif isinstance(data, list):
                items = data
                next_path = None
            else:
                break

            all_items.extend(items)

            if not next_path or not items:
                break

            cursor = self._extract_cursor(next_path)
            if not cursor:
                break
            params = {"limit": 50, "cursor": cursor}

        return BrokerResult(success=True, data=all_items)

    async def get_transaction_history(self, limit: int = 20) -> BrokerResult:
        """
        Obtiene historial de transacciones.
        GET /equity/history/transactions?limit=N
        """
        return await self._request(
            "GET", "/equity/history/transactions",
            params={"limit": min(limit, 50)},
            rate_key="history",
        )

    # ── Metadata ─────────────────────────────────────────────

    async def get_exchanges(self) -> BrokerResult:
        """GET /equity/metadata/exchanges"""
        return await self._request(
            "GET", "/equity/metadata/exchanges", rate_key="exchanges"
        )

    # ── Helpers ──────────────────────────────────────────────

    def _clean_ticker(self, raw: str) -> str:
        """
        Limpia ticker de Trading212 a formato estándar.
        Ej: "AAPL_US_EQ" → "AAPL", "SAN_ES_EQ" → "SAN"
        """
        if not raw:
            return raw
        for suffix in _SUFFIX_TO_MARKET:
            if raw.endswith(suffix):
                return raw[: -len(suffix)]
        if raw.endswith("_EQ"):
            return raw[:-3]
        if "_" in raw:
            return raw.split("_")[0]
        return raw

    # ── Precios desde posiciones (caché corto) ───────────────

    async def get_positions_prices(self) -> dict[str, float]:
        """
        Devuelve {ticker_limpio: current_price} de todas las posiciones T212.
        Útil para obtener precios real-time de instrumentos en cartera sin
        usar yfinance. Cache de 60 segundos.
        """
        now = time.monotonic()
        if self._positions_cache and (now - self._positions_ts) < self._positions_ttl:
            return {p.ticker.upper(): p.current_price for p in self._positions_cache}

        result = await self.get_positions()
        if result.success and result.data:
            self._positions_cache = result.data
            self._positions_ts = now
            return {p.ticker.upper(): p.current_price for p in result.data}
        return {}

    async def get_positions_details(self) -> list[BrokerPosition]:
        """
        Devuelve posiciones T212 con caché corto (60s).
        Incluye ticker, shares, avg_price, current_price, pnl, currency, etc.
        """
        now = time.monotonic()
        if self._positions_cache and (now - self._positions_ts) < self._positions_ttl:
            return self._positions_cache

        result = await self.get_positions()
        if result.success and result.data:
            self._positions_cache = result.data
            self._positions_ts = now
            return result.data
        return []

    async def _resolve_ticker(self, ticker: str) -> str | None:
        """
        Convierte un ticker estándar (ej: "AAPL") al formato Trading212
        (ej: "AAPL_US_EQ"). Usa catálogo cacheado.
        """
        ticker = ticker.upper().strip()

        if ticker in self._instruments_cache:
            return self._instruments_cache[ticker]["ticker_t212"]

        # Intentar desde catálogo cacheado primero
        info = await self.get_instrument_info(ticker)
        if info:
            self._instruments_cache[ticker] = info
            return info["ticker_t212"]

        # Fallback: búsqueda parcial
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
        return self._build_broker_order(
            data,
            fallback_ticker=ticker,
            fallback_side=side.upper(),
            status_default="NEW",
        )

    @staticmethod
    def _extract_cursor(next_path: Any) -> str | None:
        """Extrae cursor=... de un nextPagePath relativo o absoluto."""
        if not isinstance(next_path, str) or not next_path:
            return None

        parsed = urlparse(next_path)
        if parsed.query:
            cursor = parse_qs(parsed.query).get("cursor", [None])[0]
            return str(cursor) if cursor else None

        if "cursor=" in next_path:
            return next_path.split("cursor=", 1)[1].split("&", 1)[0] or None
        return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _infer_filled_price(self, item: dict[str, Any]) -> float | None:
        """Infiere precio de ejecución desde fill.price o filledValue/filledQuantity."""
        fill = item.get("fill")
        if isinstance(fill, dict):
            fill_price = self._to_float(fill.get("price"))
            if fill_price is not None and fill_price > 0:
                return fill_price

        filled_value = self._to_float(item.get("filledValue"))
        filled_qty = self._to_float(item.get("filledQuantity"))
        if filled_value is not None and filled_qty is not None and abs(filled_qty) > 0:
            return filled_value / abs(filled_qty)
        return None

    def _build_broker_order(
        self,
        item: dict[str, Any],
        fallback_ticker: str = "",
        fallback_side: str = "BUY",
        status_default: str = "UNKNOWN",
    ) -> BrokerOrder:
        instrument = item.get("instrument", {})
        fill = item.get("fill", {}) if isinstance(item.get("fill"), dict) else {}

        ticker_raw = ""
        if isinstance(instrument, dict):
            ticker_raw = instrument.get("ticker", "") or ""
        if not ticker_raw:
            ticker_raw = str(item.get("ticker", fallback_ticker))

        filled_shares = item.get("filledQuantity")
        if filled_shares is None and fill:
            filled_shares = fill.get("quantity")

        order_price = item.get("limitPrice")
        if order_price is None:
            order_price = item.get("stopPrice")

        timestamp = item.get("createdAt") or fill.get("filledAt", "")

        return BrokerOrder(
            order_id=str(item.get("id", "")),
            ticker=self._clean_ticker(ticker_raw),
            side=str(item.get("side", fallback_side)).upper(),
            shares=abs(self._to_float(item.get("quantity")) or 0.0),
            price=self._to_float(order_price),
            status=str(item.get("status", status_default)).upper(),
            filled_price=self._infer_filled_price(item),
            filled_shares=self._to_float(filled_shares),
            timestamp=str(timestamp or ""),
        )


# ── Singleton global (soporta dual: demo + live) ────────────

_clients: dict[str, Trading212Client] = {}
_default_mode: str = "demo"


def get_trading212_client(mode: str | None = None) -> Trading212Client | None:
    """
    Devuelve el cliente Trading212 para el modo dado.
    Si mode=None, usa el modo por defecto (TRADING212_MODE).
    """
    m = (mode or _default_mode).lower()
    return _clients.get(m)


def get_available_modes() -> list[str]:
    """Devuelve los modos con cliente inicializado ('demo', 'live', o ambos)."""
    return list(_clients.keys())


def init_trading212(
    api_key: str, api_secret: str, mode: str = "demo"
) -> Trading212Client:
    """Inicializa un cliente global de Trading212 para un modo concreto."""
    global _default_mode
    m = mode.lower()
    old = _clients.get(m)
    if old is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(old.close())
        except RuntimeError:
            pass
    client = Trading212Client(api_key=api_key, api_secret=api_secret, mode=m)
    _clients[m] = client
    _default_mode = m
    return client


def init_trading212_dual(
    api_key: str, api_secret: str, primary_mode: str = "demo",
) -> dict[str, Trading212Client]:
    """
    Inicializa DOS clientes Trading212 (demo + live) con las mismas
    credenciales.  ``primary_mode`` se usa como default cuando no se
    especifica modo.

    NOTA: normalmente cada modo requiere credenciales distintas.
    Usa ``init_trading212_from_credentials`` para el caso habitual.
    """
    global _default_mode
    _default_mode = primary_mode.lower()
    for m in ("demo", "live"):
        init_trading212(api_key, api_secret, m)
    logger.info("🔗 Trading212 dual: demo + live inicializados")
    return dict(_clients)


def init_trading212_from_credentials(
    credentials: dict[str, tuple[str, str]],
    primary_mode: str = "demo",
) -> dict[str, Trading212Client]:
    """
    Inicializa clientes Trading212 a partir de un dict de credenciales
    por modo.  Cada modo (demo/live) tiene su propio par (key, secret).

    ``credentials`` = {"demo": (key, secret), "live": (key, secret)}
    Solo se crean clientes para los modos con credenciales.
    """
    global _default_mode
    requested_primary = primary_mode.lower()

    for mode, (key, secret) in credentials.items():
        init_trading212(key, secret, mode)

    # El modo por defecto debe respetar el primary_mode solicitado
    # (si existe), no el último cliente inicializado.
    if requested_primary in _clients:
        _default_mode = requested_primary
    elif _clients:
        _default_mode = next(iter(_clients))

    modes = ", ".join(m.upper() for m in _clients)
    logger.info(
        f"🔗 Trading212 inicializado: {modes} "
        f"(default={_default_mode.upper()})"
    )
    return dict(_clients)


async def shutdown_trading212() -> None:
    """Cierra la conexión de todos los clientes."""
    for m, client in list(_clients.items()):
        await client.close()
    _clients.clear()
