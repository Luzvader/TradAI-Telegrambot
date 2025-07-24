import json
from fastapi.testclient import TestClient
from tradai.web import app
from tradai import bot_engine


def test_get_pnl(monkeypatch, tmp_path):
    orders_file = tmp_path / "orders.json"
    monkeypatch.setattr(bot_engine, "ORDERS_FILE", orders_file)
    orders = [
        {"symbol": "BTC", "side": "BUY", "quantity": 1},
        {"symbol": "BTC", "side": "SELL", "quantity": 2},
    ]
    orders_file.write_text(json.dumps(orders))

    client = TestClient(app)
    resp = client.get("/pnl")
    assert resp.status_code == 200
    assert resp.json() == {"pnl": 1.0}
