"""
Rutas del dashboard web.
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from config.markets import market_display, MARKET_CURRENCY, get_currency_symbol
from database import repository as repo
from database.connection import async_session_factory
from database.models import (
    AssetType,
    PortfolioType,
    Signal,
)
from sqlalchemy import select, func

from web.auth import auth_manager, SESSION_COOKIE, SESSION_TTL_HOURS

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Autenticación ────────────────────────────────────────────


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Página de login — formulario para código de acceso."""
    from web.app import templates

    # Si ya tiene sesión válida, redirigir al dashboard
    session_token = request.cookies.get(SESSION_COOKIE)
    if auth_manager.validate_session(session_token):
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login_submit(request: Request, code: str = Form(...)):
    """Valida el código de acceso y crea sesión."""
    from web.app import templates

    client_ip = request.client.host if request.client else "unknown"

    # Comprobar rate-limiting
    if auth_manager.is_ip_blocked(client_ip):
        mins = auth_manager.get_remaining_lockout(client_ip)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": f"Demasiados intentos. Bloqueado {mins} minutos."},
            status_code=429,
        )

    code = code.strip()

    if not auth_manager.validate_code(code):
        auth_manager.record_login_attempt(client_ip)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Código inválido o expirado. Genera uno nuevo con /web en Telegram."},
            status_code=401,
        )

    # Código válido → crear sesión, limpiar intentos
    auth_manager.clear_login_attempts(client_ip)
    session = auth_manager.create_session()
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session.token,
        max_age=SESSION_TTL_HOURS * 3600,
        httponly=True,
        samesite="lax",
        secure=False,
    )
    return response


@router.get("/logout")
async def logout(request: Request):
    """Cierra la sesión activa."""
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        auth_manager.revoke_session(session_token)

    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


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
    etf_value = 0.0
    stock_value = 0.0
    for p in positions:
        pnl = _pnl(p)
        value = round((p.current_price or p.avg_price or 0) * (p.shares or 0), 2)
        is_etf = getattr(p, "asset_type", None) == AssetType.ETF
        if not is_etf:
            try:
                from strategy.etf_config import get_etf_category_for_ticker
                is_etf = get_etf_category_for_ticker(p.ticker) is not None
            except Exception:
                pass
        if is_etf:
            etf_value += value
        else:
            stock_value += value
        pos_ccy = MARKET_CURRENCY.get(p.market or "", "USD")
        pos_ccy_sym = get_currency_symbol(pos_ccy)
        pos_data.append({
            "ticker": p.ticker,
            "market": market_display(p.market or "\u2014"),
            "sector": p.sector or "N/A",
            "shares": p.shares,
            "avg_price": p.avg_price,
            "current_price": p.current_price,
            "value": value,
            "pnl_abs": pnl["abs"],
            "pnl_pct": pnl["pct"],
            "asset_type": "etf" if is_etf else "stock",
            "currency": pos_ccy,
            "currency_symbol": pos_ccy_sym,
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
        "etf_value": round(etf_value, 2),
        "stock_value": round(stock_value, 2),
        "etf_pct": round(etf_value / total_equity * 100, 1) if total_equity > 0 else 0,
        "stock_pct": round(stock_value / total_equity * 100, 1) if total_equity > 0 else 0,
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
    """Estadísticas de señales de los últimos 30 días (query optimizada)."""
    try:
        async with async_session_factory() as session:
            since = datetime.now(UTC) - timedelta(days=30)
            stmt = (
                select(Signal.signal_type, func.count(Signal.id))
                .where(Signal.created_at >= since)
                .group_by(Signal.signal_type)
            )
            rows = (await session.execute(stmt)).all()
            stats = {"buy": 0, "sell": 0, "hold": 0}
            for signal_type, count in rows:
                key = signal_type.value.lower() if signal_type else "hold"
                if key in stats:
                    stats[key] = count
            return stats
    except Exception as e:
        logger.warning(f"Error obteniendo estadísticas de señales: {e}")
        return {"buy": 0, "sell": 0, "hold": 0}


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

    # Estado del broker T212
    broker_status = {"connected": False}
    try:
        from broker.bridge import get_broker_account_cash
        broker_acc = await get_broker_account_cash()
        if broker_acc:
            broker_status = {
                "connected": True,
                "cash": broker_acc.get("cash", 0),
                "invested": broker_acc.get("invested", 0),
                "portfolio_value": broker_acc.get("portfolio_value", 0),
                "pnl": broker_acc.get("pnl", 0),
                "currency": broker_acc.get("currency", "EUR"),
            }
    except Exception:
        pass

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "portfolio": summary,
            "signals": signals,
            "signal_stats": sig_stats,
            "openai_usage": openai_usage,
            "broker": broker_status,
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


@router.get("/api/etf")
async def api_etf_allocation():
    """API JSON: estado de asignación de ETFs en el portfolio."""
    portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
    if not portfolio:
        return {"error": "No portfolio found"}
    try:
        from strategy.etf_selector import get_etf_portfolio_status
        return await get_etf_portfolio_status(portfolio.id)
    except Exception as e:
        logger.error(f"Error obteniendo estado ETF: {e}")
        return {"error": str(e)}


@router.get("/api/broker")
async def api_broker():
    """API JSON: estado completo del broker Trading212."""
    try:
        from broker.bridge import get_broker_status, get_broker_account_cash
        status = await get_broker_status()
        return status
    except Exception as e:
        return {"connected": False, "error": str(e)}


@router.get("/api/broker/dividends")
async def api_broker_dividends(limit: int = 30):
    """API JSON: historial de dividendos del broker."""
    try:
        from broker.bridge import get_broker_dividend_history
        divs = await get_broker_dividend_history(limit=limit)
        total = sum(d.get("amount", 0) for d in divs)
        return {"dividends": divs, "total": round(total, 2), "count": len(divs)}
    except Exception as e:
        return {"error": str(e), "dividends": [], "total": 0}


@router.get("/api/broker/instruments")
async def api_broker_instruments(query: str = "", asset_type: str = ""):
    """API JSON: buscar instrumentos disponibles en T212."""
    try:
        from broker.trading212 import get_trading212_client
        client = get_trading212_client()
        if client is None:
            return {"error": "Broker no configurado", "instruments": []}

        if query:
            result = await client.search_instrument(query)
            instruments = result.data if result.success else []
        else:
            instruments = await client.get_all_instruments()

        # Filtrar por tipo si se especifica
        if asset_type:
            instruments = [
                i for i in instruments
                if i.get("type", "").upper() == asset_type.upper()
            ]

        return {
            "instruments": instruments[:50],
            "total": len(instruments),
        }
    except Exception as e:
        return {"error": str(e), "instruments": []}
