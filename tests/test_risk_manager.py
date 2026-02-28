"""
Tests para strategy/risk_manager.py — funciones puras de cálculo.
"""

from strategy.risk_manager import (
    calculate_atr_stop_loss,
    calculate_atr_take_profit,
    calculate_trailing_stop,
    calculate_portfolio_value,
)


# ── ATR Stop Loss ────────────────────────────────────────────


def test_atr_stop_loss_with_atr():
    sl = calculate_atr_stop_loss(price=100.0, atr=2.0, multiplier=2.0)
    # 100 - 4 = 96
    assert sl == 96.0


def test_atr_stop_loss_capped_at_85pct():
    """SL no puede caer por debajo del 85% del precio."""
    sl = calculate_atr_stop_loss(price=100.0, atr=20.0, multiplier=2.0)
    # 100 - 40 = 60, pero cap = 85
    assert sl == 85.0


def test_atr_stop_loss_without_atr():
    """Sin ATR, usa porcentaje fijo (8% por defecto)."""
    sl = calculate_atr_stop_loss(price=100.0, atr=None)
    assert sl == 92.0  # 100 * 0.92


def test_atr_stop_loss_zero_atr():
    sl = calculate_atr_stop_loss(price=100.0, atr=0.0)
    assert sl == 92.0  # fallback a % fijo


# ── ATR Take Profit ──────────────────────────────────────────


def test_atr_take_profit_with_atr():
    tp = calculate_atr_take_profit(price=100.0, atr=2.0, multiplier=3.0)
    # 100 + 6 = 106
    assert tp == 106.0


def test_atr_take_profit_without_atr():
    tp = calculate_atr_take_profit(price=100.0, atr=None)
    assert tp == 125.0  # 100 * 1.25


# ── Trailing Stop ────────────────────────────────────────────


def test_trailing_stop_with_atr():
    ts = calculate_trailing_stop(
        current_price=110.0, highest_price=120.0, atr=3.0
    )
    # reference = max(110, 120) = 120; trail = 3*2 = 6; stop = 114
    assert ts == 114.0


def test_trailing_stop_without_atr():
    ts = calculate_trailing_stop(
        current_price=110.0, highest_price=120.0, atr=None, trailing_pct=0.10
    )
    # reference = 120; trail = 120 * 0.10 = 12; stop = 108
    assert ts == 108.0


def test_trailing_stop_current_higher_than_highest():
    ts = calculate_trailing_stop(
        current_price=130.0, highest_price=120.0, atr=None, trailing_pct=0.08
    )
    # reference = 130; trail = 130 * 0.08 = 10.4; stop = 119.6
    assert ts == 119.6
