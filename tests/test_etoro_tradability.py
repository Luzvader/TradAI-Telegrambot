"""Tests para la resolución de operabilidad en eToro."""

import pytest

from broker.base import BrokerResult
from broker import bridge
from broker import etoro


class _SearchClient:
    """Cliente mock que devuelve resultados de búsqueda con distintos símbolos."""

    async def search_instrument(self, query: str) -> BrokerResult:
        return BrokerResult(
            success=True,
            data=[
                {
                    "symbol": "ITX",
                    "instrument_id": 1001,
                    "name": "Inditex ADR",
                    "type": "STOCK",
                    "tradable": True,
                    "buy_enabled": True,
                    "current_rate": 38.50,
                },
                {
                    "symbol": "ITXE",
                    "instrument_id": 1002,
                    "name": "Inditex SA (EUR)",
                    "type": "STOCK",
                    "tradable": True,
                    "buy_enabled": True,
                    "current_rate": 34.00,
                },
            ],
        )


class _SearchEmptyClient:
    """Cliente mock que no encuentra nada."""

    async def search_instrument(self, query: str) -> BrokerResult:
        return BrokerResult(success=True, data=[])


@pytest.mark.asyncio
async def test_tradability_finds_exact_match(monkeypatch):
    client = _SearchClient()
    monkeypatch.setattr(bridge, "get_etoro_client", lambda: client)
    bridge._TRADABILITY_CACHE.clear()

    result = await bridge.get_etoro_tradability("ITX")

    assert result["tradable"] is True
    assert result["instrument_id"] == 1001
    assert result["ticker"] == "ITX"


@pytest.mark.asyncio
async def test_tradability_falls_back_to_first_result(monkeypatch):
    client = _SearchClient()
    monkeypatch.setattr(bridge, "get_etoro_client", lambda: client)
    bridge._TRADABILITY_CACHE.clear()

    result = await bridge.get_etoro_tradability("UNKNOWN_TICKER")

    # No exact match found → falls back to first result
    assert result["tradable"] is True
    assert result["matched_symbol"] == "ITX"


@pytest.mark.asyncio
async def test_tradability_returns_not_found_for_empty_results(monkeypatch):
    client = _SearchEmptyClient()
    monkeypatch.setattr(bridge, "get_etoro_client", lambda: client)
    bridge._TRADABILITY_CACHE.clear()

    result = await bridge.get_etoro_tradability("NOPE")

    assert result["tradable"] is False
    assert "No encontrado" in result["reason"]


@pytest.mark.asyncio
async def test_tradability_uses_cache(monkeypatch):
    client = _SearchClient()
    call_count = 0
    original_search = client.search_instrument

    async def _counting_search(query):
        nonlocal call_count
        call_count += 1
        return await original_search(query)

    client.search_instrument = _counting_search
    monkeypatch.setattr(bridge, "get_etoro_client", lambda: client)
    bridge._TRADABILITY_CACHE.clear()

    r1 = await bridge.get_etoro_tradability("ITX")
    r2 = await bridge.get_etoro_tradability("ITX")

    assert r1["tradable"] is True
    assert r2["tradable"] is True
    assert call_count == 1  # Second call should use cache


@pytest.mark.asyncio
async def test_tradability_with_market_param(monkeypatch):
    client = _SearchClient()
    monkeypatch.setattr(bridge, "get_etoro_client", lambda: client)
    bridge._TRADABILITY_CACHE.clear()

    result = await bridge.get_etoro_tradability("ITX", market="NASDAQ")

    assert result["tradable"] is True
    assert result["requested_market"] == "NASDAQ"


def test_init_from_credentials_respects_primary_mode_demo():
    etoro._clients.clear()
    etoro._default_mode = "real"

    creds = {
        "demo": ("demo_api_key", "demo_user_key"),
        "real": ("real_api_key", "real_user_key"),
    }
    etoro.init_etoro_from_credentials(creds, primary_mode="demo")

    default_client = etoro.get_etoro_client()
    assert default_client is not None
    assert default_client.mode == "demo"
    etoro._clients.clear()


def test_init_from_credentials_respects_primary_mode_real():
    etoro._clients.clear()
    etoro._default_mode = "demo"

    creds = {
        "demo": ("demo_api_key", "demo_user_key"),
        "real": ("real_api_key", "real_user_key"),
    }
    etoro.init_etoro_from_credentials(creds, primary_mode="real")

    default_client = etoro.get_etoro_client()
    assert default_client is not None
    assert default_client.mode == "real"
    etoro._clients.clear()
