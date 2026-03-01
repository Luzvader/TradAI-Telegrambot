"""Tests para la resolucion de operabilidad en Trading212."""

import pytest

from broker.base import BrokerResult
from broker import bridge


class _MarketAwareClient:
    async def get_instrument_info(self, ticker: str):
        return None

    async def search_instrument(self, query: str) -> BrokerResult:
        return BrokerResult(
            success=True,
            data=[
                {
                    "ticker": "ITX",
                    "ticker_t212": "ITX_US_EQ",
                    "name": "Inditex ADR",
                    "type": "STOCK",
                    "currency": "USD",
                    "isin": "US0000000001",
                },
                {
                    "ticker": "ITX",
                    "ticker_t212": "ITX_ES_EQ",
                    "name": "Industria de Diseno Textil",
                    "type": "STOCK",
                    "currency": "EUR",
                    "isin": "ES0148396007",
                },
            ],
        )

    async def get_all_instruments(self, force_refresh: bool = False):
        return []


class _RefreshOnMissClient:
    def __init__(self) -> None:
        self.refreshed = False
        self.refresh_calls = 0

    async def get_instrument_info(self, ticker: str):
        if not self.refreshed:
            return None
        return {
            "ticker": "ITX",
            "ticker_t212": "ITX_ES_EQ",
            "name": "Industria de Diseno Textil",
            "type": "STOCK",
            "currency": "EUR",
            "isin": "ES0148396007",
        }

    async def search_instrument(self, query: str) -> BrokerResult:
        return BrokerResult(success=True, data=[])

    async def get_all_instruments(self, force_refresh: bool = False):
        self.refreshed = True
        self.refresh_calls += 1
        return []


@pytest.mark.asyncio
async def test_tradability_prefers_requested_market(monkeypatch):
    client = _MarketAwareClient()
    monkeypatch.setattr(bridge, "get_trading212_client", lambda: client)
    bridge._TRADABILITY_CACHE.clear()
    bridge._CATALOG_REFRESHED_ON_MISS = False

    ibex = await bridge.get_trading212_tradability("ITX", market="IBEX")
    nasdaq = await bridge.get_trading212_tradability("ITX", market="NASDAQ")

    assert ibex["tradable"] is True
    assert ibex["instrument_ticker"] == "ITX_ES_EQ"
    assert ibex["requested_market"] == "IBEX"

    assert nasdaq["tradable"] is True
    assert nasdaq["instrument_ticker"] == "ITX_US_EQ"
    assert nasdaq["requested_market"] == "NASDAQ"


@pytest.mark.asyncio
async def test_tradability_refreshes_catalog_once_on_miss(monkeypatch):
    client = _RefreshOnMissClient()
    monkeypatch.setattr(bridge, "get_trading212_client", lambda: client)
    bridge._TRADABILITY_CACHE.clear()
    bridge._CATALOG_REFRESHED_ON_MISS = False

    result = await bridge.get_trading212_tradability("ITX", market="IBEX")
    result_cached = await bridge.get_trading212_tradability("ITX", market="IBEX")

    assert result["tradable"] is True
    assert result["instrument_ticker"] == "ITX_ES_EQ"
    assert result_cached["tradable"] is True
    assert client.refresh_calls == 1
