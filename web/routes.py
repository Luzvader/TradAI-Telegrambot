"""
Dashboard web routes.

FastAPI serves authentication pages and JSON APIs.
The dashboard UI is an Angular SPA served from frontend/dist when available.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from ai.agents import get_registered_agents, reload_agent_registry, run_agent
from config.markets import market_display
from config.settings import SIGNAL_BUY_THRESHOLD, SIGNAL_SELL_THRESHOLD
from database import repository as repo
from database.models import PortfolioType, StrategyType
from web.auth import SESSION_COOKIE, SESSION_TTL_HOURS, auth_manager

logger = logging.getLogger(__name__)

router = APIRouter()

_PORTFOLIO_TYPES = {p.value: p for p in PortfolioType}
_STRATEGIES = {s.value: s for s in StrategyType}
_REPO_ROOT = Path(__file__).resolve().parents[1]
_FRONTEND_DIST = _REPO_ROOT / "frontend" / "dist" / "tradai-dashboard" / "browser"
_FRONTEND_INDEX = _FRONTEND_DIST / "index.html"


class StrategySwitchRequest(BaseModel):
    portfolio_type: str = Field(default=PortfolioType.REAL.value)
    strategy: str = Field(...)


class BacktestRunRequest(BaseModel):
    tickers: list[str] = Field(default_factory=list)
    period: str = Field(default="1y")
    strategy: str | None = None
    initial_capital: float = Field(default=10_000.0, ge=100)
    rebalance_days: int = Field(default=5, ge=1, le=30)
    max_positions: int = Field(default=10, ge=1, le=50)
    position_size_pct: float = Field(default=0.10, gt=0, le=1)
    buy_threshold: float = Field(default=SIGNAL_BUY_THRESHOLD, ge=0, le=100)
    sell_threshold: float = Field(default=SIGNAL_SELL_THRESHOLD, ge=0, le=100)
    use_technicals: bool = True
    use_learning: bool = True
    auto_learn: bool = False


class AgentRunRequest(BaseModel):
    agent_id: str = Field(...)
    ticker: str = Field(...)
    market: str | None = None
    strategy: str | None = None
    context: str = ""


def _parse_portfolio_type(value: str) -> PortfolioType:
    key = (value or "").strip().lower()
    ptype = _PORTFOLIO_TYPES.get(key)
    if ptype is None:
        valid = ", ".join(sorted(_PORTFOLIO_TYPES))
        raise HTTPException(status_code=400, detail=f"portfolio_type invalid. Use: {valid}")
    return ptype


def _parse_strategy(value: str | None) -> StrategyType | None:
    if value is None:
        return None
    key = value.strip().lower()
    strategy = _STRATEGIES.get(key)
    if strategy is None:
        valid = ", ".join(sorted(_STRATEGIES))
        raise HTTPException(status_code=400, detail=f"strategy invalid. Use: {valid}")
    return strategy


def _pnl(pos) -> dict[str, float]:
    if pos.current_price and pos.avg_price and pos.shares:
        pnl_abs = (pos.current_price - pos.avg_price) * pos.shares
        pnl_pct = ((pos.current_price / pos.avg_price) - 1) * 100
        return {"abs": round(pnl_abs, 2), "pct": round(pnl_pct, 2)}
    return {"abs": 0.0, "pct": 0.0}


async def _portfolio_summary(portfolio_id: int) -> dict:
    portfolio = await repo.get_portfolio(portfolio_id)
    if not portfolio:
        return {}

    positions = list(await repo.get_open_positions(portfolio_id))
    total_invested = sum((p.avg_price or 0) * (p.shares or 0) for p in positions)
    total_value = sum((p.current_price or p.avg_price or 0) * (p.shares or 0) for p in positions)
    total_pnl = total_value - total_invested

    pos_data = []
    for p in positions:
        pnl = _pnl(p)
        pos_data.append(
            {
                "ticker": p.ticker,
                "market": market_display(p.market or "-"),
                "sector": p.sector or "N/A",
                "shares": p.shares,
                "avg_price": p.avg_price,
                "current_price": p.current_price,
                "value": round((p.current_price or p.avg_price or 0) * (p.shares or 0), 2),
                "pnl_abs": pnl["abs"],
                "pnl_pct": pnl["pct"],
            }
        )
    pos_data.sort(key=lambda x: x["pnl_pct"], reverse=True)

    cash = portfolio.cash or 0
    initial_capital = portfolio.initial_capital or 0
    total_equity = total_value + cash if initial_capital > 0 else total_value

    return {
        "name": portfolio.name,
        "strategy": portfolio.strategy.value if portfolio.strategy else "-",
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
    signals = await repo.get_recent_signals(limit=limit)
    return [
        {
            "id": s.id,
            "ticker": s.ticker,
            "market": s.market,
            "type": s.signal_type.value if s.signal_type else "-",
            "price": s.price,
            "score": s.value_score,
            "created_at": s.created_at.strftime("%d/%m %H:%M") if s.created_at else "-",
            "reasoning": (s.reasoning or "")[:120] + "..."
            if s.reasoning and len(s.reasoning) > 120
            else (s.reasoning or "-"),
        }
        for s in signals
    ]


def _frontend_missing_response() -> HTMLResponse:
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>TradAI Frontend Pending Build</title>
  <style>
    body{font-family: ui-sans-serif,system-ui; background:#0c111b; color:#e8eef8; margin:0; display:grid; place-items:center; min-height:100vh;}
    main{max-width:880px; width:min(94vw,880px); background:#111a2a; border:1px solid #21324f; border-radius:16px; padding:28px;}
    h1{margin:0 0 8px; font-size:1.7rem;}
    p{color:#b5c7e4;}
    pre{background:#08101f; border:1px solid #21324f; border-radius:10px; padding:12px; overflow:auto;}
    code{color:#b9ffcf;}
  </style>
</head>
<body>
  <main>
    <h1>Angular dashboard not built yet</h1>
    <p>The legacy server-rendered UI has been replaced. Build the Angular SPA and refresh this page.</p>
    <pre><code>cd frontend
npm install
npm run build</code></pre>
    <p>Expected output path: <code>frontend/dist/tradai-dashboard/browser/index.html</code></p>
  </main>
</body>
</html>
"""
    return HTMLResponse(content=html, status_code=503)


def _serve_spa_index() -> FileResponse | HTMLResponse:
    if _FRONTEND_INDEX.exists():
        return FileResponse(_FRONTEND_INDEX)
    return _frontend_missing_response()


# Authentication routes


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    from web.app import templates

    session_token = request.cookies.get(SESSION_COOKIE)
    if auth_manager.validate_session(session_token):
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login_submit(request: Request, code: str = Form(...)):
    from web.app import templates

    client_ip = request.client.host if request.client else "unknown"

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
            {"request": request, "error": "Codigo invalido o expirado. Genera uno nuevo con /web en Telegram."},
            status_code=401,
        )

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
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        auth_manager.revoke_session(session_token)

    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


# SPA entry


@router.get("/", response_class=HTMLResponse)
async def spa_root():
    return _serve_spa_index()


# API


@router.get("/api/portfolio")
async def api_portfolio():
    portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
    if not portfolio:
        return {"error": "No portfolio found"}
    return await _portfolio_summary(portfolio.id)


@router.get("/api/portfolios")
async def api_portfolios():
    real = await repo.get_portfolio_by_type(PortfolioType.REAL)
    backtest = await repo.get_portfolio_by_type(PortfolioType.BACKTEST)
    return {
        "real": await _portfolio_summary(real.id) if real else None,
        "backtest": await _portfolio_summary(backtest.id) if backtest else None,
    }


@router.get("/api/signals")
async def api_signals(limit: int = 20):
    return await _recent_signals(limit=limit)


@router.get("/api/openai-usage")
async def api_openai_usage(days: int = 30):
    return await repo.get_openai_usage_summary(days=days)


@router.get("/api/health")
async def api_health():
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}


@router.post("/api/strategy")
async def api_strategy_switch(payload: StrategySwitchRequest):
    ptype = _parse_portfolio_type(payload.portfolio_type)
    strategy = _parse_strategy(payload.strategy)
    if strategy is None:
        raise HTTPException(status_code=400, detail="strategy is required")

    portfolio = await repo.get_portfolio_by_type(ptype)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio '{ptype.value}' not found")

    updated = await repo.set_portfolio_strategy(portfolio.id, strategy)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update strategy")

    return {
        "success": True,
        "portfolio_type": ptype.value,
        "portfolio_id": portfolio.id,
        "strategy": strategy.value,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.post("/api/backtest/run")
async def api_backtest_run(payload: BacktestRunRequest):
    from backtesting.engine import BacktestConfig, run_backtest

    tickers = [t.strip().upper().replace("$", "") for t in payload.tickers if t and t.strip()]
    tickers = sorted(set(tickers))

    if not tickers:
        bt_portfolio = await repo.get_portfolio_by_type(PortfolioType.BACKTEST)
        if bt_portfolio:
            positions = await repo.get_open_positions(bt_portfolio.id)
            tickers = sorted({p.ticker.upper() for p in positions if p.ticker})

    if not tickers:
        raise HTTPException(
            status_code=400,
            detail="No tickers provided and no open positions in backtest portfolio",
        )
    if len(tickers) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 tickers per backtest")

    strategy = _parse_strategy(payload.strategy)
    if strategy is None:
        bt_portfolio = await repo.get_portfolio_by_type(PortfolioType.BACKTEST)
        strategy = bt_portfolio.strategy if bt_portfolio and bt_portfolio.strategy else StrategyType.VALUE

    if payload.sell_threshold >= payload.buy_threshold:
        raise HTTPException(status_code=400, detail="sell_threshold must be lower than buy_threshold")

    config = BacktestConfig(
        tickers=tickers,
        strategy=strategy,
        period=payload.period,
        initial_capital=payload.initial_capital,
        rebalance_days=payload.rebalance_days,
        max_positions=payload.max_positions,
        position_size_pct=payload.position_size_pct,
        buy_threshold=payload.buy_threshold,
        sell_threshold=payload.sell_threshold,
        use_technicals=payload.use_technicals,
        use_learning=payload.use_learning,
        auto_learn=payload.auto_learn,
    )

    try:
        result = await run_backtest(config)
    except Exception as exc:
        logger.exception("Error running manual backtest")
        raise HTTPException(status_code=500, detail=f"Backtest error: {exc}") from exc

    m = result.metrics
    return {
        "config": {
            "tickers": tickers,
            "strategy": strategy.value,
            "period": payload.period,
            "initial_capital": payload.initial_capital,
            "rebalance_days": payload.rebalance_days,
        },
        "metrics": {
            "initial_capital": m.initial_capital,
            "final_value": m.final_value,
            "total_return_pct": m.total_return_pct,
            "annualized_return_pct": m.annualized_return_pct,
            "max_drawdown_pct": m.max_drawdown_pct,
            "sharpe_ratio": m.sharpe_ratio,
            "volatility_pct": m.volatility_pct,
            "total_trades": m.total_trades,
            "winning_trades": m.winning_trades,
            "losing_trades": m.losing_trades,
            "win_rate_pct": m.win_rate_pct,
            "benchmark_return_pct": m.benchmark_return_pct,
            "alpha_pct": m.alpha_pct,
        },
        "learning_logs_created": result.learning_logs_created,
        "session_analysis": result.session_analysis,
        "trades": result.trades[:50],
        "final_positions": result.final_positions,
        "daily_values_tail": result.daily_values[-120:],
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/api/agents")
async def api_agents():
    return {"agents": get_registered_agents(include_disabled=False)}


@router.post("/api/agents/reload")
async def api_agents_reload():
    reload_agent_registry()
    return {"agents": get_registered_agents(include_disabled=True)}


@router.post("/api/agents/run")
async def api_agents_run(payload: AgentRunRequest):
    strategy = _parse_strategy(payload.strategy)
    try:
        return await run_agent(
            agent_id=payload.agent_id,
            ticker=payload.ticker,
            market=payload.market,
            strategy=strategy,
            context=payload.context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error running AI agent")
        raise HTTPException(status_code=500, detail=f"Agent execution error: {exc}") from exc


@router.get("/api/broker")
async def api_broker():
    try:
        from broker.bridge import get_broker_status

        return await get_broker_status()
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


@router.get("/api/broker/dividends")
async def api_broker_dividends(limit: int = 30):
    try:
        from broker.bridge import get_broker_dividend_history

        divs = await get_broker_dividend_history(limit=limit)
        total = sum(d.get("amount", 0) for d in divs)
        return {"dividends": divs, "total": round(total, 2), "count": len(divs)}
    except Exception as exc:
        return {"error": str(exc), "dividends": [], "total": 0}


@router.get("/api/broker/instruments")
async def api_broker_instruments(query: str = "", asset_type: str = ""):
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

        if asset_type:
            instruments = [
                i for i in instruments if i.get("type", "").upper() == asset_type.upper()
            ]

        return {"instruments": instruments[:50], "total": len(instruments)}
    except Exception as exc:
        return {"error": str(exc), "instruments": []}


# Catch-all for Angular client routing


@router.get("/{full_path:path}", response_class=HTMLResponse)
async def spa_catch_all(full_path: str):
    normalized = (full_path or "").strip().lower()
    if (
        normalized == "api"
        or normalized.startswith("api/")
        or normalized == "login"
        or normalized.startswith("login/")
        or normalized == "logout"
        or normalized.startswith("logout/")
        or normalized == "static"
        or normalized.startswith("static/")
    ):
        raise HTTPException(status_code=404, detail="Not Found")

    file_candidate = _FRONTEND_DIST / full_path
    if full_path and file_candidate.exists() and file_candidate.is_file():
        return FileResponse(file_candidate)

    return _serve_spa_index()
