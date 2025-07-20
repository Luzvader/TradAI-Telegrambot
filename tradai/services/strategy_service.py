"""Service layer for strategy management and bot execution."""
from __future__ import annotations

import json
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Sequence

from ..bot_engine import BotEngine, ORDERS_FILE
from ..strategies import Strategy, load_strategies, save_strategy as save_ema_strategy
from ..strategy import (
    save_strategy as save_rule_strategy,
    list_strategies as list_rule_strategies,
    load_strategy as load_rule_strategy,
    delete_strategy as delete_rule_strategy,
)

DEFAULT_SYMBOLS: Sequence[str] = ("BTC", "ETH", "XRP", "SOL", "BNB")

# Engine runtime state
_engine_thread: threading.Thread | None = None
_engine_stop = threading.Event()

# ---------------------------------------------------------------------------
# Engine helpers
# ---------------------------------------------------------------------------

def start_engine(symbols: Sequence[str] | None = None) -> str:
    """Start the BotEngine in a background thread.

    Returns status string ("started" or "running").
    """
    global _engine_thread, _engine_stop
    if _engine_thread and _engine_thread.is_alive():
        return "running"
    if symbols is None:
        symbols = DEFAULT_SYMBOLS
    engine = BotEngine(list(symbols))
    _engine_stop.clear()
    _engine_thread = threading.Thread(
        target=engine.run_forever, kwargs={"stop_event": _engine_stop}, daemon=True
    )
    _engine_thread.start()
    return "started"

def stop_engine() -> str:
    global _engine_thread, _engine_stop
    if _engine_thread and _engine_thread.is_alive():
        _engine_stop.set()
        _engine_thread.join(timeout=0.1)
        _engine_thread = None
        return "stopped"
    return "not_running"

# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------

def list_strategies() -> List[dict]:
    loaded = load_strategies()
    if loaded:
        return [asdict(s) for s in loaded.values()]
    return list_rule_strategies()

def get_strategy(strategy_id: str):
    return load_rule_strategy(strategy_id)

def delete_strategy(strategy_id: str) -> bool:
    return delete_rule_strategy(strategy_id)

def save_strategy(payload: dict):
    """Save a strategy from payload, returns id or status."""
    if payload.get("symbol"):
        # EMA strategy
        name = payload.get("name")
        symbol = payload.get("symbol")
        strat = Strategy(
            name=name,
            symbol=symbol,
            ema_short=int(payload.get("ema_short", 20)),
            ema_long=int(payload.get("ema_long", 50)),
        )
        save_ema_strategy(strat)
        return {"status": "ok"}
    # rule-based
    sid = save_rule_strategy(payload)
    return {"id": sid}

# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

def list_orders() -> List[Dict]:
    if not ORDERS_FILE.exists():
        return []
    try:
        return json.loads(Path(ORDERS_FILE).read_text())
    except Exception:  # pragma: no cover - corrupted file
        return []
