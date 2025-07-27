"""Market data service layer.

This module wraps TradingViewClient so that the FastAPI routers do not
need to know implementation details.  It will be easier to swap the
provider or add caching in one place later.
"""
from __future__ import annotations

from typing import List, Sequence

PERIOD_MAP = {
    "1h": "60",
    "4h": "240",
    "24h": None,  # default daily change
    "1w": "1W",
    "1m": "1M",
    "3m": "3M",
    "6m": "6M",
    "1y": "1Y",
    "ytd": "YTD",
}

from ..tradingview import TradingViewClient, columns_for_timeframe

# --- Función para obtener datos históricos de Binance ---
import requests
import pandas as pd
import socket
import time

from ..indicators import ema, rsi, macd, atr, detect_candle
from ..strategies import generate_signals

def get_crypto_signals(symbol: str, interval: str = "5m"):
    """
    Descarga datos históricos, calcula indicadores y genera señales para un símbolo.
    Devuelve un diccionario con los datos relevantes para la interfaz web.
    """
    df = fetch_binance_historical(symbol, interval)
    if df is None or df.empty:
        return {"symbol": symbol, "error": "No hay datos"}

    # Calcular indicadores
    df['ema'] = df['close'].ewm(span=14, adjust=True).mean()
    df['rsi'] = df['close'].rolling(window=15).apply(lambda x: rsi(x, 14))
    macd_vals = df['close'].rolling(window=35).apply(lambda x: macd(x, 12, 26, 9)[0] if macd(x, 12, 26, 9) else None)
    macd_signal_vals = df['close'].rolling(window=35).apply(lambda x: macd(x, 12, 26, 9)[1] if macd(x, 12, 26, 9) else None)
    df['macd'] = macd_vals
    df['macd_signal'] = macd_signal_vals
    df['atr'] = df[['high', 'low', 'close']].rolling(window=15).apply(lambda x: atr(x[:,0], x[:,1], x[:,2], 14) if len(x) == 15 else None)
    # Detectar patrones de vela
    patterns = []
    for i in range(1, len(df)):
        pattern = detect_candle(df['open'].iloc[max(0,i-1):i+1], df['high'].iloc[max(0,i-1):i+1], df['low'].iloc[max(0,i-1):i+1], df['close'].iloc[max(0,i-1):i+1])
        patterns.append(pattern if pattern else "None")
    df['candle_pattern'] = ["None"] + patterns

    # Generar señales
    signals = generate_signals(df, symbol)
    latest = {
        "symbol": symbol,
        "latest_price": float(df['close'].iloc[-1]),
        "latest_signal": signals[-1] if signals else "N/A",
        "latest_rsi": float(df['rsi'].iloc[-1]) if pd.notna(df['rsi'].iloc[-1]) else None,
        "latest_macd": float(df['macd'].iloc[-1]) if pd.notna(df['macd'].iloc[-1]) else None,
        "latest_atr": float(df['atr'].iloc[-1]) if pd.notna(df['atr'].iloc[-1]) else None,
        "latest_candle": df['candle_pattern'].iloc[-1],
        "signals": signals,
    }
    return latest

BINANCE_URL = "https://api.binance.com/api/v3/klines"

def fetch_binance_historical(symbol: str, interval: str = "5m", max_retries: int = 3, retry_delay: int = 5):
    """Obtiene datos históricos de Binance con lógica de reintentos."""
    for attempt in range(max_retries):
        try:
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": 1000
            }
            response = requests.get(BINANCE_URL, params=params)
            response.raise_for_status()
            data = response.json()
            if not data:
                raise ValueError(f"No se obtuvieron datos para {symbol}")
            df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume",
                                            "close_time", "quote_asset_vol", "number_of_trades",
                                            "taker_buy_base_asset_vol", "taker_buy_quote_asset_vol", "ignore"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric)
            return df.sort_values(by="timestamp")
        except socket.gaierror as e:
            if e.errno == -3:
                print(f"Fallo temporal de resolución de nombre para {symbol} (intento {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    print(f"No se pudo obtener datos para {symbol} tras {max_retries} intentos")
                    return None
            else:
                raise
        except requests.exceptions.RequestException as e:
            print(f"Error obteniendo datos para {symbol} (intento {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                print(f"No se pudo obtener datos para {symbol} tras {max_retries} intentos")
                return None

_client = TradingViewClient()

DEFAULT_SYMBOLS: Sequence[str] = ("BTC", "ETH", "XRP", "SOL", "BNB")

def fetch_basic(symbols: Sequence[str] | None = None, period: str = "24h") -> dict:
    """Return latest price and change (% change) for the given symbols and period.
    
    Args:
        symbols: List of symbols to fetch data for. If None, uses DEFAULT_SYMBOLS.
        period: Time period for the change calculation (e.g., '24h', '1w').
        
    Returns:
        Dictionary mapping symbols to their market data. Empty dict on error.
    """
    try:
        if symbols is None:
            symbols = DEFAULT_SYMBOLS
        elif not symbols:
            logging.warning("No symbols provided to fetch_basic")
            return {}

        res = PERIOD_MAP.get(period)
        suffix = f"|{res}" if res else ""
        cols = ["close", f"change{suffix}"]
        
        raw = _client.fetch_markets(list(symbols), columns=cols)
        if not raw:
            logging.warning("No data received from TradingView")
            return {}
            
        # Convert keys like 'BINANCE:BTCUSDT' -> 'BTC'
        cleaned = {}
        for key, val in raw.items():
            try:
                if ":" in key and key.endswith("USDT"):
                    symbol = key.split(":")[1].removesuffix("USDT")
                    cleaned[symbol] = val
            except Exception as e:
                logging.warning("Error processing symbol %s: %s", key, str(e))
                continue
                
        return cleaned
        
    except Exception as e:
        logging.error("Error in fetch_basic: %s", str(e), exc_info=True)
        return {}

def fetch_with_indicators(symbols: Sequence[str] | None, timeframe: str) -> dict:
    """Return price plus indicators for symbols and timeframe.
    
    Args:
        symbols: List of symbols to fetch data for. If None, uses DEFAULT_SYMBOLS.
        timeframe: Timeframe for the indicators (e.g., '1h', '4h').
        
    Returns:
        Dictionary mapping symbols to their market data with indicators. Empty dict on error.
    """
    try:
        if symbols is None:
            symbols = DEFAULT_SYMBOLS
        elif not symbols:
            logging.warning("No symbols provided to fetch_with_indicators")
            return {}
            
        cols = columns_for_timeframe(timeframe)
        if not cols:
            logging.error("No columns defined for timeframe: %s", timeframe)
            return {}
            
        result = _client.fetch_markets(list(symbols), columns=cols)
        if not result:
            logging.warning("No data received for indicators from TradingView")
            
        return result
        
    except Exception as e:
        logging.error("Error in fetch_with_indicators: %s", str(e), exc_info=True)
        return {}
