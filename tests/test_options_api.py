from fastapi.testclient import TestClient
from tradai.web import app
from tradai import options


def test_options_save_and_load(monkeypatch, tmp_path):
    opt_file = tmp_path / "opts.dat"
    monkeypatch.setattr(options, "OPTIONS_FILE", opt_file)
    client = TestClient(app)

    data = {
        "openai_key": "ok",
        "binance_key": "bk",
        "binance_secret": "bs",
    }
    resp = client.post("/options", json=data)
    assert resp.status_code == 200
    assert options.load_options() == data

    resp = client.get("/options")
    assert resp.status_code == 200
    assert resp.json() == data
