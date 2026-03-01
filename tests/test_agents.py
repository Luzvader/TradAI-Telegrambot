"""Tests for AI agent registry and parsing."""

from ai.agents import (
    get_agent,
    get_registered_agents,
    parse_agent_registry,
    reload_agent_registry,
)


def test_parse_agent_registry_empty():
    assert parse_agent_registry("") == []


def test_parse_agent_registry_invalid_json():
    assert parse_agent_registry("{bad-json") == []


def test_parse_agent_registry_remote_requires_url():
    raw = '[{"id":"x1","kind":"remote"}]'
    parsed = parse_agent_registry(raw)
    assert parsed == []


def test_parse_agent_registry_valid_custom_agent():
    raw = (
        '[{"id":"swing-remote","name":"Swing Remote","kind":"remote",'
        '"remote_url":"https://example.com/agent","timeout_seconds":40}]'
    )
    parsed = parse_agent_registry(raw)
    assert len(parsed) == 1
    assert parsed[0].agent_id == "swing-remote"
    assert parsed[0].kind == "remote"
    assert parsed[0].timeout_seconds == 40


def test_registry_loads_defaults_and_custom(monkeypatch):
    monkeypatch.setenv(
        "AI_AGENTS_JSON",
        '[{"id":"custom-local","name":"Custom Local","kind":"local"}]',
    )
    reload_agent_registry()

    agents = get_registered_agents()
    ids = {a["id"] for a in agents}
    assert "core-analyst" in ids
    assert "risk-guardian" in ids
    assert "custom-local" in ids
    assert get_agent("custom-local") is not None

    monkeypatch.delenv("AI_AGENTS_JSON", raising=False)
    reload_agent_registry()
