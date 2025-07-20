import json
from fastapi.testclient import TestClient

import tradai.llm_agent as llm_agent
from tradai.web import app
from tradai import strategy
from tradai import options


def test_suggest_strategy(monkeypatch, tmp_path):
    opt_file = tmp_path / "options.xml"
    monkeypatch.setattr(options, "OPTIONS_FILE", opt_file)
    options.save_options({"openai_api_key": "k"})

    class DummyChat:
        @staticmethod
        def create(**kwargs):
            return {"choices": [{"message": {"content": '{"name": "s1"}'}}]}

    monkeypatch.setattr(llm_agent, "openai", type("obj", (), {"ChatCompletion": DummyChat, "api_key": None}))

    strat = llm_agent.suggest_strategy("idea")
    assert strat == {"name": "s1"}


def test_suggest_strategy_from_options(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setattr(llm_agent, "load_options", lambda: {"openai_key": "k"})

    class DummyChat:
        @staticmethod
        def create(**kwargs):
            return {"choices": [{"message": {"content": '{"name": "s1"}'}}]}

    monkeypatch.setattr(llm_agent, "openai", type("obj", (), {"ChatCompletion": DummyChat, "api_key": None}))
    strat = llm_agent.suggest_strategy("idea")
    assert strat == {"name": "s1"}


def test_llm_strategy_endpoint(monkeypatch, tmp_path):
    opt_file = tmp_path / "options.xml"
    monkeypatch.setattr(options, "OPTIONS_FILE", opt_file)
    options.save_options({"openai_api_key": "k"})

    class DummyChat:
        @staticmethod
        def create(**kwargs):
            return {"choices": [{"message": {"content": json.dumps({"foo": "bar"})}}]}

    monkeypatch.setattr(llm_agent, "openai", type("obj", (), {"ChatCompletion": DummyChat, "api_key": None}))
    monkeypatch.setattr(strategy, "STRATEGIES_DIR", tmp_path)

    client = TestClient(app)

    resp = client.post("/llm/strategy", json={"prompt": "x"})
    assert resp.status_code == 200
    assert resp.json()["strategy"] == {"foo": "bar"}

    resp = client.post("/llm/strategy", json={"prompt": "x", "save": True})
    assert resp.status_code == 200
    sid = resp.json()["id"]
    assert (tmp_path / f"{sid}.json").exists()
