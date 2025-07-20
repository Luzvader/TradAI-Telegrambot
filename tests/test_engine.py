from tradai.engine import execute
from tradai.strategies import Strategy
from tradai.wallet import DemoWallet


class DummyWallet(DemoWallet):
    def __init__(self):
        super().__init__()
        self.calls = []

    def place_order(self, symbol: str, side: str, quantity: float):
        self.calls.append((symbol, side, quantity))
        return {"status": "filled"}


def test_execute_triggers_order():
    strat = Strategy(name="s", symbol="BTC", ema_short=3, ema_long=5)
    prices = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    wallet = DummyWallet()
    action = execute(strat, prices, wallet)
    assert action == "BUY"
    assert wallet.calls == [("BTC", "BUY", 1.0)]


def test_execute_no_order_on_hold():
    strat = Strategy(name="s", symbol="BTC", ema_short=50, ema_long=100)
    prices = [1.0, 2.0, 3.0]  # insufficient data -> HOLD
    wallet = DummyWallet()
    action = execute(strat, prices, wallet)
    assert action == "HOLD"
    assert wallet.calls == []
