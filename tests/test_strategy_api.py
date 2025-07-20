from fastapi.testclient import TestClient
from tradai.web import app
from tradai import strategy, strategies


def test_strategy_crud(monkeypatch, tmp_path):
    monkeypatch.setattr(strategy, "STRATEGIES_DIR", tmp_path)
    client = TestClient(app)

    # create
    resp = client.post("/strategies", json={"name": "demo"})
    assert resp.status_code == 200
    sid = resp.json()["id"]
    assert (tmp_path / f"{sid}.json").exists()

    # list
    resp = client.get("/strategies")
    assert resp.status_code == 200
    assert sid in resp.json()["strategies"]

    # get
    resp = client.get(f"/strategies/{sid}")
    assert resp.status_code == 200
    assert resp.json()["strategy"]["name"] == "demo"

    # delete
    resp = client.delete(f"/strategies/{sid}")
    assert resp.status_code == 200
    assert not (tmp_path / f"{sid}.json").exists()

    # not found
    resp = client.get(f"/strategies/{sid}")
    assert resp.status_code == 404


def test_list_mixed_strategies(monkeypatch, tmp_path):
    ema_file = tmp_path / "emas.json"
    rule_dir = tmp_path / "rules"
    monkeypatch.setattr(strategies, "STRATEGIES_FILE", ema_file)
    monkeypatch.setattr(strategy, "STRATEGIES_DIR", rule_dir)

    client = TestClient(app)

    # create EMA strategy
    resp = client.post("/strategies", json={"name": "ema1", "symbol": "BTC"})
    assert resp.status_code == 200

    # create rule-based strategy
    resp = client.post("/strategies", json={"name": "demo"})
    assert resp.status_code == 200
    sid = resp.json()["id"]

    resp = client.get("/strategies")
    assert resp.status_code == 200
    strategies_list = resp.json()["strategies"]
    assert any(isinstance(item, dict) and item.get("name") == "ema1" for item in strategies_list)
    assert sid in strategies_list
