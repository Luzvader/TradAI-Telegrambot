"""
Funciones auxiliares para construir contexto determinista
y justificaciones estructuradas para señales.
"""

import logging
from typing import Any

from data.fundamentals import FundamentalData
from data.technical import get_technical_analysis
from strategy import technical_analyst, price_analyst

logger = logging.getLogger(__name__)


async def compute_deterministic_context(
    ticker: str,
    fd: FundamentalData,
    market: str | None = None,
) -> str:
    """
    Ejecuta los analizadores técnico y de precio de forma determinista
    y devuelve el texto formateado listo para inyectar en prompts IA.
    Ahorra tokens porque la IA no tiene que calcular esto ella misma.
    """
    parts: list[str] = []

    # Análisis técnico
    try:
        ti = await get_technical_analysis(ticker, market)
        if ti is not None:
            tech_diag = technical_analyst.diagnose(
                ti,
                current_price=fd.current_price,
                high_52w=fd.high_52w,
                low_52w=fd.low_52w,
                avg_50d=fd.avg_50d,
                avg_200d=fd.avg_200d,
            )
            parts.append(technical_analyst.format_for_prompt(tech_diag))
    except Exception as e:
        logger.debug(f"No se pudo obtener análisis técnico para {ticker}: {e}")

    # Análisis de precio / valoración
    try:
        price_diag = price_analyst.diagnose(fd)
        parts.append(price_analyst.format_for_prompt(price_diag))
    except Exception as e:
        logger.debug(f"No se pudo obtener análisis de precio para {ticker}: {e}")

    return "\n\n".join(parts)


def build_signal_justification(
    vs: Any,
    fd: Any = None,
    sl_tp: dict | None = None,
    ai_summary: str | None = None,
    tech_diag: Any | None = None,
    price_diag: Any | None = None,
) -> str:
    """
    Construye una justificación estructurada para una señal.
    Combina scoring cuantitativo, diagnósticos deterministas,
    fundamentales y análisis IA.
    """
    parts: list[str] = []

    # 1. Scores
    parts.append(
        f"📊 Score global: {vs.overall_score:.0f}/100 "
        f"(Value:{vs.value_score:.0f} Quality:{vs.quality_score:.0f} Safety:{vs.safety_score:.0f})"
    )

    # 2. Margen de seguridad
    if vs.margin_of_safety is not None:
        mos_emoji = "✅" if vs.margin_of_safety > 15 else "⚠️" if vs.margin_of_safety > 0 else "🔴"
        parts.append(f"{mos_emoji} Margen de seguridad: {vs.margin_of_safety:.1f}%")

    # 3. Diagnóstico técnico (determinista)
    if tech_diag is not None:
        parts.append(
            f"📉 Técnico: {tech_diag.trend} | Momentum: {tech_diag.momentum} | "
            f"Señal: {tech_diag.signal} ({tech_diag.confidence}%)"
        )

    # 4. Diagnóstico precio/valoración (determinista)
    if price_diag is not None:
        parts.append(
            f"💲 Valoración: {price_diag.valuation_signal} ({price_diag.confidence}%)"
            + (f" | Margen seg.: {price_diag.margin_of_safety:+.1f}%" if price_diag.margin_of_safety is not None else "")
        )

    # 5. Fundamentales clave (si disponibles)
    if fd is not None:
        fund_items = []
        if fd.pe_ratio is not None:
            fund_items.append(f"P/E:{fd.pe_ratio:.1f}")
        if fd.roe is not None:
            fund_items.append(f"ROE:{fd.roe*100:.1f}%")
        if fd.debt_to_equity is not None:
            fund_items.append(f"D/E:{fd.debt_to_equity:.0f}%")
        if fd.dividend_yield is not None:
            fund_items.append(f"Div:{fd.dividend_yield*100:.1f}%")
        if fd.revenue_growth is not None:
            fund_items.append(f"Rev.Growth:{fd.revenue_growth*100:.1f}%")
        if fund_items:
            parts.append(f"📈 Fundamentales: {' | '.join(fund_items)}")

    # 6. Stop-loss / take-profit (para posiciones existentes)
    if sl_tp:
        if sl_tp.get("stop_loss_hit"):
            parts.append(f"🔴 S/L alcanzado | PnL: {sl_tp['pnl_pct']:.1f}%")
        elif sl_tp.get("take_profit_hit"):
            parts.append(f"🟢 T/P alcanzado | PnL: {sl_tp['pnl_pct']:.1f}%")
        elif sl_tp.get("pnl_pct") is not None:
            parts.append(f"💰 PnL actual: {sl_tp['pnl_pct']:.1f}%")

    # 7. Reasoning de la estrategia
    if vs.reasoning:
        for r in vs.reasoning[:4]:
            parts.append(f"  • {r}")

    # 8. Resumen IA (si disponible)
    if ai_summary:
        # Tomar solo las primeras 200 chars del análisis IA
        short_ai = ai_summary[:200].strip()
        if len(ai_summary) > 200:
            short_ai += "…"
        parts.append(f"🧠 IA: {short_ai}")

    return "\n".join(parts)
