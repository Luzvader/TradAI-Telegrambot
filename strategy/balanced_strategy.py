"""
Estrategia Balanced.

Objetivo: combinar lo mejor de Value + Growth con un perfil de riesgo
equilibrado.
"""

from __future__ import annotations

import logging

from data.fundamentals import FundamentalData, calculate_margin_of_safety
from strategy.growth_strategy import score_growth_quality, score_growth_value, score_growth_safety
from strategy.score import StrategyScore
from strategy.utils import clamp as _clamp
from strategy.value_strategy import score_quality, score_safety, score_value

logger = logging.getLogger(__name__)


def analyze_balanced(fd: FundamentalData) -> StrategyScore:
    """Ejecuta el análisis balanced completo de una acción."""
    # Mezcla de value y growth: promediamos sub-scores para evitar sesgos.
    v_value = score_value(fd)
    v_growth = score_growth_value(fd)
    v_score = _clamp(v_value * 0.60 + v_growth * 0.40)

    q_value = score_quality(fd)
    q_growth = score_growth_quality(fd)
    q_score = _clamp(q_value * 0.55 + q_growth * 0.45)

    s_value = score_safety(fd)
    s_growth = score_growth_safety(fd)
    s_score = _clamp(s_value * 0.70 + s_growth * 0.30)

    # Overall: equilibrio entre valoración y crecimiento
    overall = v_score * 0.35 + q_score * 0.40 + s_score * 0.25
    mos = calculate_margin_of_safety(fd)

    reasoning = _build_reasoning(fd, v_score, q_score, s_score, mos)

    result = StrategyScore(
        ticker=fd.ticker,
        strategy="balanced",
        value_score=round(v_score, 1),
        quality_score=round(q_score, 1),
        safety_score=round(s_score, 1),
        overall_score=round(overall, 1),
        margin_of_safety=mos,
        reasoning=reasoning,
    )

    logger.info(
        f"⚖️ {fd.ticker}: Balanced Value={v_score:.0f} Quality={q_score:.0f} "
        f"Safety={s_score:.0f} → Overall={overall:.0f} ({result.signal})"
    )
    return result


def _build_reasoning(
    fd: FundamentalData,
    v_score: float,
    q_score: float,
    s_score: float,
    mos: float | None,
) -> list[str]:
    reasons: list[str] = ["⚖️ Estrategia equilibrada (value + growth)"]

    if v_score >= 65:
        reasons.append(f"✅ Valoración atractiva (score {v_score:.0f}/100)")
    elif v_score <= 35:
        reasons.append(f"⚠️ Valoración cara (score {v_score:.0f}/100)")

    if q_score >= 65:
        reasons.append(f"✅ Calidad/crecimiento sólidos (score {q_score:.0f}/100)")
    elif q_score <= 35:
        reasons.append(f"⚠️ Calidad/crecimiento débiles (score {q_score:.0f}/100)")

    if s_score >= 65:
        reasons.append(f"✅ Riesgo bajo/moderado (score {s_score:.0f}/100)")
    elif s_score <= 35:
        reasons.append(f"⚠️ Riesgo elevado (score {s_score:.0f}/100)")

    if fd.pe_ratio is not None:
        reasons.append(f"P/E: {fd.pe_ratio:.1f}")
    if fd.revenue_growth is not None:
        reasons.append(f"Revenue growth: {fd.revenue_growth*100:.1f}%")
    if fd.debt_to_equity is not None:
        reasons.append(f"Deuda/Equity: {fd.debt_to_equity:.0f}%")
    if mos is not None:
        reasons.append(f"Margen de seguridad (consenso): {mos:.1f}%")

    return reasons

