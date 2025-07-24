from fastapi.testclient import TestClient
import tradai.web as web


def test_bot_start_stop(monkeypatch):
    calls = {'run': 0}

    def dummy_start(symbols=None):
        calls['run'] += 1
        return 'started'

    def dummy_stop():
        calls['run'] -= 1
        return 'stopped'

    monkeypatch.setattr(web, 'svc_start_engine', lambda symbols=None: dummy_start(symbols))
    monkeypatch.setattr(web, 'svc_stop_engine', lambda: dummy_stop())

    client = TestClient(web.app)
    resp = client.post('/bot/start')
    assert resp.status_code == 200
    assert calls['run'] == 1

    resp = client.post('/bot/stop')
    assert resp.status_code == 200
