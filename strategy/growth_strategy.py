"""
Estrategia Growth (crecimiento).

Objetivo: priorizar empresas con crecimiento fuerte y rentable,
manteniendo una valoración "razonable" y un perfil de riesgo aceptable.
"""

from __future__ import annotations

import logging

from data.fundamentals import FundamentalData, calculate_margin_of_safety
from strategy.score import StrategyScore
from strategy.utils import clamp as _clamp

logger = logging.getLogger(__name__)


def score_growth_value(fd: FundamentalData) -> float:
    """
    Puntúa la valoración desde una óptica growth.
    Acepta múltiplos más altos que value, pero penaliza extremos.
    """
    score = 50.0

    # Forward P/E (más relevante en growth)
    if fd.forward_pe is not None:
        if fd.forward_pe < 0:
            score -= 20
        elif fd.forward_pe < 15:
            score += 15
        elif fd.forward_pe < 25:
            score += 10
        elif fd.forward_pe < 35:
            score += 2
        elif fd.forward_pe < 50:
            score -= 8
        else:
            score -= 18
    elif fd.pe_ratio is not None:
        # Fallback a trailing P/E
        if fd.pe_ratio < 0:
            score -= 20
        elif fd.pe_ratio < 20:
            score += 10
        elif fd.pe_ratio < 35:
            score += 2
        elif fd.pe_ratio < 60:
            score -= 8
        else:
            score -= 18

    # P/S como proxy de valoración en growth
    if fd.ps_ratio is not None:
        if fd.ps_ratio < 2.0:
            score += 10
        elif fd.ps_ratio < 5.0:
            score += 5
        elif fd.ps_ratio < 10.0:
            score -= 5
        else:
            score -= 12

    # Tendencia (growth suele funcionar mejor con momentum)
    if fd.current_price and fd.avg_200d:
        score += 5 if fd.current_price > fd.avg_200d else -5

    return _clamp(score)


def score_growth_quality(fd: FundamentalData) -> float:
    """Puntúa crecimiento + calidad: revenue/earnings growth, márgenes, ROE, FCF."""
    score = 50.0

    # Crecimiento de ingresos
    if fd.revenue_growth is not None:
        if fd.revenue_growth > 0.40:
            score += 22
        elif fd.revenue_growth > 0.25:
            score += 16
        elif fd.revenue_growth > 0.15:
            score += 10
        elif fd.revenue_growth > 0.05:
            score += 4
        elif fd.revenue_growth < 0:
            score -= 16

    # Crecimiento de beneficios
    if fd.earnings_growth is not None:
        if fd.earnings_growth > 0.40:
            score += 22
        elif fd.earnings_growth > 0.25:
            score += 16
        elif fd.earnings_growth > 0.15:
            score += 10
        elif fd.earnings_growth > 0.05:
            score += 4
        elif fd.earnings_growth < -0.10:
            score -= 18

    # Márgenes
    if fd.operating_margins is not None:
        if fd.operating_margins > 0.25:
            score += 10
        elif fd.operating_margins > 0.15:
            score += 6
        elif fd.operating_margins < 0.05:
            score -= 10

    if fd.profit_margins is not None:
        if fd.profit_margins > 0.20:
            score += 8
        elif fd.profit_margins > 0.10:
            score += 4
        elif fd.profit_margins < 0:
            score -= 12

    # ROE
    if fd.roe is not None:
        if fd.roe > 0.25:
            score += 10
        elif fd.roe > 0.15:
            score += 6
        elif fd.roe < 0:
            score -= 12

    # FCF (en growth puede ser negativo, pero lo premiamos si es positivo)
    if fd.free_cash_flow is not None:
        score += 6 if fd.free_cash_flow > 0 else -6

    return _clamp(score)


def score_growth_safety(fd: FundamentalData) -> float:
    """Puntúa el riesgo: deuda, beta, market cap."""
    score = 50.0

    if fd.debt_to_equity is not None:
        if fd.debt_to_equity < 50:
            score += 10
        elif fd.debt_to_equity < 120:
            score += 4
        elif fd.debt_to_equity < 200:
            score -= 6
        else:
            score -= 16

    if fd.beta is not None:
        if 0.8 <= fd.beta <= 1.3:
            score += 6
        elif 1.3 < fd.beta <= 1.8:
            score -= 4
        elif fd.beta > 2.0:
            score -= 12
        elif fd.beta < 0.6:
            score += 4

    if fd.market_cap is not None:
        if fd.market_cap > 100e9:
            score += 6
        elif fd.market_cap > 10e9:
            score += 3
        elif fd.market_cap < 1e9:
            score -= 10

    return _clamp(score)


def analyze_growth(fd: FundamentalData) -> StrategyScore:
    """Ejecuta el análisis growth completo de una acción."""
    v_score = score_growth_value(fd)
    q_score = score_growth_quality(fd)
    s_score = score_growth_safety(fd)

    # Overall: Growth prioriza calidad/crecimiento
    overall = v_score * 0.25 + q_score * 0.50 + s_score * 0.25
    mos = calculate_margin_of_safety(fd)

    reasoning = _build_reasoning(fd, v_score, q_score, s_score, mos)

    result = StrategyScore(
        ticker=fd.ticker,
        strategy="growth",
        value_score=round(v_score, 1),
        quality_score=round(q_score, 1),
        safety_score=round(s_score, 1),
        overall_score=round(overall, 1),
        margin_of_safety=mos,
        reasoning=reasoning,
    )

    logger.info(
        f"📈 {fd.ticker}: Growth Value={v_score:.0f} Quality={q_score:.0f} "
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
    reasons: list[str] = []

    if q_score >= 65:
        reasons.append(f"✅ Crecimiento/Calidad fuerte (score {q_score:.0f}/100)")
    elif q_score <= 35:
        reasons.append(f"⚠️ Crecimiento débil (score {q_score:.0f}/100)")

    if v_score >= 65:
        reasons.append(f"✅ Valoración razonable para growth (score {v_score:.0f}/100)")
    elif v_score <= 35:
        reasons.append(f"⚠️ Valoración exigente (score {v_score:.0f}/100)")

    if s_score >= 65:
        reasons.append(f"✅ Riesgo moderado/bajo (score {s_score:.0f}/100)")
    elif s_score <= 35:
        reasons.append(f"⚠️ Riesgo elevado (score {s_score:.0f}/100)")

    if fd.revenue_growth is not None:
        reasons.append(f"Revenue growth: {fd.revenue_growth*100:.1f}%")
    if fd.earnings_growth is not None:
        reasons.append(f"Earnings growth: {fd.earnings_growth*100:.1f}%")
    if fd.forward_pe is not None:
        reasons.append(f"Forward P/E: {fd.forward_pe:.1f}")
    elif fd.pe_ratio is not None:
        reasons.append(f"P/E: {fd.pe_ratio:.1f}")
    if fd.operating_margins is not None:
        reasons.append(f"Operating margin: {fd.operating_margins*100:.1f}%")
    if fd.debt_to_equity is not None:
        reasons.append(f"Deuda/Equity: {fd.debt_to_equity:.0f}%")
    if mos is not None:
        reasons.append(f"Margen de seguridad (consenso): {mos:.1f}%")

    return reasons

