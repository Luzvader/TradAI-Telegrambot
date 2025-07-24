import pytest

from tradai.indicators import ema, rsi, macd, atr, detect_candle


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


def test_macd_basic():
    values = [1, 2, 3, 4, 3, 2, 1, 2, 3, 4, 5]
    result = macd(values, short_period=3, long_period=6, signal_period=3)
    assert result is not None
    macd_val, signal_val = result
    assert macd_val > signal_val


def test_macd_insufficient():
    values = [1, 2, 3]
    assert macd(values, short_period=3, long_period=6, signal_period=3) is None


def test_atr_basic():
    highs = [10, 12, 13, 14]
    lows = [8, 9, 10, 11]
    closes = [9, 11, 12, 13]
    result = atr(highs, lows, closes, period=3)
    assert pytest.approx(result, rel=1e-6) == 3.0


def test_atr_insufficient():
    highs = [1, 2]
    lows = [0, 1]
    closes = [0.5, 1.5]
    assert atr(highs, lows, closes, period=3) is None


def test_detect_candle():
    opens = [10, 7]
    highs = [10, 12]
    lows = [6, 6]
    closes = [8, 11]
    assert detect_candle(opens, highs, lows, closes) == "bullish_engulfing"


def test_detect_candle_none():
    opens = [7, 10]
    highs = [12, 11]
    lows = [6, 9]
    closes = [11, 6]
    assert detect_candle(opens, highs, lows, closes) is None
