"""Módulo que contiene un cliente sencillo para consultar TradingView."""

from typing import Iterable, List, Dict, Any
from urllib import request, error
import json
import logging

# Mapeo de temporalidad de la interfaz (5m, 1h, etc.) a la resolución
# que TradingView entiende en las columnas del escáner. La clave
# ``None`` significa usar la temporalidad por defecto (diaria).
TIMEFRAME_MAP: Dict[str, str | None] = {
    "5m": "5",
    "15m": "15",
    "1h": "60",
    "4h": "240",
    "1d": None,
    "1w": "1W",
}


def columns_for_timeframe(timeframe: str) -> List[str]:
    """Devuelve las columnas apropiadas para la temporalidad dada."""
    resolution = TIMEFRAME_MAP.get(timeframe)
    suffix = f"|{resolution}" if resolution else ""
    return [
        f"open{suffix}",
        f"high{suffix}",
        f"low{suffix}",
        f"close{suffix}",
        f"EMA20{suffix}",
        f"EMA50{suffix}",
        f"RSI{suffix}",
    ]


class TradingViewClient:
    """Cliente para obtener datos de TradingView usando USDT como moneda base."""

    BASE_URL = "https://scanner.tradingview.com/crypto/scan"

    def __init__(self, base_currency: str = "USDT", broker: str = "BINANCE") -> None:
        """Inicializa el cliente con la moneda base y el broker."""
        self.base_currency = base_currency
        self.broker = broker

    def _build_payload(
        self, symbols: Iterable[str], columns: Iterable[str] | None = None
    ) -> Dict[str, Any]:
        """Construye el JSON que TradingView espera para la consulta."""
        tickers = [f"{self.broker}:{sym}{self.base_currency}" for sym in symbols]
        default_columns = ["close", "volume", "change", "Recommend.All"]
        payload_columns = list(columns) if columns is not None else default_columns
        return {
            "symbols": {"tickers": tickers, "query": {"types": []}},
            "columns": payload_columns,
        }

    def fetch_markets(
        self, symbols: Iterable[str], columns: Iterable[str] | None = None
    ) -> Dict[str, List[Any]]:
        """Devuelve los datos de mercado para los símbolos proporcionados."""
        payload = self._build_payload(symbols, columns)
        req = request.Request(
            self.BASE_URL,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        # Abrimos la conexión y parseamos la respuesta JSON
        try:
            with request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
        except (error.URLError, error.HTTPError) as exc:
            logging.warning("TradingView request failed: %s", exc)
            return {}

        markets: Dict[str, List[Any]] = {}
        # Convertimos la estructura recibida a un mapeo símbolo -> datos
        for item in data.get("data", []):
            markets[item.get("s", "")] = item.get("d", [])
        return markets
