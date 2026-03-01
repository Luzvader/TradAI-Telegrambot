"""
Analista IA – usa OpenAI para generar análisis contextual:
  • Contexto geopolítico y macroeconómico
  • Análisis sectorial
  • Opinión sobre tickers específicos
  • Integración con datos de aprendizaje previo
"""

import asyncio
import json
import logging
import time
from typing import Any

from openai import AsyncOpenAI, BadRequestError

from config.settings import OPENAI_API_KEY, OPENAI_MODEL
from config.settings import TRADING212_ANALYSIS_ORIENTED
from data.news import get_geopolitical_context, get_sector_news
from data.cache import ai_cache
from database import repository as repo

logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

SYSTEM_PROMPT = """Eres un analista financiero senior de un gran fondo de inversión. Estilo: gestor conservador con visión.
Tu análisis debe ser riguroso, basado en datos financieros oficiales, conservador en supuestos y orientado a la preservación de capital y creación de valor a largo plazo.
Reglas: contexto geopolítico, fundamentales críticos (P/E, ROE, deuda, FCF), margen seguridad 15-20%, diversificación (máx 5% ticker, 20% sector), horizonte 6-24m, aprendes de errores, conciso con emojis, en español."""

# Base compartida para reducir tokens repetidos
_COMMON_RULES = "Aprendes de errores. Conciso, emojis, español."

STRATEGY_PROMPTS: dict[str, str] = {
    "value": SYSTEM_PROMPT,
    "growth": f"""Analista financiero senior, Growth Investing. Gestor orientado a crecimiento con disciplina.
Priorizas alto crecimiento revenue/earnings, aceptas múltiplos altos si crecimiento justifica, valoras márgenes y escalabilidad, consideras TAM y ventajas competitivas. Horizonte 1-3 años. {_COMMON_RULES}""",
    "dividend": f"""Analista financiero senior, Dividend/Income Investing. Gestor de rentas conservador.
Priorizas dividend yield sostenible y creciente, FCF como base, payout <75%, baja deuda, Dividend Aristocrats. Horizonte 3-10 años. {_COMMON_RULES}""",
    "balanced": f"""Analista financiero senior, enfoque Balanced (Value+Growth).
Valoración razonable CON crecimiento sólido, calidad del negocio (ROE, márgenes), equilibrio cíclicos/defensivos. Horizonte 1-3 años. {_COMMON_RULES}""",
    "conservative": f"""Analista financiero senior ultra-conservador.
Estabilidad: beta ≤1, baja deuda, FCF positivo. Large caps defensivas y predecibles. Evitas cíclicos y alta deuda. Capital preservation > apreciación. Horizonte 3-5 años. {_COMMON_RULES}""",
}

# ── Bloques de análisis profundo para usar en prompts ────────

INDUSTRY_ANALYSIS_PROMPT = """
🔍 ANÁLISIS PROFUNDO DE LA INDUSTRIA:
1) Definición y mapa: industria/subindustria exacta, cadena de valor (proveedores → producción → distribución → cliente), modelo económico típico (drivers de ingresos, estructura de costes, dónde se captura el margen).
2) Dinámicas competitivas: competencia (fragmentada vs concentrada, precio vs diferenciación, switching costs), efectos de red, economías de escala, barreras de entrada/salida, poder de proveedores/clientes, amenaza de sustitutos.
3) Márgenes medios industria: rangos típicos de margen bruto, EBITDA/EBIT, margen neto. Compara con la empresa y explica desviaciones (mix, geografía, pricing power, eficiencia, ciclo).
4) Crecimiento industria: CAGR histórico y esperado, estructural vs cíclico, impulsores (demografía, tecnología, regulación, penetración, precios/volumen).
5) Retos y riesgos clave: top 3-5 con impacto (alto/medio/bajo) + horizonte (corto/medio/largo).
6) Sensibilidad: clasificar defensiva/semi-cíclica/cíclica, comportamiento en recesiones y ante tipos de interés.
7) Cuota de mercado: principales competidores, cuota estimada empresa y top 3-5, tendencia consolidación vs fragmentación.
"""

COMPANY_ANALYSIS_PROMPT = """
📊 ANÁLISIS PROFUNDO DE LA EMPRESA:
1) ¿Qué hace? Core products/services, qué impulsa valor a largo plazo.
2) ¿Cómo gana dinero? Revenue streams y segmentos operativos, % contribución de cada uno.
3) ¿Quiénes son sus clientes? Tipos (B2B/B2C, SMBs, enterprises, gobiernos), concentración.
4) ¿Competidores? Directos y alternativos (sustitutos), posicionamiento competitivo.
5) ¿Dónde opera? Desglose geográfico de ingresos.
6) ¿Ingresos recurrentes? Contratos, suscripciones, renewal rates, switching costs.
7) ¿Pricing power? Tendencias de márgenes bruto/operativo, evidencia en periodos inflacionarios.
8) ¿Qué pasa en recesión? Ciclicidad, rendimiento histórico en crisis, warnings del management.
9) ¿Deuda? Estructura capital: deuda total, vencimientos, tipos fijo vs variable, coste, vs cash y FCF.
"""


def get_strategy_prompt(strategy: str | None = None) -> str:
    """Devuelve el system prompt adaptado a la estrategia."""
    if strategy is None:
        return SYSTEM_PROMPT
    return STRATEGY_PROMPTS.get(strategy.lower(), SYSTEM_PROMPT)


def _compact_fundamentals(data: dict[str, Any]) -> str:
    """
    Comprime un dict de fundamentales eliminando claves con valor None/N/A
    y formateando de forma compacta para reducir tokens en el prompt.
    """
    filtered = {
        k: v for k, v in data.items()
        if v is not None and v != "N/A" and v != ""
    }
    if not filtered:
        return "{}"
    # Formatear números para legibilidad
    parts: list[str] = []
    for k, v in filtered.items():
        if isinstance(v, float):
            parts.append(f"{k}: {v:.4g}")
        else:
            parts.append(f"{k}: {v}")
    return "\n".join(parts)


def _is_reasoning_model(model: str) -> bool:
    """Detecta si el modelo es de razonamiento (o-series o gpt-5+)."""
    m = model.lower()
    return m.startswith(("o1", "o3", "o4", "gpt-5"))


# Precios por 1M tokens (USD) – actualizar cuando OpenAI cambie tarifas
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    # (input_per_1M, output_per_1M)
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    "o3": (10.00, 40.00),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (1.10, 4.40),
    "gpt-5": (2.00, 8.00),
    "gpt-5.2": (2.00, 8.00),
}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estima el coste en USD de una llamada a la API de OpenAI."""
    # Buscar modelo exacto o prefijo más largo
    pricing = _MODEL_PRICING.get(model.lower())
    if pricing is None:
        # Buscar por prefijo
        for prefix, p in sorted(_MODEL_PRICING.items(), key=lambda x: -len(x[0])):
            if model.lower().startswith(prefix):
                pricing = p
                break
    if pricing is None:
        # Default: gpt-4o pricing
        pricing = (2.50, 10.00)

    input_cost = prompt_tokens * pricing[0] / 1_000_000
    output_cost = completion_tokens * pricing[1] / 1_000_000
    return round(input_cost + output_cost, 6)


# ── Rate Limiter ─────────────────────────────────────────────


class _RateLimiter:
    """
    Token bucket rate limiter para llamadas a la API de OpenAI.
    Limita tanto peticiones por minuto (RPM) como tokens por minuto (TPM).
    """

    def __init__(self, rpm: int = 60, tpm: int = 150_000):
        self._rpm = rpm
        self._tpm = tpm
        self._request_times: list[float] = []
        self._token_counts: list[tuple[float, int]] = []  # (timestamp, tokens)
        self._lock = asyncio.Lock()

    async def acquire(self, estimated_tokens: int = 1000) -> None:
        """Espera hasta que haya capacidad disponible."""
        async with self._lock:
            now = time.monotonic()
            window = 60.0  # 1 minuto

            # Limpiar entradas antiguas
            self._request_times = [t for t in self._request_times if now - t < window]
            self._token_counts = [(t, n) for t, n in self._token_counts if now - t < window]

            # Check RPM
            while len(self._request_times) >= self._rpm:
                wait = self._request_times[0] + window - now
                if wait > 0:
                    logger.debug(f"Rate limit RPM: esperando {wait:.1f}s")
                    await asyncio.sleep(wait)
                now = time.monotonic()
                self._request_times = [t for t in self._request_times if now - t < window]

            # Check TPM
            current_tokens = sum(n for _, n in self._token_counts)
            while current_tokens + estimated_tokens > self._tpm:
                wait = self._token_counts[0][0] + window - now
                if wait > 0:
                    logger.debug(f"Rate limit TPM: esperando {wait:.1f}s")
                    await asyncio.sleep(wait)
                now = time.monotonic()
                self._token_counts = [(t, n) for t, n in self._token_counts if now - t < window]
                current_tokens = sum(n for _, n in self._token_counts)

            # Registrar
            self._request_times.append(now)
            self._token_counts.append((now, estimated_tokens))

    def record_actual_tokens(self, tokens: int) -> None:
        """Actualiza el último registro con los tokens reales usados."""
        if self._token_counts:
            ts, _ = self._token_counts[-1]
            self._token_counts[-1] = (ts, tokens)


_rate_limiter = _RateLimiter()


async def _call_llm(
    user_prompt: str, system: str = SYSTEM_PROMPT, max_tokens: int = 1000,
    context: str = "general", cache_ttl: int | None = None,
) -> str:
    """
    Llamada genérica al LLM con detección automática de modelo.
    - Modelos de razonamiento (o1, o3…): sin temperature, max_completion_tokens.
    - Modelos de chat (gpt-*): max_completion_tokens (estándar moderno).
    - Fallback automático si el modelo rechaza algún parámetro.
    - Registra uso de tokens y coste estimado.
    - Cachea respuestas por context+prompt_hash para evitar llamadas duplicadas.
      cache_ttl: segundos de caché (None = TTL por defecto del ai_cache, 0 = sin caché).
    """
    if client is None:
        return "⚠️ OpenAI API no configurada. Configura OPENAI_API_KEY en .env"

    # Validar prompt no vacío
    if not user_prompt or not user_prompt.strip():
        logger.warning("_call_llm: prompt vacío, omitiendo llamada")
        return "⚠️ Prompt vacío"

    # ── Caché de respuestas AI ──
    use_cache = cache_ttl != 0
    cache_key = ""
    if use_cache:
        import hashlib
        prompt_hash = hashlib.md5(
            (system[:80] + user_prompt).encode(), usedforsecurity=False
        ).hexdigest()[:12]
        cache_key = f"llm:{context}:{prompt_hash}"
        cached = ai_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"🎯 AI cache hit: {context}")
            return cached

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]

    reasoning = _is_reasoning_model(OPENAI_MODEL)

    # Rate limiting antes de llamar a la API
    estimated_tokens = len(user_prompt) // 3 + max_tokens  # Estimación rough
    await _rate_limiter.acquire(estimated_tokens)

    # Estrategias de parámetros a probar en orden
    strategies: list[dict[str, Any]] = []

    # gpt-5+ puede usar reasoning tokens internos que consumen el budget;
    # pedimos extra para cubrir reasoning + respuesta visible.
    effective_max = max_tokens * 3 if reasoning else max_tokens

    if reasoning:
        # Modelos de razonamiento: sin temperature, solo max_completion_tokens
        strategies.append({"max_completion_tokens": effective_max})
    else:
        # Modelos de chat modernos: max_completion_tokens + temperature
        strategies.append({"temperature": 0.3, "max_completion_tokens": max_tokens})
        # Fallback 1: sin temperature
        strategies.append({"max_completion_tokens": max_tokens})
        # Fallback 2: max_tokens clásico (modelos antiguos)
        strategies.append({"temperature": 0.3, "max_tokens": max_tokens})

    last_error = ""
    for strategy in strategies:
        try:
            response = await client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                **strategy,
            )
            # Registrar uso de tokens
            try:
                usage = response.usage
                if usage:
                    prompt_t = usage.prompt_tokens or 0
                    completion_t = usage.completion_tokens or 0
                    total_t = prompt_t + completion_t
                    _rate_limiter.record_actual_tokens(total_t)
                    cost = _estimate_cost(OPENAI_MODEL, prompt_t, completion_t)
                    await repo.save_openai_usage(
                        model=OPENAI_MODEL,
                        prompt_tokens=prompt_t,
                        completion_tokens=completion_t,
                        total_tokens=total_t,
                        context=context,
                        estimated_cost_usd=cost,
                    )
            except Exception as ue:
                logger.warning(f"Error registrando uso de OpenAI: {ue}")

            result_text = response.choices[0].message.content or ""

            # Si contenido vacío y reasoning tokens consumieron el budget, reintentar con más tokens
            if not result_text and response.choices[0].finish_reason == "length":
                reasoning_used = 0
                try:
                    reasoning_used = (response.usage.completion_tokens_details.reasoning_tokens or 0) if response.usage and response.usage.completion_tokens_details else 0
                except Exception as e:
                    logger.debug(f"No se pudo leer reasoning_tokens: {e}")
                if reasoning_used > 0:
                    logger.warning(
                        f"Respuesta vacía: reasoning consumió {reasoning_used} tokens. "
                        f"Reintentando con {max_tokens * 4} max_completion_tokens"
                    )
                    retry_response = await client.chat.completions.create(
                        model=OPENAI_MODEL,
                        messages=messages,
                        max_completion_tokens=max_tokens * 4,
                    )
                    result_text = retry_response.choices[0].message.content or ""
                    # Registrar uso del retry
                    try:
                        ru = retry_response.usage
                        if ru:
                            await repo.save_openai_usage(
                                model=OPENAI_MODEL,
                                prompt_tokens=ru.prompt_tokens or 0,
                                completion_tokens=ru.completion_tokens or 0,
                                total_tokens=(ru.prompt_tokens or 0) + (ru.completion_tokens or 0),
                                context=f"{context}_retry",
                                estimated_cost_usd=_estimate_cost(OPENAI_MODEL, ru.prompt_tokens or 0, ru.completion_tokens or 0),
                            )
                    except Exception as e:
                        logger.debug(f"Error guardando uso OpenAI (retry): {e}")

            # Guardar en caché
            if use_cache and cache_key and result_text and not result_text.startswith("⚠️"):
                ttl = cache_ttl if cache_ttl and cache_ttl > 0 else None
                ai_cache.set(cache_key, result_text, ttl=ttl)

            return result_text
        except BadRequestError as e:
            body = e.body if isinstance(e.body, dict) else {}
            err = body.get("error") if isinstance(body.get("error"), dict) else {}
            param = err.get("param", "") if err else ""
            last_error = (err.get("message") if err else None) or str(e)

            # Si el parámetro rechazado es uno de los que estamos probando,
            # la siguiente estrategia lo cambiará → continuar.
            if param in ("max_tokens", "max_completion_tokens", "temperature"):
                logger.info(
                    f"Modelo {OPENAI_MODEL} rechazó '{param}', probando siguiente estrategia"
                )
                continue

            # Error no recuperable
            logger.error(f"Error llamando a OpenAI: {last_error}")
            return f"⚠️ Error en análisis IA: {last_error}"
        except Exception as e:
            logger.error(f"Error llamando a OpenAI: {e}")
            return f"⚠️ Error en análisis IA: {str(e)}"

    logger.error(f"Error llamando a OpenAI: todas las estrategias fallaron – {last_error}")
    return f"⚠️ Error en análisis IA: {last_error}"


async def analyze_with_context(
    ticker: str,
    market: str | None,
    fundamentals: dict[str, Any],
    portfolio_context: dict[str, Any] | None = None,
    strategy: str | None = None,
    deterministic_context: str = "",
) -> str:
    """
    Análisis completo de un ticker con contexto geopolítico,
    sectorial y aprendizaje previo.

    Si se proporciona `deterministic_context` (resúmenes técnico y de
    valoración pre-computados), el prompt se recorta para que la IA
    solo aporte juicio cualitativo, ahorrando tokens.
    """
    # Validar ticker
    ticker = ticker.strip().upper()
    if not ticker:
        return "⚠️ Ticker no proporcionado"
    market_norm = market.upper() if market else None

    # 1. Contexto geopolítico
    geo_context = await get_geopolitical_context()

    # 2. Noticias del sector
    sector = fundamentals.get("sector", "")
    sector_news = await get_sector_news(sector) if sector else []
    sector_headlines = "\n".join(
        [f"  - {n['title']}" for n in sector_news[:5]]
    ) or "Sin noticias sectoriales recientes."

    # 3. Aprendizaje previo
    learning_summary = await repo.get_learning_summary()
    recent_lessons = await repo.get_learning_logs(limit=5)
    lessons_text = "\n".join(
        [f"  - {l.ticker} ({l.outcome}): {l.lessons_learned}" for l in recent_lessons if l.lessons_learned]
    ) or "Sin lecciones previas registradas."

    # 3b. Objetivo de inversión (si existe)
    obj = await repo.get_investment_objective(ticker, market=market_norm)
    objective_text = ""
    if obj:
        obj_parts = ["\nOBJETIVO INVERSIÓN PREVIO:"]
        if obj.thesis:
            obj_parts.append(f"  Tesis: {obj.thesis}")
        if obj.target_entry_price:
            obj_parts.append(f"  Entrada obj: {obj.target_entry_price}$")
        if obj.target_exit_price:
            obj_parts.append(f"  Salida obj: {obj.target_exit_price}$")
        if obj.catalysts:
            obj_parts.append(f"  Catalizadores: {obj.catalysts}")
        if obj.risks:
            obj_parts.append(f"  Riesgos: {obj.risks}")
        if obj.conviction:
            obj_parts.append(f"  Convicción: {obj.conviction}/10 | Horizonte: {obj.time_horizon or 'N/A'}")
        objective_text = "\n".join(obj_parts) + "\n"

    # 3c. Contexto de operabilidad en Trading212 (orienta recomendaciones)
    tradability_text = ""
    if TRADING212_ANALYSIS_ORIENTED:
        try:
            from broker.bridge import get_trading212_tradability

            tradability = await get_trading212_tradability(ticker, market_norm)
            if tradability.get("tradable") is True:
                tradability_text = (
                    "OPERABILIDAD TRADING212:\n"
                    "  Activo operable en Trading212.\n"
                )
            elif tradability.get("tradable") is False:
                tradability_text = (
                    "OPERABILIDAD TRADING212:\n"
                    f"  No operable en Trading212 ({tradability.get('reason', 'sin detalle')}).\n"
                )
            else:
                tradability_text = (
                    "OPERABILIDAD TRADING212:\n"
                    f"  No verificado ({tradability.get('reason', 'sin detalle')}).\n"
                )
        except Exception as e:
            tradability_text = f"OPERABILIDAD TRADING212:\n  No verificado ({e}).\n"

    # 4. Contexto del portfolio (compacto)
    portfolio_text = ""
    if portfolio_context:
        pv = portfolio_context.get('total_value', 'N/A')
        pc = portfolio_context.get('cash', 'N/A')
        pp = portfolio_context.get('num_positions', 0)
        pr = portfolio_context.get('return_pct', 0)
        portfolio_text = f"\nPortfolio: {pv}$ | Cash: {pc}$ | {pp} pos | {pr}% retorno\n"

    # ── Prompt adaptado: con o sin contexto determinista ──
    if deterministic_context:
        # Prompt reducido: el análisis técnico y de valoración ya están hechos.
        # La IA sólo aporta juicio cualitativo (ahorro ~40% tokens).
        prompt = f"""${ticker} — Análisis cualitativo (técnico/valoración ya pre-computados):

{deterministic_context}

CONTEXTO GEOPOLÍTICO:
{geo_context}

NOTICIAS SECTOR ({sector}):
{sector_headlines}

APRENDIZAJE (Win rate: {learning_summary.get('wins', 0)}/{learning_summary.get('total_trades_analyzed', 0)}, Avg: {learning_summary.get('avg_profit_pct', 0)}%):
{lessons_text}
{objective_text}{portfolio_text}{tradability_text}

Los análisis técnico y de valoración ya están pre-computados arriba.
Responde con:

{INDUSTRY_ANALYSIS_PROMPT}

{COMPANY_ANALYSIS_PROMPT}

Además:
1. Riesgos principales (3-5) con impacto y horizonte
2. Catalizadores (3-5) con timing esperado
3. Si no es operable en Trading212, indica alternativa operable equivalente
4. Si hay objetivo previo, evalúa si la tesis sigue vigente
5. Conclusión ejecutiva en 5-8 bullets (atractivo estructural, motor de crecimiento, principal riesgo, pricing power, edge/desventaja vs sector)
6. Resumen final en 2-3 frases
"""
        ctx = f"analyze_{ticker}" + (f"_{market_norm}" if market_norm else "")
        return await _call_llm(prompt, system=get_strategy_prompt(strategy), max_tokens=2000, context=ctx)
    else:
        # Prompt completo (fallback sin contexto determinista)
        prompt = f"""Analiza ${ticker}:

FUNDAMENTALES:
{_compact_fundamentals(fundamentals)}

CONTEXTO GEOPOLÍTICO:
{geo_context}

NOTICIAS SECTOR ({sector}):
{sector_headlines}

APRENDIZAJE (Win rate: {learning_summary.get('wins', 0)}/{learning_summary.get('total_trades_analyzed', 0)}, Avg: {learning_summary.get('avg_profit_pct', 0)}%):
{lessons_text}
{objective_text}{portfolio_text}{tradability_text}

Responde con un análisis completo que incluya:

{INDUSTRY_ANALYSIS_PROMPT}

{COMPANY_ANALYSIS_PROMPT}

Además:
1. Veredicto: BUY / HOLD / SELL
2. Convicción: 1-10
3. Riesgos principales (3-5) con impacto (alto/medio/bajo) y horizonte (corto/medio/largo)
4. Catalizadores (3-5) con timing esperado
5. Precio objetivo (con rango de escenarios: bear/base/bull)
6. Si no es operable en Trading212, indica alternativa operable equivalente
7. Si hay objetivo previo, evalúa si la tesis sigue vigente
8. Conclusión ejecutiva: atractivo estructural de la industria, motor de crecimiento, principal riesgo, pricing power, edge/desventaja de la empresa vs sector
9. Resumen en 2-3 frases
"""
        ctx = f"analyze_{ticker}" + (f"_{market_norm}" if market_norm else "")
        return await _call_llm(prompt, system=get_strategy_prompt(strategy), max_tokens=3000, context=ctx)


async def get_macro_analysis(strategy: str | None = None) -> str:
    """Genera un análisis macroeconómico general."""
    geo = await get_geopolitical_context()
    prompt = f"""Análisis macro breve basado en titulares recientes:

{geo}

Incluye:
1. Sentimiento del mercado (1-10)
2. Riesgos geopolíticos clave
3. Oportunidades actuales
4. Sectores favorecidos / perjudicados
5. Recomendación (incrementar/mantener/reducir exposición)
"""
    return await _call_llm(prompt, system=get_strategy_prompt(strategy), max_tokens=600, context="macro_analysis")


async def generate_trade_rationale(
    ticker: str, side: str, fundamentals: dict[str, Any],
    strategy: str | None = None,
) -> str:
    """Genera un razonamiento para una operación específica."""
    prompt = f"""Genera un razonamiento breve para esta operación:
Operación: {side} ${ticker}
Datos: {json.dumps(fundamentals, indent=2, default=str)}

Formato: 3-4 bullets concisos explicando por qué es buena idea (o no) esta operación.
"""
    return await _call_llm(prompt, system=get_strategy_prompt(strategy), max_tokens=400, context=f"rationale_{ticker}")
