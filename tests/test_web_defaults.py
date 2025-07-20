from fastapi.testclient import TestClient
from tradai.web import app, DEFAULT_SYMBOLS, TradingViewClient
from tradai.tradingview import columns_for_timeframe


def test_monitor_defaults(monkeypatch):
    client = TestClient(app)
    captured = {}
    def fake_fetch_markets(self, symbols, columns=None):
        captured['columns'] = columns
        return {f"BINANCE:{s}USDT": [1, 2, 3, 4, 5, 6, 7] for s in symbols}
    monkeypatch.setattr(TradingViewClient, "fetch_markets", fake_fetch_markets)

    resp = client.get("/monitor?timeframe=15m&symbols=BTC")
    assert resp.status_code == 200
    data = resp.json()
    assert data["timeframe"] == "15m"
    assert captured['columns'] == columns_for_timeframe("15m")
    assert sorted(data["data"].keys()) == ["BINANCE:BTCUSDT"]
