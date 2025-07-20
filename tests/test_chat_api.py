from fastapi.testclient import TestClient
from tradai.web import app

def test_chat_echo():
    client = TestClient(app)
    resp = client.post('/chat', json={'message': 'hola'})
    assert resp.status_code == 200
    assert resp.json() == {'reply': 'hola'}
