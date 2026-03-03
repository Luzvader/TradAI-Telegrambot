"""Tests para el procesamiento de órdenes límite pendientes."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from broker.base import BrokerResult
from database.models import OperationOrigin
from scheduler import jobs


class _FilledBrokerOrder:
    status = "FILLED"
    filled_price = 99.5
    price = 99.5


class _MockEtoroClient:
    async def get_order_by_id(self, order_id: str) -> BrokerResult:
        return BrokerResult(success=True, data=_FilledBrokerOrder())


class _MockEtoroClientHistoryFallback:
    async def get_order_by_id(self, order_id: str) -> BrokerResult:
        return BrokerResult(success=False, error="HTTP 404: not found")

    async def get_historical_order_by_id(self, order_id: str) -> BrokerResult:
        return BrokerResult(success=True, data=_FilledBrokerOrder())


def _pending_order() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        portfolio_id=10,
        ticker="AAPL",
        market="NASDAQ",
        shares=2.0,
        limit_price=100.0,
        broker_order_id="order-123",
        asset_type=None,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


@pytest.mark.asyncio
async def test_filled_limit_order_registers_local_buy_without_reexecuting_broker(monkeypatch):
    order = _pending_order()
    mark_filled = AsyncMock()
    notify = AsyncMock()
    buy_mock = AsyncMock(return_value={"success": True})

    monkeypatch.setattr(
        jobs.repo, "get_pending_limit_orders_active", AsyncMock(return_value=[order])
    )
    monkeypatch.setattr(
        jobs.repo, "get_portfolio", AsyncMock(return_value=SimpleNamespace(id=10))
    )
    monkeypatch.setattr(jobs.repo, "mark_limit_order_filled", mark_filled)
    monkeypatch.setattr(jobs, "_notify", notify)
    monkeypatch.setattr(
        "broker.etoro.get_etoro_client", lambda: _MockEtoroClient()
    )
    monkeypatch.setattr("portfolio.portfolio_manager.execute_buy", buy_mock)

    await jobs.job_check_pending_limit_orders()

    assert buy_mock.await_count == 1
    kwargs = buy_mock.await_args.kwargs
    assert kwargs["skip_broker_execution"] is True
    assert kwargs["origin"] == OperationOrigin.IMPORT
    assert mark_filled.await_count == 1


@pytest.mark.asyncio
async def test_filled_limit_order_not_marked_when_local_registration_fails(monkeypatch):
    order = _pending_order()
    mark_filled = AsyncMock()
    buy_mock = AsyncMock(return_value={"success": False, "error": "db error"})

    monkeypatch.setattr(
        jobs.repo, "get_pending_limit_orders_active", AsyncMock(return_value=[order])
    )
    monkeypatch.setattr(
        jobs.repo, "get_portfolio", AsyncMock(return_value=SimpleNamespace(id=10))
    )
    monkeypatch.setattr(jobs.repo, "mark_limit_order_filled", mark_filled)
    monkeypatch.setattr(jobs, "_notify", AsyncMock())
    monkeypatch.setattr(
        "broker.etoro.get_etoro_client", lambda: _MockEtoroClient()
    )
    monkeypatch.setattr("portfolio.portfolio_manager.execute_buy", buy_mock)

    await jobs.job_check_pending_limit_orders()

    assert buy_mock.await_count == 1
    assert mark_filled.await_count == 0


@pytest.mark.asyncio
async def test_filled_limit_order_uses_history_when_pending_endpoint_returns_404(monkeypatch):
    order = _pending_order()
    mark_filled = AsyncMock()
    buy_mock = AsyncMock(return_value={"success": True})

    monkeypatch.setattr(
        jobs.repo, "get_pending_limit_orders_active", AsyncMock(return_value=[order])
    )
    monkeypatch.setattr(
        jobs.repo, "get_portfolio", AsyncMock(return_value=SimpleNamespace(id=10))
    )
    monkeypatch.setattr(jobs.repo, "mark_limit_order_filled", mark_filled)
    monkeypatch.setattr(jobs, "_notify", AsyncMock())
    monkeypatch.setattr(
        "broker.etoro.get_etoro_client", lambda: _MockEtoroClientHistoryFallback()
    )
    monkeypatch.setattr("portfolio.portfolio_manager.execute_buy", buy_mock)

    await jobs.job_check_pending_limit_orders()

    assert buy_mock.await_count == 1
    assert mark_filled.await_count == 1
