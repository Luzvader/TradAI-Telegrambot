"""Market data service layer.

This module wraps TradingViewClient so that the FastAPI routers do not
need to know implementation details.  It will be easier to swap the
provider or add caching in one place later.
"""
from __future__ import annotations

from typing import List, Sequence

from ..tradingview import TradingViewClient, columns_for_timeframe

_client = TradingViewClient()

DEFAULT_SYMBOLS: Sequence[str] = ("BTC", "ETH", "XRP", "SOL", "BNB")

def fetch_basic(symbols: Sequence[str] | None = None):
    """Return latest price and change for the given symbols."""
    if symbols is None:
        symbols = DEFAULT_SYMBOLS
    return _client.fetch_markets(list(symbols))

def fetch_with_indicators(symbols: Sequence[str] | None, timeframe: str):
    """Return price plus indicators for symbols and timeframe."""
    if symbols is None:
        symbols = DEFAULT_SYMBOLS
    cols = columns_for_timeframe(timeframe)
    return _client.fetch_markets(list(symbols), columns=cols)
