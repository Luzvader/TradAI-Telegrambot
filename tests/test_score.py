"""
Tests para strategy/score.py — StrategyScore y señales.
"""

from strategy.score import StrategyScore


def _make_score(overall: float, **kwargs) -> StrategyScore:
    defaults = dict(
        ticker="TEST",
        strategy="value",
        value_score=50.0,
        quality_score=50.0,
        safety_score=50.0,
        overall_score=overall,
        margin_of_safety=None,
        reasoning=[],
    )
    defaults.update(kwargs)
    return StrategyScore(**defaults)


def test_signal_buy():
    s = _make_score(80.0)
    assert s.signal == "BUY"


def test_signal_sell():
    s = _make_score(20.0)
    assert s.signal == "SELL"


def test_signal_hold():
    s = _make_score(50.0)
    assert s.signal == "HOLD"


def test_signal_boundary_buy():
    """Score exactamente en el umbral de compra (default 70)."""
    s = _make_score(70.0)
    assert s.signal == "BUY"


def test_signal_boundary_sell():
    """Score exactamente en el umbral de venta (default 30)."""
    s = _make_score(30.0)
    assert s.signal == "SELL"


def test_signal_just_above_sell():
    s = _make_score(31.0)
    assert s.signal == "HOLD"


def test_signal_just_below_buy():
    s = _make_score(69.0)
    assert s.signal == "HOLD"


def test_market_field():
    s = _make_score(50.0, market="IBEX")
    assert s.market == "IBEX"


def test_market_default_none():
    s = _make_score(50.0)
    assert s.market is None
