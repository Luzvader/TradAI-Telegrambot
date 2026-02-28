"""
Estrategia Conservative (defensiva).

Objetivo: priorizar estabilidad, baja volatilidad y balance sólido.
Suele penalizar compañías pequeñas, muy endeudadas o con beta alta.
"""

from __future__ import annotations

import logging

from data.fundamentals import FundamentalData, calculate_margin_of_safety
from strategy.score import StrategyScore
from strategy.utils import clamp as _clamp

logger = logging.getLogger(__name__)


def score_conservative_safety(fd: FundamentalData) -> float:
    """Puntúa seguridad con criterios más estrictos."""
    score = 50.0

    if fd.beta is not None:
        if 0.3 <= fd.beta <= 1.0:
            score += 20
        elif 1.0 < fd.beta <= 1.3:
            score += 8
        elif 1.3 < fd.beta <= 1.6:
            score -= 6
        else:
            score -= 16

    if fd.debt_to_equity is not None:
        if fd.debt_to_equity < 30:
            score += 18
        elif fd.debt_to_equity < 70:
            score += 8
        elif fd.debt_to_equity < 120:
            score -= 6
        else:
            score -= 18

    if fd.market_cap is not None:
        if fd.market_cap > 200e9:
            score += 12
        elif fd.market_cap > 50e9:
            score += 8
        elif fd.market_cap > 10e9:
            score += 4
        elif fd.market_cap < 2e9:
            score -= 14

    # Tendencia: preferimos no estar muy por debajo de la media 200d
    if fd.current_price and fd.avg_200d:
        score += 4 if fd.current_price >= fd.avg_200d else -8

    return _clamp(score)


def score_conservative_quality(fd: FundamentalData) -> float:
    """Puntúa calidad defensiva: márgenes y FCF."""
    score = 50.0

    if fd.free_cash_flow is not None:
        score += 12 if fd.free_cash_flow > 0 else -18

    if fd.profit_margins is not None:
        if fd.profit_margins > 0.15:
            score += 10
        elif fd.profit_margins > 0.08:
            score += 4
        elif fd.profit_margins < 0:
            score -= 14

    if fd.operating_margins is not None:
        if fd.operating_margins > 0.15:
            score += 6
        elif fd.operating_margins < 0.05:
            score -= 10

    if fd.roe is not None:
        if fd.roe > 0.18:
            score += 8
        elif fd.roe > 0.10:
            score += 4
        elif fd.roe < 0:
            score -= 12

    # Penalizar crecimiento negativo pronunciado
    if fd.revenue_growth is not None and fd.revenue_growth < -0.05:
        score -= 10
    if fd.earnings_growth is not None and fd.earnings_growth < -0.10:
        score -= 10

    return _clamp(score)


def score_conservative_value(fd: FundamentalData) -> float:
    """Evita pagar demasiado: múltiplos moderados."""
    score = 50.0

    if fd.pe_ratio is not None:
        if fd.pe_ratio < 0:
            score -= 18
        elif fd.pe_ratio < 12:
            score += 14
        elif fd.pe_ratio < 18:
            score += 10
        elif fd.pe_ratio < 25:
            score += 2
        elif fd.pe_ratio < 35:
            score -= 8
        else:
            score -= 16

    if fd.pb_ratio is not None:
        if fd.pb_ratio < 1.2:
            score += 8
        elif fd.pb_ratio < 2.5:
            score += 4
        elif fd.pb_ratio > 5.0:
            score -= 10

    mos = calculate_margin_of_safety(fd)
    if mos is not None:
        if mos > 15:
            score += 6
        elif mos < -10:
            score -= 6

    return _clamp(score)


def analyze_conservative(fd: FundamentalData) -> StrategyScore:
    """Ejecuta el análisis conservative completo de una acción."""
    v_score = score_conservative_value(fd)
    q_score = score_conservative_quality(fd)
    s_score = score_conservative_safety(fd)

    # Overall: la seguridad pesa más
    overall = v_score * 0.20 + q_score * 0.30 + s_score * 0.50
    mos = calculate_margin_of_safety(fd)

    reasoning = _build_reasoning(fd, v_score, q_score, s_score, mos)

    result = StrategyScore(
        ticker=fd.ticker,
        strategy="conservative",
        value_score=round(v_score, 1),
        quality_score=round(q_score, 1),
        safety_score=round(s_score, 1),
        overall_score=round(overall, 1),
        margin_of_safety=mos,
        reasoning=reasoning,
    )

    logger.info(
        f"🛡️ {fd.ticker}: Conservative Value={v_score:.0f} Quality={q_score:.0f} "
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
    reasons: list[str] = ["🛡️ Estrategia defensiva (conservative)"]

    if s_score >= 70:
        reasons.append(f"✅ Perfil muy defensivo (score {s_score:.0f}/100)")
    elif s_score <= 40:
        reasons.append(f"⚠️ Volatilidad/riesgo alto (score {s_score:.0f}/100)")

    if q_score >= 65:
        reasons.append(f"✅ Negocio estable (score {q_score:.0f}/100)")
    elif q_score <= 35:
        reasons.append(f"⚠️ Calidad/FCF débiles (score {q_score:.0f}/100)")

    if v_score >= 65:
        reasons.append(f"✅ Precio razonable (score {v_score:.0f}/100)")
    elif v_score <= 35:
        reasons.append(f"⚠️ Precio exigente (score {v_score:.0f}/100)")

    if fd.beta is not None:
        reasons.append(f"Beta: {fd.beta:.2f}")
    if fd.debt_to_equity is not None:
        reasons.append(f"Deuda/Equity: {fd.debt_to_equity:.0f}%")
    if fd.market_cap is not None:
        reasons.append(f"Market cap: {fd.market_cap/1e9:.0f}B$")
    if mos is not None:
        reasons.append(f"Margen de seguridad (consenso): {mos:.1f}%")

    return reasons

