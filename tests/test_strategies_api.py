from fastapi.testclient import TestClient

from tradai.web import app
from tradai import strategies


def test_strategies_endpoints(monkeypatch, tmp_path):
    file = tmp_path / "strats.json"
    monkeypatch.setattr(strategies, "STRATEGIES_FILE", file)
    client = TestClient(app)

    resp = client.post(
        "/strategies",
        json={"name": "s1", "symbol": "BTC", "ema_short": 3, "ema_long": 5},
    )
    assert resp.status_code == 200
    assert file.exists()

    resp = client.get("/strategies")
    assert resp.status_code == 200
    data = resp.json()
    assert data["strategies"][0]["name"] == "s1"
    assert data["strategies"][0]["symbol"] == "BTC"
