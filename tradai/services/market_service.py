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
}

from ..tradingview import TradingViewClient, columns_for_timeframe

_client = TradingViewClient()

DEFAULT_SYMBOLS: Sequence[str] = ("BTC", "ETH", "XRP", "SOL", "BNB")

def fetch_basic(symbols: Sequence[str] | None = None, period: str = "24h"):
    """Return latest price and change (% change) for the given symbols and period."""
    if symbols is None:
        symbols = DEFAULT_SYMBOLS

    res = PERIOD_MAP.get(period, None)
    suffix = f"|{res}" if res else ""
    cols = [
        "close",
        f"change{suffix}",
    ]
    raw = _client.fetch_markets(list(symbols), columns=cols)
    # Convert keys like 'BINANCE:BTCUSDT' -> 'BTC'
    cleaned = {
        key.split(":")[1].removesuffix("USDT"): val for key, val in raw.items()
    }
    return cleaned

def fetch_with_indicators(symbols: Sequence[str] | None, timeframe: str):
    """Return price plus indicators for symbols and timeframe."""
    if symbols is None:
        symbols = DEFAULT_SYMBOLS
    cols = columns_for_timeframe(timeframe)
    return _client.fetch_markets(list(symbols), columns=cols)
