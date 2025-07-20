import pytest

from tradai.indicators import ema, rsi


def test_ema_known_sequence():
    values = [1, 2, 3, 4, 5]
    result = ema(values, period=3)
    assert pytest.approx(result, rel=1e-6) == 4.0


def test_ema_insufficient_data():
    values = [1, 2]
    assert ema(values, period=3) is None


def test_rsi_known_sequence():
    values = [1, 2, 1, 2]
    result = rsi(values, period=3)
    assert pytest.approx(result, rel=1e-6) == 66.66666666666666


def test_rsi_insufficient_data():
    values = [1, 2, 3]
    assert rsi(values, period=3) is None
