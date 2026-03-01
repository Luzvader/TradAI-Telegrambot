"""
Repositorio – Signals, Watchlist, Earnings.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Sequence

from sqlalchemy import select, func

from database.connection import async_session_factory
from database.models import (
    AssetType,
    EarningsEvent,
    Signal,
    SignalType,
    WatchlistItem,
    WatchlistStatus,
)

logger = logging.getLogger(__name__)


# ── Signals ──────────────────────────────────────────────────


async def save_signal(
    ticker: str,
    market: str,
    signal_type: SignalType,
    price: float | None = None,
    value_score: float | None = None,
    risk_score: float | None = None,
    reasoning: str | None = None,
    ai_analysis: str | None = None,
) -> Signal:
    async with async_session_factory() as session:
        sig = Signal(
            ticker=ticker.upper(),
            market=market,
            signal_type=signal_type,
            price=price,
            value_score=value_score,
            risk_score=risk_score,
            reasoning=reasoning,
            ai_analysis=ai_analysis,
        )
        session.add(sig)
        await session.commit()
        await session.refresh(sig)
        return sig


async def get_recent_signals(limit: int = 10) -> Sequence[Signal]:
    async with async_session_factory() as session:
        stmt = (
            select(Signal).order_by(Signal.created_at.desc()).limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()


async def get_signals_since(since: datetime, limit: int = 50) -> Sequence[Signal]:
    """Obtiene señales desde una fecha dada."""
    async with async_session_factory() as session:
        stmt = (
            select(Signal)
            .where(Signal.created_at >= since)
            .order_by(Signal.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()


async def has_recent_signal(
    ticker: str,
    signal_type: SignalType,
    hours: int = 24,
    market: str | None = None,
) -> bool:
    """Comprueba si ya existe una señal reciente del mismo tipo para el ticker.

    Si se proporciona `market`, se filtra por mercado. Para US (NASDAQ/NYSE),
    se deduplica de forma conjunta porque yfinance no distingue por sufijo.
    """
    async with async_session_factory() as session:
        since = datetime.now(UTC) - timedelta(hours=hours)
        where_clauses = [
            Signal.ticker == ticker.upper(),
            Signal.signal_type == signal_type,
            Signal.created_at >= since,
        ]
        if market:
            mk = market.upper()
            if mk in ("NASDAQ", "NYSE"):
                where_clauses.append(Signal.market.in_(("NASDAQ", "NYSE")))
            else:
                where_clauses.append(Signal.market == mk)

        stmt = select(func.count(Signal.id)).where(*where_clauses)
        result = await session.execute(stmt)
        count = result.scalar() or 0
        return count > 0


# ── Watchlist ────────────────────────────────────────────────


async def get_active_watchlist() -> Sequence[WatchlistItem]:
    async with async_session_factory() as session:
        stmt = select(WatchlistItem).where(
            WatchlistItem.status == WatchlistStatus.ACTIVE
        )
        result = await session.execute(stmt)
        return result.scalars().all()


async def add_to_watchlist(
    ticker: str,
    market: str,
    sector: str | None = None,
    reason: str | None = None,
    ai_notes: str | None = None,
    asset_type: AssetType = AssetType.STOCK,
) -> WatchlistItem | None:
    """Añade un ticker. Devuelve None si ya hay 100 activos."""
    async with async_session_factory() as session:
        count_stmt = select(func.count()).where(
            WatchlistItem.status == WatchlistStatus.ACTIVE
        )
        count_result = await session.execute(count_stmt)
        count = count_result.scalar() or 0
        if count >= 100:
            return None

        item = WatchlistItem(
            ticker=ticker.upper(),
            market=market,
            asset_type=asset_type,
            sector=sector,
            reason=reason,
            ai_notes=ai_notes,
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item


async def remove_from_watchlist(ticker: str) -> bool:
    async with async_session_factory() as session:
        stmt = select(WatchlistItem).where(
            WatchlistItem.ticker == ticker.upper(),
            WatchlistItem.status == WatchlistStatus.ACTIVE,
        )
        result = await session.execute(stmt)
        item = result.scalar_one_or_none()
        if item is None:
            return False
        item.status = WatchlistStatus.REMOVED
        item.removed_at = datetime.now(UTC)
        await session.commit()
        return True


# ── Earnings ─────────────────────────────────────────────────


async def save_earnings_event(
    ticker: str, **kwargs
) -> EarningsEvent:
    async with async_session_factory() as session:
        event = EarningsEvent(ticker=ticker.upper(), **kwargs)
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event


async def get_upcoming_earnings(
    tickers: list[str],
) -> Sequence[EarningsEvent]:
    async with async_session_factory() as session:
        now = datetime.now(UTC)
        stmt = (
            select(EarningsEvent)
            .where(
                EarningsEvent.ticker.in_([t.upper() for t in tickers]),
                EarningsEvent.report_date >= now,
            )
            .order_by(EarningsEvent.report_date.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()
