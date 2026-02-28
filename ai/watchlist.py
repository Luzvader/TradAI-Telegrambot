"""
Watchlist IA – genera y mantiene una watchlist de hasta 5 acciones
fuera de la cartera que merecen estudio.
"""

import asyncio
import json
import logging
from typing import Any

from ai.analyst import _call_llm
from data.fundamentals import fetch_fundamentals
from database import repository as repo
from database.models import PortfolioType, StrategyType
from strategy.selector import get_strategy_analyzer

logger = logging.getLogger(__name__)

def _parse_json_array_response(response: str) -> list[dict[str, Any]] | None:
    clean = response.strip()
    if not clean:
        return None
    if clean.startswith("⚠️"):
        return None

    # Limpiar posibles markdown markers
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1]
        clean = clean.rsplit("```", 1)[0].strip()

    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        start = clean.find("[")
        end = clean.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(clean[start : end + 1])
        except Exception:
            return None

    return parsed if isinstance(parsed, list) else None


async def _get_active_strategy() -> StrategyType:
    portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
    return portfolio.strategy if portfolio and portfolio.strategy else StrategyType.VALUE


def _build_watchlist_prompt(strategy: StrategyType, excluded: str) -> str:
    base = (
        "Responde SOLO con un JSON array así:\n"
        "[\n"
        "  {\n"
        "    \"ticker\": \"AAPL\",\n"
        "    \"market\": \"NASDAQ\",\n"
        "    \"reason\": \"razón detallada de por qué merece estudio\",\n"
        "    \"thesis\": \"tesis de inversión concisa\",\n"
        "    \"target_entry\": 150.0,\n"
        "    \"target_exit\": 200.0,\n"
        "    \"catalysts\": \"catalizadores esperados (earnings, productos, etc.)\",\n"
        "    \"risks\": \"principales riesgos identificados\",\n"
        "    \"conviction\": 7,\n"
        "    \"time_horizon\": \"medio\"\n"
        "  }\n"
        "]\n"
        "Sin explicaciones adicionales, solo el JSON.\n"
        "conviction: 1-10 (1=baja, 10=muy alta)\n"
        "time_horizon: corto (<6m), medio (6-24m), largo (>24m)\n"
        "target_entry y target_exit: precios en la moneda del mercado\n"
    )

    if strategy == StrategyType.GROWTH:
        return f"""Como analista growth, sugiere exactamente 5 acciones para estudiar
como posibles inversiones. Deben ser empresas que:
- Coticen en NASDAQ, NYSE, IBEX 35, DAX, CAC 40, FTSE MIB, AEX, FTSE 100
- Tengan crecimiento fuerte (revenue/earnings) y márgenes sólidos
- Tengan una valoración razonable para growth (evitar extremos)
- NO estén ya en cartera (excluir: {excluded})

Para cada acción, justifica DETALLADAMENTE por qué merece estudio,
define una tesis de inversión, catalizadores esperados, riesgos y precios objetivo.

{base}"""

    if strategy == StrategyType.DIVIDEND:
        return f"""Como analista dividend/income, sugiere exactamente 5 acciones para estudiar
como posibles inversiones. Deben ser empresas que:
- Coticen en NASDAQ, NYSE, IBEX 35, DAX, CAC 40, FTSE MIB, AEX, FTSE 100
- Tengan dividend yield atractivo y estabilidad financiera
- Mantengan deuda controlada y cash flow saludable
- NO estén ya en cartera (excluir: {excluded})

Para cada acción, justifica DETALLADAMENTE por qué merece estudio,
define una tesis de inversión, catalizadores esperados, riesgos y precios objetivo.

{base}"""

    if strategy == StrategyType.BALANCED:
        return f"""Como analista balanced, sugiere exactamente 5 acciones para estudiar
como posibles inversiones. Deben ser empresas que:
- Coticen en NASDAQ, NYSE, IBEX 35, DAX, CAC 40, FTSE MIB, AEX, FTSE 100
- Combinen valoración razonable con crecimiento/quality
- Tengan balance sólido y riesgo controlado
- NO estén ya en cartera (excluir: {excluded})

Para cada acción, justifica DETALLADAMENTE por qué merece estudio,
define una tesis de inversión, catalizadores esperados, riesgos y precios objetivo.

{base}"""

    if strategy == StrategyType.CONSERVATIVE:
        return f"""Como analista conservador/defensivo, sugiere exactamente 5 acciones para estudiar
como posibles inversiones. Deben ser empresas que:
- Coticen en NASDAQ, NYSE, IBEX 35, DAX, CAC 40, FTSE MIB, AEX, FTSE 100
- Sean empresas estables (baja volatilidad, deuda baja, cash flow positivo)
- Preferiblemente large caps / negocios defensivos
- NO estén ya en cartera (excluir: {excluded})

Para cada acción, justifica DETALLADAMENTE por qué merece estudio,
define una tesis de inversión, catalizadores esperados, riesgos y precios objetivo.

{base}"""

    # VALUE por defecto
    return f"""Como analista value, sugiere exactamente 5 acciones para estudiar
como posibles inversiones. Deben ser empresas que:
- Coticen en NASDAQ, NYSE, IBEX 35, DAX, CAC 40, FTSE MIB, AEX, FTSE 100
- Tengan fundamentales sólidos para value investing
- NO estén ya en cartera (excluir: {excluded})

Para cada acción, justifica DETALLADAMENTE por qué merece estudio,
define una tesis de inversión, catalizadores esperados, riesgos y precios objetivo.

{base}"""


async def ai_generate_watchlist(
    current_portfolio_tickers: list[str],
) -> list[dict[str, Any]]:
    """
    Pide a la IA que sugiera hasta 5 tickers para estudiar,
    excluyendo los que ya están en cartera.
    """
    excluded = ", ".join(current_portfolio_tickers) or "ninguno"

    active_strategy = await _get_active_strategy()
    prompt = _build_watchlist_prompt(active_strategy, excluded)
    response = await _call_llm(prompt, max_tokens=500)

    # Guard: respuesta vacía o error
    if not response or response.startswith("⚠️"):
        logger.warning(f"Watchlist IA: respuesta vacía o error: {response[:80] if response else 'vacía'}")
        return []

    # Parsear respuesta
    suggestions = _parse_json_array_response(response)
    if suggestions is None:
        logger.error(f"Error parseando watchlist IA.\nRespuesta: {response}")
        return []

    # Validar y añadir a la watchlist (máx 5)
    added = []
    current_watchlist = await repo.get_active_watchlist()
    current_wl_tickers = [w.ticker for w in current_watchlist]

    for item in suggestions[:5]:
        ticker = item.get("ticker", "").upper()
        if not ticker or ticker in current_portfolio_tickers or ticker in current_wl_tickers:
            continue

        market = item.get("market", "NASDAQ")
        reason = item.get("reason", "")
        thesis = item.get("thesis", "")
        catalysts = item.get("catalysts", "")
        risks = item.get("risks", "")
        conviction = item.get("conviction")
        time_horizon = item.get("time_horizon", "medio")
        target_entry = item.get("target_entry")
        target_exit = item.get("target_exit")

        # Construir razón enriquecida
        rich_reason = reason
        if thesis:
            rich_reason += f"\n📝 Tesis: {thesis}"
        if catalysts:
            rich_reason += f"\n🚀 Catalizadores: {catalysts}"
        if risks:
            rich_reason += f"\n⚠️ Riesgos: {risks}"

        # Obtener sector
        try:
            fd = await asyncio.to_thread(fetch_fundamentals, ticker, market)
            sector = fd.sector
        except Exception:
            sector = None

        wl_item = await repo.add_to_watchlist(
            ticker=ticker,
            market=market,
            sector=sector,
            reason=rich_reason,
            ai_notes=f"Sugerida por IA | Convicción: {conviction or 'N/A'}/10",
        )

        # Guardar objetivo de inversión
        if wl_item:
            try:
                await repo.save_investment_objective(
                    ticker=ticker,
                    market=market,
                    thesis=thesis or reason,
                    target_entry_price=float(target_entry) if target_entry else None,
                    target_exit_price=float(target_exit) if target_exit else None,
                    catalysts=catalysts or None,
                    risks=risks or None,
                    time_horizon=time_horizon,
                    conviction=int(conviction) if conviction else None,
                    source="ai",
                )
            except Exception as e:
                logger.warning(f"Error guardando objetivo para {ticker}: {e}")

            added.append({
                "ticker": ticker,
                "market": market,
                "sector": sector,
                "reason": reason,
                "thesis": thesis,
                "catalysts": catalysts,
                "risks": risks,
                "conviction": conviction,
                "target_entry": target_entry,
                "target_exit": target_exit,
            })

    logger.info(f"📋 Watchlist actualizada: {len(added)} nuevos tickers")
    return added


async def refresh_watchlist_analysis() -> list[dict[str, Any]]:
    """Re-analiza los tickers en la watchlist activa."""
    watchlist = await repo.get_active_watchlist()
    results = []
    active_strategy = await _get_active_strategy()
    analyzer = get_strategy_analyzer(active_strategy)

    for item in watchlist:
        try:
            fd = await asyncio.to_thread(fetch_fundamentals, item.ticker, item.market)
            vs = await asyncio.to_thread(analyzer, fd)
            results.append({
                "ticker": item.ticker,
                "market": item.market,
                "sector": item.sector,
                "reason": item.reason,
                "overall_score": vs.overall_score,
                "signal": vs.signal,
                "reasoning": vs.reasoning,
                "strategy": vs.strategy,
            })
        except Exception as e:
            logger.warning(f"Error analizando watchlist {item.ticker}: {e}")

    return results


async def get_watchlist_summary() -> str:
    """Genera un resumen legible de la watchlist."""
    watchlist = await repo.get_active_watchlist()
    if not watchlist:
        return "📋 Watchlist vacía. Usa /watchlist_generate para crear una."

    lines = ["📋 *WATCHLIST ACTIVA*\n"]
    active_strategy = await _get_active_strategy()
    analyzer = get_strategy_analyzer(active_strategy)
    for i, item in enumerate(watchlist, 1):
        try:
            fd = await asyncio.to_thread(fetch_fundamentals, item.ticker, item.market)
            if fd is None or fd.current_price is None:
                lines.append(f"{i}. ⚠️ *${item.ticker}* ({item.market}) - Sin datos disponibles")
                continue
            vs = await asyncio.to_thread(analyzer, fd)
            emoji = "🟢" if vs.signal == "BUY" else "🔴" if vs.signal == "SELL" else "🟡"
            price_str = f"{fd.current_price:.2f}$" if fd.current_price is not None else "N/D"
            pe_str = f"{fd.pe_ratio:.1f}" if fd.pe_ratio is not None else "N/D"
            lines.append(
                f"{i}. {emoji} *${item.ticker}* ({item.market})\n"
                f"   Score: {vs.overall_score:.0f}/100 | Signal: {vs.signal} | Strat: {vs.strategy}\n"
                f"   Precio: {price_str} | P/E: {pe_str}"
            )
            # Mostrar objetivos de inversión si existen
            obj = await repo.get_investment_objective(item.ticker, market=item.market)
            if obj:
                if obj.thesis:
                    lines.append(f"   📝 Tesis: {obj.thesis[:100]}")
                targets = []
                if obj.target_entry_price:
                    targets.append(f"Entrada: {obj.target_entry_price:.2f}$")
                if obj.target_exit_price:
                    targets.append(f"Salida: {obj.target_exit_price:.2f}$")
                if targets:
                    lines.append(f"   🎯 {' | '.join(targets)}")
                if obj.conviction:
                    lines.append(f"   💪 Convicción: {obj.conviction}/10 | Horizonte: {obj.time_horizon or 'N/A'}")
                if obj.catalysts:
                    lines.append(f"   🚀 Catalizadores: {obj.catalysts[:80]}")
            else:
                lines.append(f"   Razón: {item.reason[:80] if item.reason else 'N/A'}")
        except Exception:
            lines.append(f"{i}. ⚠️ *${item.ticker}* - Error obteniendo datos")

    return "\n".join(lines)
