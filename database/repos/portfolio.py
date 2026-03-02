"""
Repositorio – Portfolio, Positions, Operations, Cash, Strategy, Snapshots.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import select, update

from database.connection import async_session_factory
from database.models import (
    AssetType,
    Operation,
    OperationOrigin,
    OperationSide,
    Portfolio,
    PortfolioSnapshot,
    PortfolioType,
    Position,
    PositionStatus,
    StrategyType,
    PendingLimitOrder,
    PendingLimitOrderStatus,
)

logger = logging.getLogger(__name__)


# ── Portfolio ────────────────────────────────────────────────


async def get_or_create_portfolio(
    name: str, ptype: PortfolioType,
) -> Portfolio:
    async with async_session_factory() as session:
        stmt = select(Portfolio).where(
            Portfolio.name == name, Portfolio.portfolio_type == ptype
        )
        result = await session.execute(stmt)
        portfolio = result.scalar_one_or_none()
        if portfolio is None:
            portfolio = Portfolio(
                name=name, portfolio_type=ptype,
            )
            session.add(portfolio)
            await session.commit()
            await session.refresh(portfolio)
            logger.info(f"📁 Portfolio creado: {name} ({ptype.value})")
        return portfolio


async def get_portfolio(portfolio_id: int) -> Optional[Portfolio]:
    async with async_session_factory() as session:
        return await session.get(Portfolio, portfolio_id)


async def get_portfolio_by_type(ptype: PortfolioType) -> Optional[Portfolio]:
    async with async_session_factory() as session:
        stmt = select(Portfolio).where(Portfolio.portfolio_type == ptype)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


# ── Positions ────────────────────────────────────────────────


async def get_open_positions(portfolio_id: int) -> Sequence[Position]:
    async with async_session_factory() as session:
        stmt = select(Position).where(
            Position.portfolio_id == portfolio_id,
            Position.status == PositionStatus.OPEN,
        )
        result = await session.execute(stmt)
        return result.scalars().all()


async def get_position_by_ticker(
    portfolio_id: int, ticker: str, market: str | None = None
) -> Optional[Position]:
    async with async_session_factory() as session:
        stmt = select(Position).where(
            Position.portfolio_id == portfolio_id,
            Position.ticker == ticker.upper(),
            Position.status == PositionStatus.OPEN,
        )
        if market:
            mk = market.upper()
            if mk in ("NASDAQ", "NYSE"):
                stmt = stmt.where(Position.market.in_(("NASDAQ", "NYSE")))
            else:
                stmt = stmt.where(Position.market == mk)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def upsert_position(
    portfolio_id: int,
    ticker: str,
    market: str,
    sector: str | None,
    shares: float,
    avg_price: float,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    asset_type: AssetType | None = None,
) -> Position:
    async with async_session_factory() as session:
        market_norm = (market or "NASDAQ").upper()
        stmt = select(Position).where(
            Position.portfolio_id == portfolio_id,
            Position.ticker == ticker.upper(),
            Position.status == PositionStatus.OPEN,
        )
        if market_norm in ("NASDAQ", "NYSE"):
            stmt = stmt.where(Position.market.in_(("NASDAQ", "NYSE")))
        else:
            stmt = stmt.where(Position.market == market_norm)
        result = await session.execute(stmt)
        pos = result.scalar_one_or_none()

        if pos is None:
            pos = Position(
                portfolio_id=portfolio_id,
                ticker=ticker.upper(),
                market=market_norm,
                sector=sector,
                shares=shares,
                avg_price=avg_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                asset_type=asset_type or AssetType.STOCK,
            )
            session.add(pos)
        else:
            # Actualizar media ponderada
            total_cost = pos.shares * pos.avg_price + shares * avg_price
            pos.shares += shares
            pos.avg_price = total_cost / pos.shares if pos.shares > 0 else 0
            if stop_loss is not None:
                pos.stop_loss = stop_loss
            if take_profit is not None:
                pos.take_profit = take_profit
            # Actualizar sector si estaba vacío
            if sector and (pos.sector is None or pos.sector == "N/A"):
                pos.sector = sector
            # Actualizar asset_type si se proporcionó y no se había establecido
            if asset_type is not None:
                pos.asset_type = asset_type

        await session.commit()
        await session.refresh(pos)
        return pos


async def close_position(position_id: int) -> None:
    async with async_session_factory() as session:
        stmt = (
            update(Position)
            .where(Position.id == position_id)
            .values(status=PositionStatus.CLOSED, closed_at=datetime.now(UTC))
        )
        await session.execute(stmt)
        await session.commit()


async def update_position_price(position_id: int, price: float) -> None:
    async with async_session_factory() as session:
        stmt = (
            update(Position)
            .where(Position.id == position_id)
            .values(current_price=price)
        )
        await session.execute(stmt)
        await session.commit()


async def update_position_sector(position_id: int, sector: str) -> None:
    """Actualiza el sector de una posición (para posiciones antiguas sin sector)."""
    async with async_session_factory() as session:
        stmt = (
            update(Position)
            .where(Position.id == position_id)
            .values(sector=sector)
        )
        await session.execute(stmt)
        await session.commit()


# ── Operations ───────────────────────────────────────────────


async def record_operation(
    portfolio_id: int,
    ticker: str,
    market: str,
    side: OperationSide,
    price: float,
    amount_usd: float,
    shares: float,
    notes: str | None = None,
    origin: OperationOrigin = OperationOrigin.MANUAL,
) -> Operation:
    async with async_session_factory() as session:
        op = Operation(
            portfolio_id=portfolio_id,
            ticker=ticker.upper(),
            market=market,
            side=side,
            price=price,
            amount_usd=amount_usd,
            shares=shares,
            notes=notes,
            origin=origin,
        )
        session.add(op)
        await session.commit()
        await session.refresh(op)
        return op


async def get_operations(
    portfolio_id: int, limit: int = 20
) -> Sequence[Operation]:
    async with async_session_factory() as session:
        stmt = (
            select(Operation)
            .where(Operation.portfolio_id == portfolio_id)
            .order_by(Operation.timestamp.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()


# ── Strategy ─────────────────────────────────────────────────


async def set_portfolio_strategy(
    portfolio_id: int, strategy: StrategyType
) -> bool:
    """Establece la estrategia activa de un portfolio."""
    async with async_session_factory() as session:
        stmt = (
            update(Portfolio)
            .where(Portfolio.id == portfolio_id)
            .values(strategy=strategy)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0


async def get_portfolio_strategy(portfolio_id: int) -> StrategyType | None:
    """Obtiene la estrategia activa de un portfolio."""
    async with async_session_factory() as session:
        portfolio = await session.get(Portfolio, portfolio_id)
        return portfolio.strategy if portfolio else None


# ── Cash Management ──────────────────────────────────────────


async def update_portfolio_cash(portfolio_id: int, cash: float) -> None:
    """Actualiza el cash disponible de un portfolio."""
    async with async_session_factory() as session:
        stmt = (
            update(Portfolio)
            .where(Portfolio.id == portfolio_id)
            .values(cash=cash)
        )
        await session.execute(stmt)
        await session.commit()


async def set_initial_capital(portfolio_id: int, capital: float) -> None:
    """Establece el capital inicial y el cash de un portfolio."""
    async with async_session_factory() as session:
        stmt = (
            update(Portfolio)
            .where(Portfolio.id == portfolio_id)
            .values(initial_capital=capital, cash=capital)
        )
        await session.execute(stmt)
        await session.commit()


async def set_initial_capital_only(portfolio_id: int, capital: float) -> None:
    """Establece solo el capital inicial, sin modificar cash."""
    async with async_session_factory() as session:
        stmt = (
            update(Portfolio)
            .where(Portfolio.id == portfolio_id)
            .values(initial_capital=capital)
        )
        await session.execute(stmt)
        await session.commit()


async def adjust_cash(portfolio_id: int, delta: float) -> float:
    """Ajusta el cash (positivo = entrada, negativo = salida). Devuelve nuevo cash."""
    async with async_session_factory() as session:
        portfolio = await session.get(Portfolio, portfolio_id)
        if portfolio is None:
            return 0
        portfolio.cash = (portfolio.cash or 0) + delta
        await session.commit()
        return portfolio.cash


async def set_cash(portfolio_id: int, amount: float) -> float:
    """Establece el cash a un valor absoluto. Devuelve el nuevo cash."""
    async with async_session_factory() as session:
        portfolio = await session.get(Portfolio, portfolio_id)
        if portfolio is None:
            return 0
        portfolio.cash = amount
        await session.commit()
        return portfolio.cash


# ── Portfolio Snapshots (NAV tracking) ───────────────────────


async def save_portfolio_snapshot(
    portfolio_id: int,
    total_value: float,
    invested_value: float,
    cash: float,
    num_positions: int,
    pnl: float | None = None,
    pnl_pct: float | None = None,
    benchmark_value: float | None = None,
) -> PortfolioSnapshot:
    """Guarda un snapshot diario del portfolio."""
    async with async_session_factory() as session:
        snap = PortfolioSnapshot(
            portfolio_id=portfolio_id,
            total_value=total_value,
            invested_value=invested_value,
            cash=cash,
            num_positions=num_positions,
            pnl=pnl,
            pnl_pct=pnl_pct,
            benchmark_value=benchmark_value,
        )
        session.add(snap)
        await session.commit()
        await session.refresh(snap)
        return snap


async def get_portfolio_snapshots(
    portfolio_id: int, limit: int = 90
) -> Sequence[PortfolioSnapshot]:
    """Obtiene los últimos snapshots del portfolio."""
    async with async_session_factory() as session:
        stmt = (
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.portfolio_id == portfolio_id)
            .order_by(PortfolioSnapshot.snapshot_date.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()


# ── Pending Limit Orders ─────────────────────────────────────


async def create_pending_limit_order(
    portfolio_id: int,
    ticker: str,
    market: str,
    shares: float,
    limit_price: float,
    broker_order_id: str | None = None,
    chat_id: str | None = None,
    asset_type: str | None = None,
    ttl_hours: int = 24,
) -> PendingLimitOrder:
    """Registra una nueva orden límite pendiente."""
    async with async_session_factory() as session:
        now = datetime.now(UTC)
        order = PendingLimitOrder(
            portfolio_id=portfolio_id,
            ticker=ticker.upper(),
            market=market,
            shares=shares,
            limit_price=limit_price,
            broker_order_id=broker_order_id,
            chat_id=chat_id,
            asset_type=asset_type,
            status=PendingLimitOrderStatus.PENDING,
            placed_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        logger.info(
            f"📋 Limit order registrada: {ticker} x{shares} @ {limit_price} "
            f"(broker_id={broker_order_id}, expira={order.expires_at.isoformat()})"
        )
        return order


async def get_pending_limit_orders_active() -> Sequence[PendingLimitOrder]:
    """Devuelve todas las órdenes límite con estado PENDING."""
    async with async_session_factory() as session:
        stmt = select(PendingLimitOrder).where(
            PendingLimitOrder.status == PendingLimitOrderStatus.PENDING
        )
        result = await session.execute(stmt)
        return result.scalars().all()


async def mark_limit_order_filled(
    order_id: int,
    filled_price: float | None = None,
) -> None:
    """Marca una orden límite como ejecutada."""
    async with async_session_factory() as session:
        stmt = (
            update(PendingLimitOrder)
            .where(PendingLimitOrder.id == order_id)
            .values(
                status=PendingLimitOrderStatus.FILLED,
                filled_at=datetime.now(UTC),
                filled_price=filled_price,
            )
        )
        await session.execute(stmt)
        await session.commit()


async def mark_limit_order_cancelled(order_id: int) -> None:
    """Marca una orden límite como cancelada manualmente."""
    async with async_session_factory() as session:
        stmt = (
            update(PendingLimitOrder)
            .where(PendingLimitOrder.id == order_id)
            .values(status=PendingLimitOrderStatus.CANCELLED)
        )
        await session.execute(stmt)
        await session.commit()


async def mark_limit_order_expired(order_id: int) -> None:
    """Marca una orden límite como expirada (24h sin ejecución)."""
    async with async_session_factory() as session:
        stmt = (
            update(PendingLimitOrder)
            .where(PendingLimitOrder.id == order_id)
            .values(status=PendingLimitOrderStatus.EXPIRED)
        )
        await session.execute(stmt)
        await session.commit()
