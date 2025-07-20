"""Utility functions to compute portfolio profit/loss."""
from __future__ import annotations

import json
from pathlib import Path

from .. import bot_engine


def calculate_pnl() -> float:
    """Return cumulative PnL computed from the orders log.

    This very simple implementation assumes quantity units equal
    trade value (Demo wallet behaviour). Each ``BUY`` decreases PnL
    and each ``SELL`` increases it by ``quantity``.
    """
    orders_file: Path = bot_engine.ORDERS_FILE
    if not orders_file.exists():
        return 0.0
    try:
        orders = json.loads(orders_file.read_text())
    except Exception:
        return 0.0

    pnl = 0.0
    for order in orders:
        qty = float(order.get("quantity", 0))
        side = order.get("side")
        if side == "BUY":
            pnl -= qty
        elif side == "SELL":
            pnl += qty
    return pnl
