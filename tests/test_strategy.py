from tradai import strategy
from tradai.strategy import Estrategia, save_strategy, load_strategy


def test_evaluate_rules():
    s = Estrategia(name="demo", buy_above=10, sell_below=5)
    assert s.evaluate({"price": 12}) == "BUY"
    assert s.evaluate({"price": 3}) == "SELL"
    assert s.evaluate({"price": 7}) == "HOLD"


def test_strategy_persistence(tmp_path, monkeypatch):
    file = tmp_path / "strategies.json"
    monkeypatch.setattr(strategy, "STRATEGY_FILE", file)

    s = Estrategia(name="demo", buy_above=10, sell_below=5)
    save_strategy(s)
    assert file.exists()

    loaded = load_strategy("demo")
    assert isinstance(loaded, Estrategia)
    assert loaded == s
