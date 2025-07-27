import pytest

from tradai.portfolio_decisions import Position, Portfolio, decide_actions


def test_total_value_and_weights():
    p = Portfolio(
        cash=100.0,
        positions={
            "BTC": Position("BTC", 0.01, 10000.0),
            "ETH": Position("ETH", 2.0, 100.0),
        },
    )
    assert round(p.total_value(), 2) == 400.0
    w = p.weights()
    assert pytest.approx(w["BTC"], rel=1e-2) == 0.25
    assert pytest.approx(w["ETH"], rel=1e-2) == 0.5


def test_decide_actions():
    p = Portfolio(
        cash=100.0,
        positions={
            "BTC": Position("BTC", 0.01, 10000.0),
            "ETH": Position("ETH", 2.0, 100.0),
        },
    )
    target = {"BTC": 0.5, "ETH": 0.5}
    prices = {"BTC": 10000.0, "ETH": 100.0}
    actions = decide_actions(p, target, prices, threshold=0.1)
    assert actions["BTC"][0] == "BUY"
    assert actions["ETH"][0] == "HOLD"
