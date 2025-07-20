import json
from tradai import bot_engine

class DummyStrategy:
    def evaluate(self, data):
        return [{"symbol": "BTC", "side": "BUY", "quantity": 1}]

class DummyClient:
    def fetch_markets(self, symbols, columns=None):
        return {"BINANCE:BTCUSDT": [1,2,3]}

class DummyWallet:
    def place_order(self, symbol, side, quantity):
        return {"status": "filled"}


def test_bot_engine_run_once(monkeypatch, tmp_path):
    orders_file = tmp_path / "orders.json"
    monkeypatch.setattr(bot_engine, "ORDERS_FILE", orders_file)
    monkeypatch.setattr(bot_engine, "TradingViewClient", lambda: DummyClient())
    monkeypatch.setattr(bot_engine, "load_wallet", lambda: DummyWallet())
    monkeypatch.setattr(bot_engine, "load_strategies", lambda pkg: [DummyStrategy()])

    engine = bot_engine.BotEngine(["BTC"], interval_minutes=1)
    engine.run_once()

    data = json.loads(orders_file.read_text())
    assert data[0]["symbol"] == "BTC"
    assert data[0]["side"] == "BUY"

