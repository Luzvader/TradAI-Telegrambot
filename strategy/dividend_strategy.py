"""
Estrategia Dividend / Income.

Objetivo: priorizar dividend yield atractivo y sostenible con estabilidad
financiera (deuda baja, beta baja, cash flow positivo).
"""

from __future__ import annotations

import logging

from data.fundamentals import FundamentalData, calculate_margin_of_safety
from strategy.score import StrategyScore
from strategy.utils import clamp as _clamp

logger = logging.getLogger(__name__)


def score_dividend_value(fd: FundamentalData) -> float:
    """Puntúa yield + valoración razonable."""
    score = 50.0

    if fd.dividend_yield is not None:
        if fd.dividend_yield >= 0.06:
            score += 25
        elif fd.dividend_yield >= 0.04:
            score += 18
        elif fd.dividend_yield >= 0.03:
            score += 12
        elif fd.dividend_yield >= 0.02:
            score += 6
        elif fd.dividend_yield > 0:
            score += 2
    else:
        score -= 8  # sin datos de yield = menos atractivo para income

    # Evitar múltiplos extremos
    if fd.pe_ratio is not None:
        if fd.pe_ratio < 0:
            score -= 15
        elif fd.pe_ratio < 10:
            score += 6
        elif fd.pe_ratio < 18:
            score += 10
        elif fd.pe_ratio < 25:
            score += 2
        elif fd.pe_ratio < 35:
            score -= 6
        else:
            score -= 14

    if fd.pb_ratio is not None:
        if fd.pb_ratio < 1.5:
            score += 6
        elif fd.pb_ratio < 3.0:
            score += 2
        elif fd.pb_ratio > 6.0:
            score -= 8

    mos = calculate_margin_of_safety(fd)
    if mos is not None:
        if mos > 20:
            score += 8
        elif mos < -10:
            score -= 8

    return _clamp(score)


def score_dividend_quality(fd: FundamentalData) -> float:
    """Puntúa sostenibilidad: márgenes, ROE y FCF."""
    score = 50.0

    if fd.free_cash_flow is not None:
        if fd.free_cash_flow > 0:
            score += 12
        else:
            score -= 18

    if fd.profit_margins is not None:
        if fd.profit_margins > 0.20:
            score += 10
        elif fd.profit_margins > 0.10:
            score += 6
        elif fd.profit_margins < 0:
            score -= 12

    if fd.operating_margins is not None:
        if fd.operating_margins > 0.20:
            score += 6
        elif fd.operating_margins < 0.05:
            score -= 8

    if fd.roe is not None:
        if fd.roe > 0.20:
            score += 8
        elif fd.roe > 0.12:
            score += 4
        elif fd.roe < 0:
            score -= 12

    # Crecimiento negativo sostenido suele amenazar dividendos
    if fd.revenue_growth is not None and fd.revenue_growth < 0:
        score -= 8

    return _clamp(score)


def score_dividend_safety(fd: FundamentalData) -> float:
    """Puntúa estabilidad: deuda, beta, market cap."""
    score = 50.0

    if fd.debt_to_equity is not None:
        if fd.debt_to_equity < 40:
            score += 16
        elif fd.debt_to_equity < 80:
            score += 8
        elif fd.debt_to_equity < 150:
            score -= 8
        else:
            score -= 18

    if fd.beta is not None:
        if 0.4 <= fd.beta <= 1.0:
            score += 14
        elif 1.0 < fd.beta <= 1.3:
            score += 6
        elif fd.beta > 1.6:
            score -= 12
        elif fd.beta < 0.3:
            score += 8

    if fd.market_cap is not None:
        if fd.market_cap > 100e9:
            score += 8
        elif fd.market_cap > 10e9:
            score += 4
        elif fd.market_cap < 1e9:
            score -= 12

    return _clamp(score)


def analyze_dividend(fd: FundamentalData) -> StrategyScore:
    """Ejecuta el análisis dividend completo de una acción."""
    v_score = score_dividend_value(fd)
    q_score = score_dividend_quality(fd)
    s_score = score_dividend_safety(fd)

    # Overall: en dividend prioriza seguridad/estabilidad
    overall = v_score * 0.30 + q_score * 0.30 + s_score * 0.40
    mos = calculate_margin_of_safety(fd)

    reasoning = _build_reasoning(fd, v_score, q_score, s_score, mos)

    result = StrategyScore(
        ticker=fd.ticker,
        strategy="dividend",
        value_score=round(v_score, 1),
        quality_score=round(q_score, 1),
        safety_score=round(s_score, 1),
        overall_score=round(overall, 1),
        margin_of_safety=mos,
        reasoning=reasoning,
    )

    logger.info(
        f"💸 {fd.ticker}: Dividend Value={v_score:.0f} Quality={q_score:.0f} "
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

    if fd.dividend_yield is not None:
        reasons.append(f"Dividend yield: {fd.dividend_yield*100:.2f}%")

    if s_score >= 65:
        reasons.append(f"✅ Estabilidad alta (score {s_score:.0f}/100)")
    elif s_score <= 35:
        reasons.append(f"⚠️ Estabilidad baja (score {s_score:.0f}/100)")

    if q_score >= 65:
        reasons.append(f"✅ Dividendos sostenibles (score {q_score:.0f}/100)")
    elif q_score <= 35:
        reasons.append(f"⚠️ Calidad/FCF débiles (score {q_score:.0f}/100)")

    if fd.debt_to_equity is not None:
        reasons.append(f"Deuda/Equity: {fd.debt_to_equity:.0f}%")
    if fd.beta is not None:
        reasons.append(f"Beta: {fd.beta:.2f}")
    if fd.pe_ratio is not None:
        reasons.append(f"P/E: {fd.pe_ratio:.1f}")
    if mos is not None:
        reasons.append(f"Margen de seguridad (consenso): {mos:.1f}%")

    return reasons

