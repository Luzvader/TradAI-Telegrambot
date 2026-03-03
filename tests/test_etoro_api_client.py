"""Tests de compatibilidad del cliente eToro con respuestas API."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from broker.base import BrokerResult
from broker.etoro import EtoroClient


class _FakeResponse:
    def __init__(self, status: int, headers: dict[str, str] | None = None, body: str = ""):
        self.status = status
        self.headers = headers or {}
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self) -> str:
        return self._body

    async def json(self):
        import json
        return json.loads(self._body)


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def request(self, *args, **kwargs):
        return self._response


@pytest.mark.asyncio
async def test_client_initializes_with_correct_mode():
    client = EtoroClient("test_key", "test_user", mode="demo")
    assert client.mode == "demo"
    assert client.api_key == "test_key"
    assert client.user_key == "test_user"


@pytest.mark.asyncio
async def test_client_real_mode():
    client = EtoroClient("key", "user", mode="real")
    assert client.mode == "real"


@pytest.mark.asyncio
async def test_search_instrument_returns_broker_result(monkeypatch):
    client = EtoroClient("key", "user", mode="demo")

    fake_result = BrokerResult(
        success=True,
        data=[
            {
                "symbol": "AAPL",
                "instrument_id": 1234,
                "name": "Apple Inc.",
                "type": "STOCK",
            }
        ],
    )

    monkeypatch.setattr(client, "search_instrument", AsyncMock(return_value=fake_result))

    result = await client.search_instrument("AAPL")
    assert result.success is True
    assert len(result.data) == 1
    assert result.data[0]["symbol"] == "AAPL"
