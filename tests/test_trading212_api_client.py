"""Tests de compatibilidad del cliente Trading212 con respuestas API reales."""

from unittest.mock import AsyncMock

import pytest

from broker.base import BrokerResult
from broker.trading212 import Trading212Client


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


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def request(self, *args, **kwargs):
        return self._response


@pytest.mark.asyncio
async def test_request_accepts_2xx_without_json_body(monkeypatch):
    client = Trading212Client("key", "secret", mode="demo")
    response = _FakeResponse(status=200, headers={"Content-Type": "text/plain"}, body="")

    monkeypatch.setattr(client, "_get_session", AsyncMock(return_value=_FakeSession(response)))

    result = await client._request("DELETE", "/equity/orders/1", rate_key="orders_cancel")

    assert result.success is True
    assert result.data is None


@pytest.mark.asyncio
async def test_get_historical_order_by_id_parses_nested_order_and_fill(monkeypatch):
    client = Trading212Client("key", "secret", mode="demo")

    payload = {
        "items": [
            {
                "order": {
                    "id": 123,
                    "ticker": "AAPL_US_EQ",
                    "side": "BUY",
                    "quantity": 2,
                    "status": "FILLED",
                    "createdAt": "2026-03-02T10:00:00Z",
                },
                "fill": {
                    "price": 101.5,
                    "quantity": 2,
                    "filledAt": "2026-03-02T10:00:01Z",
                },
            }
        ],
        "nextPagePath": None,
    }

    async def _fake_request(method, endpoint, json_data=None, params=None, rate_key="default"):
        return BrokerResult(success=True, data=payload)

    monkeypatch.setattr(client, "_request", _fake_request)

    result = await client.get_historical_order_by_id("123")

    assert result.success is True
    assert result.data.order_id == "123"
    assert result.data.ticker == "AAPL"
    assert result.data.status == "FILLED"
    assert result.data.filled_price == 101.5
    assert result.data.filled_shares == 2
