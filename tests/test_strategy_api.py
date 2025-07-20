from fastapi.testclient import TestClient
from tradai.web import app
from tradai import strategy


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
