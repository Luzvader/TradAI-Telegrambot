"""
Rutas del dashboard web.
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from config.markets import market_display
from database import repository as repo
from database.connection import async_session_factory
from database.models import (
    PortfolioType,
    Signal,
    SignalType,
)
from sqlalchemy import select, func

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────


def _pnl(pos) -> dict:
    """Calcula P&L de una posición."""
    if pos.current_price and pos.avg_price and pos.shares:
        pnl_abs = (pos.current_price - pos.avg_price) * pos.shares
        pnl_pct = ((pos.current_price / pos.avg_price) - 1) * 100
        return {"abs": round(pnl_abs, 2), "pct": round(pnl_pct, 2)}
    return {"abs": 0.0, "pct": 0.0}


async def _portfolio_summary(portfolio_id: int) -> dict:
    """Genera resumen completo de un portfolio."""
    portfolio = await repo.get_portfolio(portfolio_id)
    if not portfolio:
        return {}

    positions = list(await repo.get_open_positions(portfolio_id))
    total_invested = sum(
        (p.avg_price or 0) * (p.shares or 0) for p in positions
    )
    total_value = sum(
        (p.current_price or p.avg_price or 0) * (p.shares or 0) for p in positions
    )
    total_pnl = total_value - total_invested

    pos_data = []
    for p in positions:
        pnl = _pnl(p)
        pos_data.append({
            "ticker": p.ticker,
            "market": market_display(p.market or "—"),
            "sector": p.sector or "N/A",
            "shares": p.shares,
            "avg_price": p.avg_price,
            "current_price": p.current_price,
            "value": round((p.current_price or p.avg_price or 0) * (p.shares or 0), 2),
            "pnl_abs": pnl["abs"],
            "pnl_pct": pnl["pct"],
        })
    pos_data.sort(key=lambda x: x["pnl_pct"], reverse=True)

    cash = portfolio.cash or 0
    initial_capital = portfolio.initial_capital or 0
    # Patrimonio = valor posiciones + cash (si hay capital) ó solo posiciones
    if initial_capital > 0:
        total_equity = total_value + cash
    else:
        total_equity = total_value

    return {
        "name": portfolio.name,
        "strategy": portfolio.strategy.value if portfolio.strategy else "—",
        "cash": cash,
        "initial_capital": initial_capital,
        "total_invested": round(total_invested, 2),
        "total_value": round(total_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round((total_pnl / total_invested * 100) if total_invested else 0, 2),
        "total_assets": round(total_equity, 2),
        "positions": pos_data,
        "num_positions": len(pos_data),
    }


async def _recent_signals(limit: int = 20) -> list[dict]:
    """Obtiene señales recientes."""
    signals = await repo.get_recent_signals(limit=limit)
    return [
        {
            "id": s.id,
            "ticker": s.ticker,
            "market": s.market,
            "type": s.signal_type.value if s.signal_type else "—",
            "price": s.price,
            "score": s.value_score,
            "created_at": s.created_at.strftime("%d/%m %H:%M") if s.created_at else "—",
            "reasoning": (s.reasoning or "")[:120] + "..." if s.reasoning and len(s.reasoning) > 120 else (s.reasoning or "—"),
        }
        for s in signals
    ]


async def _signal_stats() -> dict:
    """Estadísticas de señales de los últimos 30 días."""
    async with async_session_factory() as session:
        since = datetime.now(UTC) - timedelta(days=30)
        buy_count = (await session.execute(
            select(func.count(Signal.id)).where(
                Signal.signal_type == SignalType.BUY, Signal.created_at >= since
            )
        )).scalar() or 0
        sell_count = (await session.execute(
            select(func.count(Signal.id)).where(
                Signal.signal_type == SignalType.SELL, Signal.created_at >= since
            )
        )).scalar() or 0
        hold_count = (await session.execute(
            select(func.count(Signal.id)).where(
                Signal.signal_type == SignalType.HOLD, Signal.created_at >= since
            )
        )).scalar() or 0
        return {"buy": buy_count, "sell": sell_count, "hold": hold_count}


# ── Páginas ──────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Página principal del dashboard."""
    from web.app import templates

    # Obtener portfolio real
    portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
    summary = {}
    if portfolio:
        summary = await _portfolio_summary(portfolio.id)

    signals = await _recent_signals(limit=15)
    sig_stats = await _signal_stats()
    openai_usage = await repo.get_openai_usage_summary(days=30)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "portfolio": summary,
            "signals": signals,
            "signal_stats": sig_stats,
            "openai_usage": openai_usage,
        },
    )


@router.get("/signals", response_class=HTMLResponse)
async def signals_page(request: Request):
    """Página de señales recientes (htmx partial)."""
    from web.app import templates

    signals = await _recent_signals(limit=50)
    return templates.TemplateResponse(
        "partials/signals_table.html",
        {"request": request, "signals": signals},
    )


@router.get("/positions", response_class=HTMLResponse)
async def positions_page(request: Request):
    """Página de posiciones (htmx partial)."""
    from web.app import templates

    portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
    summary = {}
    if portfolio:
        summary = await _portfolio_summary(portfolio.id)

    return templates.TemplateResponse(
        "partials/positions_table.html",
        {"request": request, "portfolio": summary},
    )


# ── API JSON ─────────────────────────────────────────────────


@router.get("/api/portfolio")
async def api_portfolio():
    """API JSON: resumen del portfolio."""
    portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
    if not portfolio:
        return {"error": "No portfolio found"}
    return await _portfolio_summary(portfolio.id)


@router.get("/api/signals")
async def api_signals(limit: int = 20):
    """API JSON: señales recientes."""
    return await _recent_signals(limit=limit)


@router.get("/api/openai-usage")
async def api_openai_usage(days: int = 30):
    """API JSON: uso de OpenAI."""
    return await repo.get_openai_usage_summary(days=days)


@router.get("/api/health")
async def api_health():
    """Health check."""
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}
