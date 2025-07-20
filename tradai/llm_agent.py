"""Utility functions to interact with an LLM service to generate strategies."""

from __future__ import annotations

import json

import openai
from .options import load_options


OPENAI_OPTION_KEY = "openai_api_key"


def suggest_strategy(user_prompt: str) -> dict:
    """Request the LLM to suggest a trading strategy.

    Parameters
    ----------
    user_prompt: str
        Prompt describing the strategy idea.

    Returns
    -------
    dict
        Strategy suggested by the LLM parsed from JSON.

    Raises
    ------
    RuntimeError
        If the API key is missing, the request fails or the response is not
        valid JSON.
    """

    opts = load_options() or {}
    api_key = opts.get(OPENAI_OPTION_KEY) or opts.get("openai_key")
    if not api_key:
        raise RuntimeError("OpenAI API key not configured")

    openai.api_key = api_key
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un asistente que genera estrategias de trading en formato JSON."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as exc:  # pragma: no cover - network/HTTP errors
        raise RuntimeError(f"LLM request failed: {exc}")

    try:
        content = resp["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as exc:
        raise RuntimeError(f"Invalid LLM response: {exc}")
