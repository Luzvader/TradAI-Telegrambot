"""Módulo que contiene un cliente sencillo para consultar TradingView."""

import json
import logging
from typing import Iterable, List, Dict, Any, Optional
from urllib import request, error

# Mapeo de temporalidad (5m, 1h, etc.) a resoluciones compatibles con TradingView.
# El valor `None` indica usar la resolución diaria por defecto.
TIMEFRAME_MAP: Dict[str, Optional[str]] = {
    "5m": "5",
    "15m": "15",
    "1h": "60",
    "4h": "240",
    "1d": None,
    "1w": "1W",
}


def columns_for_timeframe(timeframe: str) -> List[str]:
    """
    Devuelve las columnas apropiadas para la temporalidad dada.
    
    Args:
        timeframe: Cadena representando la temporalidad (por ejemplo, "1h", "1d").
    
    Returns:
        Lista de nombres de columnas para el escáner de TradingView.
    """
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
    """Cliente para obtener datos del escáner de TradingView usando una moneda base."""

    BASE_URL = "https://scanner.tradingview.com/crypto/scan"

    def __init__(self, base_currency: str = "USDT", broker: str = "BINANCE") -> None:
        """
        Inicializa el cliente con una moneda base y un broker específico.

        Args:
            base_currency: Moneda base para los símbolos (por defecto 'USDT').
            broker: Nombre del broker (por defecto 'BINANCE').
        """
        self.base_currency = base_currency
        self.broker = broker

    def _build_payload(
        self,
        symbols: Iterable[str],
        columns: Optional[Iterable[str]] = None
    ) -> Dict[str, Any]:
        """
        Construye el payload JSON requerido por TradingView.
        
        Args:
            symbols: Lista de símbolos (por ejemplo, ["BTC", "ETH"]).
            columns: Lista de columnas a consultar. Si es None, se usan columnas por defecto.
        
        Returns:
            Diccionario con el payload estructurado.
        """
        tickers = [f"{self.broker}:{sym}{self.base_currency}" for sym in symbols]
        default_columns = ["close", "volume", "change", "Recommend.All"]
        payload_columns = list(columns) if columns else default_columns

        return {
            "symbols": {"tickers": tickers, "query": {"types": []}},
            "columns": payload_columns,
        }

    def fetch_markets(
        self,
        symbols: Iterable[str],
        columns: Optional[Iterable[str]] = None
    ) -> Dict[str, List[Any]]:
        """
        Realiza una solicitud al escáner de TradingView para obtener datos de mercado.

        Args:
            symbols: Lista de símbolos de criptomonedas.
            columns: Columnas deseadas en la respuesta (opcional).
        
        Returns:
            Un diccionario mapeando símbolos a sus datos respectivos.
        """
        if not symbols:
            logging.warning("No se proporcionaron símbolos para buscar")
            return {}

        payload = self._build_payload(symbols, columns)
        req = request.Request(
            self.BASE_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        try:
            with request.urlopen(req, timeout=10) as resp:
                response_data = resp.read().decode("utf-8")
                data = json.loads(response_data)
                
                # Verificar si la respuesta contiene un error
                if not isinstance(data, dict):
                    logging.error("Respuesta inesperada de TradingView: %s", response_data[:500])
                    return {}
                    
                if "error" in data:
                    logging.error("Error de TradingView: %s", data.get("error", "Error desconocido"))
                    return {}
                    
                if "data" not in data:
                    logging.error("Estructura de respuesta inesperada: %s", data)
                    return {}

        except (error.URLError, error.HTTPError) as exc:
            logging.warning("Error de conexión con TradingView: %s", str(exc))
            return {}
        except json.JSONDecodeError as exc:
            logging.error("Error al decodificar la respuesta de TradingView: %s", str(exc))
            return {}
        except Exception as exc:
            logging.error("Error inesperado al obtener datos de TradingView: %s", str(exc))
            return {}

        # Convertir la respuesta a un mapeo símbolo -> lista de datos
        markets: Dict[str, List[Any]] = {}
        try:
            for item in data.get("data", []):
                if not isinstance(item, dict):
                    continue
                    
                symbol = item.get("s")
                if not symbol:
                    continue
                    
                market_data = item.get("d", [])
                if not isinstance(market_data, list):
                    market_data = []
                    
                markets[symbol] = market_data
                
        except Exception as exc:
            logging.error("Error al procesar los datos de TradingView: %s", str(exc))
            return {}

        return markets
