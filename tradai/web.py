"""FastAPI app para exponer la funcionalidad de TradAI vía HTTP.

Endpoints principales:
- ``GET /markets`` para consultar datos básicos de mercado.
- ``GET /monitor`` para precio e indicadores de uno o varios símbolos.

El frontend (HTML/JS) se sirve como archivos estáticos desde el
directorio ``webapp`` en la raíz del proyecto.
"""

from __future__ import annotations

from typing import List

from fastapi import Body, FastAPI, HTTPException, Query


from .tradingview import TradingViewClient

from .services.market_service import (
    fetch_basic,
    fetch_with_indicators,
    DEFAULT_SYMBOLS,
)
from .strategy import save_strategy as save_rule_strategy
from .llm_agent import suggest_strategy
from .wallet import (
    load_wallet_config,
    save_wallet_config,
    BinanceWallet,
    load_wallet,
)
from .options import load_options, save_options
from .services.strategy_service import (
    start_engine as svc_start_engine,
    stop_engine as svc_stop_engine,
    list_strategies as svc_list_strategies,
    get_strategy as svc_get_strategy,
    delete_strategy as svc_delete_strategy,
    save_strategy as svc_save_strategy,
    list_orders as svc_list_orders,
)
from .services.pnl_service import calculate_pnl as svc_calculate_pnl

app = FastAPI(title="TradAI Web API")

# DEFAULT_SYMBOLS imported from market_service



@app.get("/markets")
def get_markets(
    symbols: str | None = Query(None, description="Símbolos separados por coma"),
    period: str = Query("24h", description="1h,4h,24h,1w,1m,3m,6m,1y,ytd"),
):
    """Devuelve datos de mercado básicos de TradingView."""
    symbols_list: List[str]
    if symbols:
        symbols_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    else:
        symbols_list = DEFAULT_SYMBOLS

    data = fetch_basic(symbols_list, period)
    return {"symbols": symbols_list, "data": data}


@app.get("/monitor")
def monitor(
    symbols: str | None = Query(None, description="Símbolos separados por coma"),
    timeframe: str = Query("5m", description="5m, 15m, 1h, 4h, 1d o 1w"),
):
    """Devuelve precio e indicadores técnicos para los símbolos indicados."""
    allowed_frames = {"5m", "15m", "1h", "4h", "1d", "1w"}
    if timeframe not in allowed_frames:
        raise HTTPException(status_code=400, detail="Timeframe no válido")

    symbols_list: List[str]
    if symbols:
        symbols_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    else:
        symbols_list = DEFAULT_SYMBOLS

    data = fetch_with_indicators(symbols_list, timeframe)
    return {"timeframe": timeframe, "data": data}


@app.post("/wallet")
def set_wallet(payload: dict = Body(...)):
    """Crea o actualiza la cartera actual."""
    w_type = payload.get("type")
    if w_type not in {"demo", "binance"}:
        raise HTTPException(status_code=400, detail="Tipo de wallet no soportado")
    if w_type == "binance":
        try:
            BinanceWallet(
                payload.get("api_key"), payload.get("api_secret")
            ).get_balances()
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"Credenciales inválidas: {exc}"
            )
    try:
        save_wallet_config(payload)
    except Exception as exc:  # pragma: no cover - error inesperado
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "ok"}


@app.get("/wallet")
def get_wallet():
    """Devuelve la configuración y balances de la cartera actual."""
    wallet = load_wallet()
    try:
        balances = wallet.get_balances()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc))
    cfg = load_wallet_config() or {"type": "demo"}
    return {"type": cfg.get("type"), "balances": balances}


@app.post("/options")
def set_options(payload: dict = Body(...)):
    """Guarda opciones generales incluyendo claves API."""
    try:
        save_options(payload)
    except Exception as exc:  # pragma: no cover - disk error
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "ok"}


@app.get("/options")
def get_options():
    """Devuelve las opciones guardadas."""
    return load_options() or {}


@app.post("/strategies")
def create_strategy(payload: dict = Body(...)):
    """Guarda una estrategia (EMA o rule-based) via service layer."""
    try:
        return svc_save_strategy(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/strategies")
def get_strategies():
    """Lista estrategias guardadas."""
    return {"strategies": svc_list_strategies()}


@app.get("/strategies/{strategy_id}")
def get_strategy(strategy_id: str):
    data = svc_get_strategy(strategy_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"id": strategy_id, "strategy": data}


@app.delete("/strategies/{strategy_id}")
def delete_strategy_route(strategy_id: str):
    deleted = svc_delete_strategy(strategy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"status": "deleted"}


@app.post("/llm/strategy")
def llm_strategy_route(payload: dict = Body(...)):
    """Genera una estrategia usando un LLM."""
    prompt = payload.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt requerido")
    try:
        strat = suggest_strategy(prompt)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:  # pragma: no cover - unexpected
        raise HTTPException(status_code=500, detail=str(exc))

    result = {"strategy": strat}
    if payload.get("save"):
        try:
            sid = save_rule_strategy(strat)
        except Exception as exc:  # pragma: no cover - disk error
            raise HTTPException(status_code=500, detail=str(exc))
        result["id"] = sid
    return result


@app.post("/bot/start")
def start_bot():
    """Start the BotEngine in the background."""
    status = svc_start_engine(DEFAULT_SYMBOLS)
    return {"status": status}


@app.post("/bot/stop")
def stop_bot():
    """Stop the running BotEngine if active."""
    status = svc_stop_engine()
    return {"status": status}


@app.get("/orders")
def get_orders():
    return svc_list_orders()


@app.get("/pnl")
def get_pnl():
    """Return simple profit/loss based on logged orders."""
    pnl = svc_calculate_pnl()
    return {"pnl": pnl}


@app.post("/chat")
def chat_route(payload: dict = Body(...)):
    """Very simple echo chat endpoint."""
    msg = payload.get("message")
    if not msg:
        raise HTTPException(status_code=400, detail="message requerido")
    return {"reply": msg}

__all__ = ["app", "DEFAULT_SYMBOLS", "TradingViewClient"]
