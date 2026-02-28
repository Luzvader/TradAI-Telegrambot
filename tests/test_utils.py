"""
Tests para strategy/utils.py
"""

from strategy.utils import clamp


def test_clamp_within_bounds():
    assert clamp(50.0) == 50.0


def test_clamp_below_min():
    assert clamp(-10.0) == 0.0


def test_clamp_above_max():
    assert clamp(150.0) == 100.0


def test_clamp_exact_min():
    assert clamp(0.0) == 0.0


def test_clamp_exact_max():
    assert clamp(100.0) == 100.0


def test_clamp_custom_range():
    assert clamp(5.0, min_val=10.0, max_val=20.0) == 10.0
    assert clamp(25.0, min_val=10.0, max_val=20.0) == 20.0
    assert clamp(15.0, min_val=10.0, max_val=20.0) == 15.0
