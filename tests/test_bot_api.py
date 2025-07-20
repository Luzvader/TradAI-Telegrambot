from fastapi.testclient import TestClient
import tradai.web as web


def test_bot_start_stop(monkeypatch):
    calls = {'run': 0}

    class DummyEngine:
        def run_forever(self, stop_event=None):
            calls['run'] += 1
            if stop_event:
                stop_event.set()

    monkeypatch.setattr(web, 'BotEngine', lambda symbols: DummyEngine())

    client = TestClient(web.app)
    resp = client.post('/bot/start')
    assert resp.status_code == 200
    assert calls['run'] == 1

    resp = client.post('/bot/stop')
    assert resp.status_code == 200
