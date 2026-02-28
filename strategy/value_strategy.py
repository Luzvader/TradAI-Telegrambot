"""
Estrategia de Value Investing.
Calcula scores de valor, calidad y seguridad para cada acción.
Emula la filosofía de un fondo de inversión value.
"""

import logging

from data.fundamentals import FundamentalData, calculate_margin_of_safety
from strategy.score import StrategyScore

logger = logging.getLogger(__name__)


ValueScore = StrategyScore  # backwards compatible alias


def score_value(fd: FundamentalData) -> float:
    """
    Puntúa la valoración (¿está barata?).
    Factores: P/E, P/B, P/S, margen de seguridad.
    """
    score = 50.0  # Base neutral

    # P/E Ratio (cuanto menor, mejor para value)
    if fd.pe_ratio is not None:
        if fd.pe_ratio < 0:
            score -= 15  # Pérdidas
        elif fd.pe_ratio < 10:
            score += 20
        elif fd.pe_ratio < 15:
            score += 15
        elif fd.pe_ratio < 20:
            score += 5
        elif fd.pe_ratio < 30:
            score -= 5
        else:
            score -= 15

    # Forward P/E vs Trailing P/E (¿mejorando?)
    if fd.forward_pe is not None and fd.pe_ratio is not None:
        if fd.pe_ratio > 0 and fd.forward_pe > 0:
            if fd.forward_pe < fd.pe_ratio * 0.85:
                score += 10  # Beneficios creciendo
            elif fd.forward_pe > fd.pe_ratio * 1.15:
                score -= 5   # Beneficios decreciendo

    # P/B Ratio
    if fd.pb_ratio is not None:
        if fd.pb_ratio < 1.0:
            score += 15  # Cotiza por debajo de valor en libros
        elif fd.pb_ratio < 2.0:
            score += 8
        elif fd.pb_ratio < 3.0:
            score += 2
        elif fd.pb_ratio > 5.0:
            score -= 10

    # P/S Ratio
    if fd.ps_ratio is not None:
        if fd.ps_ratio < 1.0:
            score += 10
        elif fd.ps_ratio < 2.0:
            score += 5
        elif fd.ps_ratio > 8.0:
            score -= 10

    # Dividendo
    if fd.dividend_yield is not None and fd.dividend_yield > 0:
        if fd.dividend_yield > 0.05:
            score += 10
        elif fd.dividend_yield > 0.03:
            score += 7
        elif fd.dividend_yield > 0.01:
            score += 3

    # Distancia al mínimo de 52 semanas (oportunidad value)
    if fd.current_price and fd.low_52w and fd.high_52w:
        range_52w = fd.high_52w - fd.low_52w
        if range_52w > 0:
            position = (fd.current_price - fd.low_52w) / range_52w
            if position < 0.3:
                score += 10  # Cerca del mínimo
            elif position > 0.9:
                score -= 8   # Cerca del máximo

    return max(0, min(100, score))


def score_quality(fd: FundamentalData) -> float:
    """
    Puntúa la calidad del negocio.
    Factores: ROE, márgenes, crecimiento, flujo de caja libre.
    """
    score = 50.0

    # ROE (Return on Equity)
    if fd.roe is not None:
        if fd.roe > 0.25:
            score += 20
        elif fd.roe > 0.15:
            score += 12
        elif fd.roe > 0.10:
            score += 5
        elif fd.roe < 0:
            score -= 15

    # ROA (Return on Assets)
    if fd.roa is not None:
        if fd.roa > 0.10:
            score += 10
        elif fd.roa > 0.05:
            score += 5
        elif fd.roa < 0:
            score -= 10

    # Márgenes de beneficio
    if fd.profit_margins is not None:
        if fd.profit_margins > 0.20:
            score += 12
        elif fd.profit_margins > 0.10:
            score += 6
        elif fd.profit_margins < 0:
            score -= 12

    # Márgenes operativos
    if fd.operating_margins is not None:
        if fd.operating_margins > 0.25:
            score += 8
        elif fd.operating_margins > 0.15:
            score += 4
        elif fd.operating_margins < 0.05:
            score -= 5

    # Crecimiento de ingresos
    if fd.revenue_growth is not None:
        if fd.revenue_growth > 0.20:
            score += 10
        elif fd.revenue_growth > 0.10:
            score += 5
        elif fd.revenue_growth < 0:
            score -= 8

    # Crecimiento de beneficios
    if fd.earnings_growth is not None:
        if fd.earnings_growth > 0.20:
            score += 8
        elif fd.earnings_growth > 0.05:
            score += 4
        elif fd.earnings_growth < -0.10:
            score -= 10

    # Free Cash Flow positivo
    if fd.free_cash_flow is not None:
        if fd.free_cash_flow > 0:
            score += 8
        else:
            score -= 10

    return max(0, min(100, score))


def score_safety(fd: FundamentalData) -> float:
    """
    Puntúa la seguridad de la inversión.
    Factores: deuda, beta, volatilidad, consenso analistas.
    """
    score = 50.0

    # Deuda / Equity
    if fd.debt_to_equity is not None:
        if fd.debt_to_equity < 30:
            score += 15  # Baja deuda
        elif fd.debt_to_equity < 80:
            score += 8
        elif fd.debt_to_equity < 150:
            score -= 5
        else:
            score -= 15  # Alta deuda

    # Beta (volatilidad)
    if fd.beta is not None:
        if 0.5 <= fd.beta <= 1.0:
            score += 10  # Baja volatilidad
        elif 1.0 < fd.beta <= 1.3:
            score += 3
        elif fd.beta > 1.5:
            score -= 10  # Alta volatilidad
        elif fd.beta < 0.3:
            score += 5   # Muy defensivo

    # Market cap (preferimos large caps por seguridad)
    if fd.market_cap is not None:
        if fd.market_cap > 100e9:       # > $100B
            score += 10
        elif fd.market_cap > 10e9:      # > $10B
            score += 5
        elif fd.market_cap < 1e9:       # < $1B
            score -= 10                  # Small cap, más riesgo

    # Media 200 días vs precio actual (tendencia)
    if fd.current_price and fd.avg_200d:
        if fd.current_price > fd.avg_200d:
            score += 5   # Por encima de media, tendencia alcista
        else:
            score -= 3   # Por debajo, posible debilidad

    # Recomendación de analistas
    if fd.recommendation:
        rec = fd.recommendation.lower()
        if rec in ("strong_buy", "buy"):
            score += 8
        elif rec == "hold":
            score += 0
        elif rec in ("sell", "strong_sell"):
            score -= 10

    return max(0, min(100, score))


def analyze_value(fd: FundamentalData) -> ValueScore:
    """Ejecuta el análisis value completo de una acción."""
    v_score = score_value(fd)
    q_score = score_quality(fd)
    s_score = score_safety(fd)

    # Overall: media ponderada (Value 40%, Quality 35%, Safety 25%)
    overall = v_score * 0.40 + q_score * 0.35 + s_score * 0.25
    mos = calculate_margin_of_safety(fd)

    # Generar razonamiento
    reasoning = _build_reasoning(fd, v_score, q_score, s_score, mos)

    result = ValueScore(
        ticker=fd.ticker,
        strategy="value",
        value_score=round(v_score, 1),
        quality_score=round(q_score, 1),
        safety_score=round(s_score, 1),
        overall_score=round(overall, 1),
        margin_of_safety=mos,
        reasoning=reasoning,
    )

    logger.info(
        f"📊 {fd.ticker}: Value={v_score:.0f} Quality={q_score:.0f} "
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
    """Genera explicaciones legibles del análisis."""
    reasons = []

    if v_score >= 65:
        reasons.append(f"✅ Valoración atractiva (score {v_score:.0f}/100)")
    elif v_score <= 35:
        reasons.append(f"⚠️ Valoración cara (score {v_score:.0f}/100)")

    if q_score >= 65:
        reasons.append(f"✅ Negocio de alta calidad (score {q_score:.0f}/100)")
    elif q_score <= 35:
        reasons.append(f"⚠️ Calidad del negocio baja (score {q_score:.0f}/100)")

    if s_score >= 65:
        reasons.append(f"✅ Perfil de riesgo bajo (score {s_score:.0f}/100)")
    elif s_score <= 35:
        reasons.append(f"⚠️ Perfil de riesgo elevado (score {s_score:.0f}/100)")

    if fd.pe_ratio is not None:
        reasons.append(f"P/E: {fd.pe_ratio:.1f}")
    if fd.roe is not None:
        reasons.append(f"ROE: {fd.roe*100:.1f}%")
    if fd.debt_to_equity is not None:
        reasons.append(f"Deuda/Equity: {fd.debt_to_equity:.0f}%")
    if mos is not None:
        reasons.append(f"Margen de seguridad: {mos:.1f}%")

    return reasons
