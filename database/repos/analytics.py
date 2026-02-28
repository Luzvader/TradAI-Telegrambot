"""
Repositorio – Learning, Market Context, OpenAI Usage, Dividends.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Sequence

from sqlalchemy import select, func

from database.connection import async_session_factory
from database.models import (
    DividendPayment,
    LearningLog,
    MarketContext,
    OpenAIUsage,
)

logger = logging.getLogger(__name__)


# ── Learning ─────────────────────────────────────────────────


async def save_learning_log(log: LearningLog) -> LearningLog:
    async with async_session_factory() as session:
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log


async def get_learning_logs(limit: int = 50) -> Sequence[LearningLog]:
    async with async_session_factory() as session:
        stmt = (
            select(LearningLog)
            .order_by(LearningLog.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()


async def get_learning_summary() -> dict:
    """Estadísticas agregadas del aprendizaje."""
    async with async_session_factory() as session:
        total = await session.execute(select(func.count(LearningLog.id)))
        wins = await session.execute(
            select(func.count(LearningLog.id)).where(LearningLog.outcome == "win")
        )
        losses = await session.execute(
            select(func.count(LearningLog.id)).where(LearningLog.outcome == "loss")
        )
        avg_profit = await session.execute(
            select(func.avg(LearningLog.profit_pct))
        )
        return {
            "total_trades_analyzed": total.scalar() or 0,
            "wins": wins.scalar() or 0,
            "losses": losses.scalar() or 0,
            "avg_profit_pct": round(avg_profit.scalar() or 0, 2),
        }


# ── Market Context ───────────────────────────────────────────


async def save_market_context(
    context_type: str, summary: str, source: str | None = None,
    relevance_score: float | None = None,
) -> MarketContext:
    async with async_session_factory() as session:
        ctx = MarketContext(
            context_type=context_type,
            summary=summary,
            source=source,
            relevance_score=relevance_score,
        )
        session.add(ctx)
        await session.commit()
        await session.refresh(ctx)
        return ctx


async def get_latest_context(
    context_type: str | None = None, limit: int = 5
) -> Sequence[MarketContext]:
    async with async_session_factory() as session:
        stmt = select(MarketContext).order_by(MarketContext.created_at.desc())
        if context_type:
            stmt = stmt.where(MarketContext.context_type == context_type)
        stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()


# ── OpenAI Usage Tracking ────────────────────────────────────


async def save_openai_usage(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    estimated_cost_usd: float | None = None,
    context: str | None = None,
) -> OpenAIUsage:
    """Registra el uso de tokens de OpenAI."""
    async with async_session_factory() as session:
        usage = OpenAIUsage(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost_usd,
            context=context,
        )
        session.add(usage)
        await session.commit()
        await session.refresh(usage)
        return usage


async def get_openai_usage_summary(days: int = 30) -> dict:
    """Resumen de uso de OpenAI en los últimos N días."""
    async with async_session_factory() as session:
        since = datetime.now(UTC) - timedelta(days=days)
        total_tokens = await session.execute(
            select(func.sum(OpenAIUsage.total_tokens)).where(
                OpenAIUsage.created_at >= since
            )
        )
        total_cost = await session.execute(
            select(func.sum(OpenAIUsage.estimated_cost_usd)).where(
                OpenAIUsage.created_at >= since
            )
        )
        total_calls = await session.execute(
            select(func.count(OpenAIUsage.id)).where(
                OpenAIUsage.created_at >= since
            )
        )
        return {
            "total_tokens": total_tokens.scalar() or 0,
            "total_cost_usd": round(total_cost.scalar() or 0, 4),
            "total_calls": total_calls.scalar() or 0,
            "period_days": days,
        }


# ── Dividends ────────────────────────────────────────────────


async def save_dividend_payment(
    portfolio_id: int,
    ticker: str,
    market: str,
    amount_per_share: float,
    shares_held: float,
    currency: str = "USD",
    ex_date: datetime | None = None,
    pay_date: datetime | None = None,
) -> DividendPayment:
    """Registra un pago de dividendos."""
    total = round(amount_per_share * shares_held, 4)
    dp = DividendPayment(
        portfolio_id=portfolio_id,
        ticker=ticker.upper(),
        market=market,
        amount_per_share=amount_per_share,
        shares_held=shares_held,
        total_amount=total,
        currency=currency,
        ex_date=ex_date,
        pay_date=pay_date,
    )
    async with async_session_factory() as session:
        session.add(dp)
        await session.commit()
        await session.refresh(dp)
        return dp


async def get_dividends_for_portfolio(
    portfolio_id: int,
    since_days: int | None = None,
) -> Sequence[DividendPayment]:
    """Obtiene los dividendos de un portfolio, opcionalmente filtrados por fecha."""
    async with async_session_factory() as session:
        q = select(DividendPayment).where(
            DividendPayment.portfolio_id == portfolio_id
        )
        if since_days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=since_days)
            q = q.where(DividendPayment.created_at >= cutoff)
        q = q.order_by(DividendPayment.created_at.desc())
        result = await session.execute(q)
        return result.scalars().all()


async def get_total_dividends(
    portfolio_id: int,
    ticker: str | None = None,
) -> float:
    """Suma total de dividendos cobrados (opcionalmente por ticker)."""
    async with async_session_factory() as session:
        q = select(func.sum(DividendPayment.total_amount)).where(
            DividendPayment.portfolio_id == portfolio_id
        )
        if ticker:
            q = q.where(DividendPayment.ticker == ticker.upper())
        result = await session.execute(q)
        return round(result.scalar() or 0.0, 2)
