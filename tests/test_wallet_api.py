from fastapi.testclient import TestClient
from tradai.web import app
from tradai import wallet
from tradai import options


def test_wallet_creation_and_persistence(monkeypatch, tmp_path):
    wallet_file = tmp_path / "options.xml"
    monkeypatch.setattr(options, "OPTIONS_FILE", wallet_file)
    client = TestClient(app)
    resp = client.post("/wallet", json={"type": "demo"})
    assert resp.status_code == 200
    assert wallet_file.exists()
    cfg = wallet.load_wallet_config()
    assert cfg == {"type": "demo"}


def test_wallet_get_balances_demo(monkeypatch, tmp_path):
    wallet_file = tmp_path / "options.xml"
    monkeypatch.setattr(options, "OPTIONS_FILE", wallet_file)
    monkeypatch.setattr(wallet.DemoWallet, "get_balances", lambda self: {"USDT": 50})
    wallet.save_wallet_config({"type": "demo"})
    client = TestClient(app)
    resp = client.get("/wallet")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "demo"
    assert data["balances"] == {"USDT": 50}


def test_wallet_get_balances_binance(monkeypatch, tmp_path):
    wallet_file = tmp_path / "options.xml"
    monkeypatch.setattr(options, "OPTIONS_FILE", wallet_file)
    class DummyClient:
        def get_account(self):
            return {"balances": []}
        def create_order(self, **kwargs):
            return {}
    monkeypatch.setattr(wallet, "Client", lambda *a, **k: DummyClient())
    monkeypatch.setattr(wallet.BinanceWallet, "get_balances", lambda self: {"BTC": 1})
    wallet.save_wallet_config({"type": "binance", "api_key": "k", "api_secret": "s"})
    client = TestClient(app)
    resp = client.get("/wallet")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "binance"
    assert data["balances"] == {"BTC": 1}


def test_wallet_invalid_binance_credentials(monkeypatch, tmp_path):
    wallet_file = tmp_path / "options.xml"
    monkeypatch.setattr(options, "OPTIONS_FILE", wallet_file)
    class DummyClient:
        def get_account(self):
            return {"balances": []}
        def create_order(self, **kwargs):
            return {}
    monkeypatch.setattr(wallet, "Client", lambda *a, **k: DummyClient())
    def fake_balances(self):
        raise Exception("invalid key")
    monkeypatch.setattr(wallet.BinanceWallet, "get_balances", fake_balances)
    client = TestClient(app)
    resp = client.post(
        "/wallet",
        json={"type": "binance", "api_key": "k", "api_secret": "s"},
    )
    assert resp.status_code == 400

