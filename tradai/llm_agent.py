from __future__ import annotations
import json
import logging
import os
from typing import Dict, Optional
from pathlib import Path
import cachetools
import threading
import ast
import openai
try:  # Compatibilidad con OpenAI >=1.0
    from openai.error import (
        AuthenticationError,
        RateLimitError,
        APIError,
        OpenAIError,
    )
except Exception:  # pragma: no cover - fallback para nuevas versiones
    from openai import (
        AuthenticationError,
        RateLimitError,
        APIError,
        OpenAIError,
    )
from retry import retry
from .options import load_options
from .strategies import Strategy

# Configuración de logging consistente con otros módulos
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

OPENAI_OPTION_KEY = "openai_api_key"
STRATEGY_CACHE = cachetools.TTLCache(maxsize=100, ttl=3600)  # Cache for 1 hour
STRATEGY_FILE = Path("strategies.json")
FILE_LOCK = threading.Lock()

def validate_strategy_response(strategy: Dict) -> bool:
    """Valida que el diccionario de estrategia tenga las claves necesarias y condiciones válidas.

    Args:
        strategy (Dict): Diccionario con la estrategia generada por el LLM.

    Returns:
        bool: True si la estrategia es válida, False en caso contrario.
    """
    required_keys = {"symbol", "buy_condition", "sell_condition"}
    if not isinstance(strategy, dict):
        logger.error("Respuesta de estrategia no es un diccionario")
        return False
    if not all(key in strategy for key in required_keys):
        logger.error(f"Estrategia no contiene todas las claves requeridas: {required_keys}")
        return False
    if not isinstance(strategy["symbol"], str) or not strategy["symbol"].isupper():
        logger.error(f"Símbolo inválido: {strategy.get('symbol', 'N/A')}")
        return False
    # Validación de condiciones (deben ser expresiones lógicas simples)
    for condition in (strategy["buy_condition"], strategy["sell_condition"]):
        if not isinstance(condition, str):
            logger.error(f"Condición inválida (debe ser string): {condition}")
            return False
        if not any(ind in condition.lower() for ind in ["rsi", "ema", "macd", "atr", "candle"]):
            logger.error(f"Condición no incluye indicadores conocidos: {condition}")
            return False
        # Validación básica de sintaxis
        try:
            # Reemplazar indicadores por valores dummy para validar sintaxis
            dummy_condition = (
                condition.replace("RSI", "50")
                .replace("EMA20", "100")
                .replace("EMA50", "100")
                .replace("MACD", "0")
                .replace("ATR", "10")
                .replace("candle", "'bullish_engulfing'")
            )
            ast.parse(dummy_condition)
        except SyntaxError as e:
            logger.error(f"Sintaxis inválida en condición: {condition}, error: {e}")
            return False
    return True

def save_strategy(strategy: Dict, save_to_file: bool = True) -> None:
    """Guarda la estrategia en un archivo JSON para reutilización.

    Args:
        strategy (Dict): Diccionario con la estrategia a guardar.
        save_to_file (bool): Si True, guarda la estrategia en STRATEGY_FILE.
    """
    if not save_to_file:
        return
    try:
        strategies = []
        if STRATEGY_FILE.exists():
            with FILE_LOCK:
                with STRATEGY_FILE.open("r") as f:
                    strategies = json.load(f)
        strategies.append(strategy)
        with FILE_LOCK:
            STRATEGY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with STRATEGY_FILE.open("w") as f:
                json.dump(strategies, f, indent=2)
        logger.info(f"Estrategia guardada en {STRATEGY_FILE}")
    except Exception as e:
        logger.error(f"Error al guardar estrategia en {STRATEGY_FILE}: {e}")

@cachetools.cached(
    STRATEGY_CACHE,
    key=lambda *a, **kw: f"{a[0]}:{kw.get('model', 'gpt-3.5-turbo')}"
)
@retry((RateLimitError, APIError), tries=3, delay=2, backoff=2)
def suggest_strategy(
    user_prompt: str,
    model: str = "gpt-3.5-turbo",
    max_tokens: int = 500,
    temperature: float = 0.7,
    system_prompt: Optional[str] = None,
    save_to_file: bool = True
) -> Optional[Dict]:
    """Request the LLM to suggest a trading strategy.

    Args:
        user_prompt (str): Prompt describing the strategy idea (max 1000 characters).
        model (str, optional): OpenAI model to use for the request. Defaults to "gpt-3.5-turbo".
        max_tokens (int, optional): Maximum number of tokens for the response. Defaults to 500.
        temperature (float, optional): Temperature for controlling response creativity. Defaults to 0.7.
        system_prompt (str, optional): Custom system prompt to override the default.
        save_to_file (bool, optional): If True, save the strategy to STRATEGY_FILE. Defaults to True.

    Returns:
        dict | None: Strategy suggested by the LLM parsed from JSON, or None if invalid.

    Raises:
        RuntimeError: If the API key is missing, the request fails, or the response is invalid.
    """
    # Validación del prompt
    if not isinstance(user_prompt, str) or len(user_prompt) > 1000:
        logger.error("Prompt inválido: debe ser una cadena de máximo 1000 caracteres")
        raise RuntimeError("Invalid prompt: must be a string with max 1000 characters")
    if any(keyword in user_prompt.lower() for keyword in ["ignore", "bypass", "system", "assistant"]):
        logger.error("Prompt contiene palabras clave sospechosas")
        raise RuntimeError("Invalid prompt: contains restricted keywords")

    # Cargar opciones con fallback a variable de entorno
    opts = load_options() or {}
    api_key = opts.get(OPENAI_OPTION_KEY) or opts.get("openai_key") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OpenAI API key no configurada")
        raise RuntimeError("OpenAI API key not configured")

    # Configurar cliente OpenAI
    openai.api_key = api_key
    default_system_prompt = (
        "Eres un asistente que genera estrategias de trading en formato JSON. "
        "La estrategia debe incluir: 'symbol' (símbolo de la criptomoneda, ej. 'BTC'), "
        "'buy_condition' (condición de compra, ej. 'RSI < 30'), "
        "'sell_condition' (condición de venta, ej. 'RSI > 70'). "
        "Ejemplo: {\"symbol\": \"BTC\", \"buy_condition\": \"RSI < 30 and EMA20 > EMA50\", \"sell_condition\": \"RSI > 70\"}"
    )
    system_prompt = system_prompt or opts.get("system_prompt", default_system_prompt)

    # Solicitar estrategia al LLM
    try:
        logger.info(f"Enviando solicitud a LLM para generar estrategia con modelo {model}")
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature
        )
    except AuthenticationError as e:
        logger.error(f"Error de autenticación con OpenAI: {e}")
        raise RuntimeError(f"Authentication failed: {e}")
    except RateLimitError as e:
        logger.error(f"Límite de tasa alcanzado en OpenAI: {e}")
        raise RuntimeError(f"Rate limit exceeded: {e}")
    except APIError as e:
        logger.error(f"Error en la solicitud a OpenAI: {e}")
        raise RuntimeError(f"API request failed: {e}")
    except Exception as e:
        logger.error(f"Error inesperado en la solicitud a OpenAI: {e}")
        raise RuntimeError(f"LLM request failed: {e}")

    # Procesar la respuesta de la API
    try:
        content = resp["choices"][0]["message"]["content"]
        strategy = json.loads(content)
        if not validate_strategy_response(strategy):
            logger.error("Estrategia devuelta por el LLM no cumple con el formato esperado")
        else:
            logger.info(f"Estrategia generada exitosamente para símbolo: {strategy.get('symbol', 'N/A')}")
        save_strategy(strategy, save_to_file=save_to_file)
        return strategy
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Respuesta de LLM no es JSON válido o está mal formada: {e}")
        raise RuntimeError(f"Invalid LLM response: {e}")
