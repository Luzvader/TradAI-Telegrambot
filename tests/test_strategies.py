import json
from pathlib import Path

from tradai import strategies


def test_save_and_load_strategy(monkeypatch, tmp_path):
    file = tmp_path / "strategies.json"
    monkeypatch.setattr(strategies, "STRATEGIES_FILE", file)
    strat = strategies.Strategy(name="s1", symbol="BTC", ema_short=3, ema_long=5)
    strategies.save_strategy(strat)
    assert file.exists()
    loaded = strategies.load_strategies()
    assert list(loaded.keys()) == ["s1"]
    loaded_strat = loaded["s1"]
    assert loaded_strat.name == "s1"
    assert loaded_strat.symbol == "BTC"
    assert loaded_strat.ema_short == 3
    assert loaded_strat.ema_long == 5


def test_strategy_evaluation():
    strat = strategies.Strategy(name="s", symbol="BTC", ema_short=3, ema_long=5)
    uptrend = [float(i) for i in range(1, 11)]
    downtrend = [float(i) for i in range(10, 0, -1)]
    assert strat.evaluate(uptrend) == "BUY"
    assert strat.evaluate(downtrend) == "SELL"
