"""
Agent registry and execution helpers.

Supports two kinds of agents:
- local: runs in-process using the existing LLM stack
- remote: calls an external HTTP endpoint
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

_AGENTS_ENV_VAR = "AI_AGENTS_JSON"
_ID_SANITIZER = re.compile(r"[^a-z0-9_-]+")


@dataclass(frozen=True)
class AgentSpec:
    """Configuration for one specialized agent."""

    agent_id: str
    name: str
    kind: str = "local"  # local | remote
    description: str = ""
    system_prompt: str = ""
    remote_url: str = ""
    api_key_env: str = ""
    timeout_seconds: int = 25
    enabled: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.agent_id,
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "remote_url": self.remote_url if self.kind == "remote" else "",
            "api_key_env": self.api_key_env if self.kind == "remote" else "",
            "timeout_seconds": self.timeout_seconds,
            "enabled": self.enabled,
            "has_custom_prompt": bool(self.system_prompt.strip()),
        }


def _default_agents() -> list[AgentSpec]:
    return [
        AgentSpec(
            agent_id="core-analyst",
            name="Core Analyst",
            kind="local",
            description="General purpose trading analyst with full portfolio context.",
        ),
        AgentSpec(
            agent_id="risk-guardian",
            name="Risk Guardian",
            kind="local",
            description="Risk focused agent: concentration, downside and invalidation.",
            system_prompt=(
                "You are a strict risk manager for an institutional trading desk. "
                "Prioritize capital preservation. "
                "Always include: invalidation levels, position sizing, max loss plan, "
                "liquidity and execution caveats. Keep output concise in Spanish."
            ),
        ),
    ]


def _normalize_agent_id(value: str) -> str:
    normalized = _ID_SANITIZER.sub("-", (value or "").strip().lower())
    normalized = normalized.strip("-_")
    return normalized


def _to_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _to_int(value: Any, default: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(v, 120))


def parse_agent_registry(raw_json: str) -> list[AgentSpec]:
    """
    Parse AI_AGENTS_JSON into agent specs.

    Expected format:
    [
      {
        "id": "swing-remote",
        "name": "Swing Remote",
        "kind": "remote",
        "description": "...",
        "remote_url": "https://host/agent",
        "api_key_env": "MY_AGENT_KEY",
        "timeout_seconds": 30,
        "enabled": true
      }
    ]
    """
    text = (raw_json or "").strip()
    if not text:
        return []

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("%s invalid JSON: %s", _AGENTS_ENV_VAR, exc)
        return []

    if not isinstance(payload, list):
        logger.warning("%s must be a JSON array", _AGENTS_ENV_VAR)
        return []

    specs: list[AgentSpec] = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        agent_id = _normalize_agent_id(str(item.get("id") or item.get("agent_id") or ""))
        if not agent_id:
            continue

        kind = str(item.get("kind", "local")).strip().lower() or "local"
        if kind not in {"local", "remote"}:
            logger.warning("Ignoring agent '%s': unknown kind '%s'", agent_id, kind)
            continue

        remote_url = str(item.get("remote_url", "")).strip()
        if kind == "remote" and not remote_url:
            logger.warning("Ignoring remote agent '%s': remote_url is required", agent_id)
            continue

        specs.append(
            AgentSpec(
                agent_id=agent_id,
                name=str(item.get("name") or agent_id),
                kind=kind,
                description=str(item.get("description") or ""),
                system_prompt=str(item.get("system_prompt") or ""),
                remote_url=remote_url,
                api_key_env=str(item.get("api_key_env") or ""),
                timeout_seconds=_to_int(item.get("timeout_seconds"), 25),
                enabled=_to_bool(item.get("enabled"), True),
            )
        )

    return specs


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, AgentSpec]:
    registry: dict[str, AgentSpec] = {a.agent_id: a for a in _default_agents()}
    extra_specs = parse_agent_registry(os.getenv(_AGENTS_ENV_VAR, ""))
    for spec in extra_specs:
        registry[spec.agent_id] = spec
    return registry


def reload_agent_registry() -> None:
    """Clear in-memory cache so env updates are reloaded."""
    _load_registry.cache_clear()


def get_registered_agents(include_disabled: bool = False) -> list[dict[str, Any]]:
    specs = sorted(_load_registry().values(), key=lambda a: a.agent_id)
    if not include_disabled:
        specs = [a for a in specs if a.enabled]
    return [a.to_public_dict() for a in specs]


def get_agent(agent_id: str, include_disabled: bool = False) -> AgentSpec | None:
    aid = _normalize_agent_id(agent_id)
    if not aid:
        return None
    spec = _load_registry().get(aid)
    if spec is None:
        return None
    if not include_disabled and not spec.enabled:
        return None
    return spec


def _strategy_to_value(strategy: Any) -> str | None:
    if strategy is None:
        return None
    if hasattr(strategy, "value"):
        value = str(getattr(strategy, "value")).strip().lower()
        return value or None
    value = str(strategy).strip().lower()
    return value or None


def _compact_base_analysis(base: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticker": base.get("ticker"),
        "market": base.get("market"),
        "name": base.get("name"),
        "sector": base.get("sector"),
        "currency": base.get("currency"),
        "price": base.get("price"),
        "signal": base.get("signal"),
        "overall_score": base.get("overall_score"),
        "value_score": base.get("value_score"),
        "quality_score": base.get("quality_score"),
        "safety_score": base.get("safety_score"),
        "margin_of_safety": base.get("margin_of_safety"),
        "pe_ratio": base.get("pe_ratio"),
        "roe": base.get("roe"),
        "debt_to_equity": base.get("debt_to_equity"),
        "dividend_yield": base.get("dividend_yield"),
        "tech_summary": base.get("tech_summary"),
        "price_summary": base.get("price_summary"),
        "broker_tradability": base.get("broker_tradability") or {},
    }


def _render_reasoning(value: Any) -> str:
    if isinstance(value, list):
        lines = [f"- {str(v)}" for v in value[:6]]
        return "\n".join(lines)
    return str(value or "")


async def _run_local_agent(
    agent: AgentSpec,
    base_analysis: dict[str, Any],
    strategy: str | None,
    context: str,
) -> str:
    from ai.analyst import _call_llm, get_strategy_prompt

    ticker = str(base_analysis.get("ticker") or "").upper()
    market = str(base_analysis.get("market") or "")
    reasoning_text = _render_reasoning(base_analysis.get("reasoning"))
    strategy_value = strategy or str(base_analysis.get("strategy") or "value").lower()

    system_prompt = agent.system_prompt.strip() or get_strategy_prompt(strategy_value)
    user_prompt = (
        f"Actua como el agente especializado '{agent.name}'.\n"
        f"Ticker: {ticker}\n"
        f"Mercado: {market}\n"
        f"Estrategia: {strategy_value}\n"
        f"Signal base: {base_analysis.get('signal')} | Score: {base_analysis.get('overall_score')}\n"
        f"Precio actual: {base_analysis.get('price')} {base_analysis.get('currency')}\n"
        f"Margin of safety: {base_analysis.get('margin_of_safety')}\n"
        f"Broker tradability: {json.dumps(base_analysis.get('broker_tradability') or {}, ensure_ascii=True)}\n"
        f"Resumen tecnico: {base_analysis.get('tech_summary')}\n"
        f"Resumen de precio: {base_analysis.get('price_summary')}\n"
        f"Razonamiento base:\n{reasoning_text}\n\n"
        f"Contexto extra del usuario:\n{context or 'N/A'}\n\n"
        "Devuelve un informe accionable con:\n"
        "1) Tesis resumida\n"
        "2) Riesgos y nivel de conviccion\n"
        "3) Niveles clave (entrada/stop/salida)\n"
        "4) Plan de ejecucion para Trading212\n"
        "5) Condicion de invalidacion\n"
    )
    return await _call_llm(
        user_prompt=user_prompt,
        system=system_prompt,
        max_tokens=1400,
        context=f"agent_{agent.agent_id}_{ticker}",
        cache_ttl=180,
    )


async def _run_remote_agent(
    agent: AgentSpec,
    base_analysis: dict[str, Any],
    strategy: str | None,
    context: str,
) -> str:
    try:
        import aiohttp
    except ImportError as exc:
        raise RuntimeError(
            "aiohttp is required for remote agents. Install dependencies from requirements.txt"
        ) from exc

    headers = {"Content-Type": "application/json"}
    if agent.api_key_env:
        secret = os.getenv(agent.api_key_env, "").strip()
        if secret:
            headers["Authorization"] = f"Bearer {secret}"

    payload = {
        "agent_id": agent.agent_id,
        "agent_name": agent.name,
        "ticker": base_analysis.get("ticker"),
        "market": base_analysis.get("market"),
        "strategy": strategy or base_analysis.get("strategy"),
        "context": context,
        "base_analysis": _compact_base_analysis(base_analysis),
        "timestamp": datetime.now(UTC).isoformat(),
    }

    timeout = aiohttp.ClientTimeout(total=agent.timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(agent.remote_url, headers=headers, json=payload) as resp:
            body_text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(
                    f"Remote agent HTTP {resp.status}: {body_text[:300]}"
                )

            data: Any
            try:
                data = json.loads(body_text)
            except json.JSONDecodeError:
                return body_text

            if isinstance(data, dict):
                text = (
                    data.get("analysis")
                    or data.get("text")
                    or data.get("message")
                    or ""
                )
                if text:
                    return str(text)
                return json.dumps(data, ensure_ascii=True)

            if isinstance(data, list):
                return json.dumps(data, ensure_ascii=True)

            return str(data)


async def run_agent(
    agent_id: str,
    ticker: str,
    market: str | None = None,
    strategy: Any = None,
    context: str = "",
) -> dict[str, Any]:
    """Execute an agent against a ticker and return enriched analysis."""
    from signals.signal_engine import analyze_ticker

    agent = get_agent(agent_id)
    if agent is None:
        raise ValueError(f"Agent '{agent_id}' not found or disabled")

    strategy_value = _strategy_to_value(strategy)
    base_analysis = await analyze_ticker(
        ticker=ticker,
        market=market,
        strategy=strategy_value,
    )
    if base_analysis.get("error"):
        raise ValueError(base_analysis["error"])

    if agent.kind == "remote":
        analysis_text = await _run_remote_agent(agent, base_analysis, strategy_value, context)
    else:
        analysis_text = await _run_local_agent(agent, base_analysis, strategy_value, context)

    return {
        "agent": agent.to_public_dict(),
        "ticker": base_analysis.get("ticker"),
        "market": base_analysis.get("market"),
        "strategy": strategy_value or base_analysis.get("strategy"),
        "analysis": analysis_text,
        "base_analysis": _compact_base_analysis(base_analysis),
        "created_at": datetime.now(UTC).isoformat(),
    }
