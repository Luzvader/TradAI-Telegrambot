"""
Analizador técnico determinista — genera diagnósticos técnicos
completos SIN usar la IA. El resultado se puede inyectar como
contexto pre-computado en los prompts del LLM, ahorrando tokens.

Indicadores utilizados:
  • RSI (sobrecompra/sobreventa)
  • MACD (momentum y cruces)
  • Bollinger Bands (volatilidad y posición)
  • ATR (rango y volatilidad implícita)
  • SMA 50/200 (golden/death cross, tendencia)
  • Soportes y resistencias (52w, medias)
"""

import logging
from dataclasses import dataclass, field

from data.technical import TechnicalIndicators

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TechnicalDiagnosis:
    """Resultado del diagnóstico técnico determinista."""
    ticker: str
    trend: str = "NEUTRAL"         # BULLISH / BEARISH / NEUTRAL
    momentum: str = "NEUTRAL"      # POSITIVO / NEGATIVO / NEUTRAL
    volatility: str = "NORMAL"     # ALTA / NORMAL / BAJA
    signal: str = "HOLD"           # BUY / SELL / HOLD
    confidence: int = 50           # 0-100
    support: float | None = None
    resistance: float | None = None
    bullets: list[str] = field(default_factory=list)
    summary: str = ""              # Resumen en una línea


def diagnose(
    ti: TechnicalIndicators,
    current_price: float | None = None,
    high_52w: float | None = None,
    low_52w: float | None = None,
    avg_50d: float | None = None,
    avg_200d: float | None = None,
) -> TechnicalDiagnosis:
    """
    Genera un diagnóstico técnico 100% determinista a partir de los
    indicadores ya calculados.  No necesita llamada a ninguna API.
    """
    d = TechnicalDiagnosis(ticker=ti.ticker)
    bullish = 0
    bearish = 0

    # ── RSI ──────────────────────────────────────────────────
    if ti.rsi is not None:
        if ti.rsi_oversold:
            bullish += 2
            d.bullets.append(f"📉 RSI en sobreventa ({ti.rsi:.0f}) — posible rebote")
        elif ti.rsi_overbought:
            bearish += 2
            d.bullets.append(f"📈 RSI en sobrecompra ({ti.rsi:.0f}) — posible corrección")
        elif ti.rsi > 55:
            bullish += 0.5
            d.bullets.append(f"RSI positivo ({ti.rsi:.0f})")
        elif ti.rsi < 45:
            bearish += 0.5
            d.bullets.append(f"RSI débil ({ti.rsi:.0f})")

    # ── MACD ─────────────────────────────────────────────────
    if ti.macd_histogram is not None:
        if ti.macd_bullish:
            bullish += 1.5
            d.bullets.append("MACD alcista (línea sobre señal)")
        else:
            bearish += 1.5
            d.bullets.append("MACD bajista (línea bajo señal)")

        if ti.macd_histogram > 0 and abs(ti.macd_histogram) > 0.5:
            bullish += 0.5
        elif ti.macd_histogram < 0 and abs(ti.macd_histogram) > 0.5:
            bearish += 0.5

    # ── Bollinger Bands ──────────────────────────────────────
    if ti.bb_position is not None:
        if ti.bb_position < 0.1:
            bullish += 1.5
            d.bullets.append(f"Precio en banda inferior de Bollinger ({ti.bb_position:.2f})")
        elif ti.bb_position > 0.9:
            bearish += 1.5
            d.bullets.append(f"Precio en banda superior de Bollinger ({ti.bb_position:.2f})")
        elif 0.4 <= ti.bb_position <= 0.6:
            d.bullets.append("Precio en zona media de Bollinger (neutral)")

    # ── Golden / Death cross ─────────────────────────────────
    if ti.golden_cross:
        bullish += 2
        d.bullets.append("🟢 Golden cross (SMA50 > SMA200)")
    elif ti.death_cross:
        bearish += 2
        d.bullets.append("🔴 Death cross (SMA50 < SMA200)")

    # ── Tendencia vs medias ──────────────────────────────────
    sma50 = ti.sma_50 or avg_50d
    sma200 = ti.sma_200 or avg_200d
    if current_price is not None:
        if sma50 and current_price > sma50:
            bullish += 0.5
        elif sma50 and current_price < sma50:
            bearish += 0.5
        if sma200 and current_price > sma200:
            bullish += 0.5
        elif sma200 and current_price < sma200:
            bearish += 0.5

    # ── Volatilidad (ATR) ────────────────────────────────────
    if ti.atr_pct is not None:
        if ti.atr_pct > 4.0:
            d.volatility = "ALTA"
            d.bullets.append(f"⚡ Volatilidad alta (ATR {ti.atr_pct:.1f}%)")
        elif ti.atr_pct < 1.5:
            d.volatility = "BAJA"
            d.bullets.append(f"Volatilidad baja (ATR {ti.atr_pct:.1f}%)")
        else:
            d.volatility = "NORMAL"

    # ── Soportes y resistencias ──────────────────────────────
    supports: list[float] = []
    resistances: list[float] = []

    if low_52w is not None:
        supports.append(low_52w)
    if ti.bb_lower is not None:
        supports.append(ti.bb_lower)
    if sma200 is not None:
        supports.append(sma200)

    if high_52w is not None:
        resistances.append(high_52w)
    if ti.bb_upper is not None:
        resistances.append(ti.bb_upper)
    if sma50 and sma200 and sma50 > sma200:
        resistances.append(sma50)

    if supports:
        valid_supports = [s for s in supports if current_price is None or s < current_price * 1.02]
        d.support = round(max(valid_supports), 2) if valid_supports else round(min(supports), 2)
    if resistances:
        valid_resistances = [r for r in resistances if current_price is None or r > current_price * 0.98]
        d.resistance = round(min(valid_resistances), 2) if valid_resistances else round(max(resistances), 2)

    # ── Distancia al rango 52 semanas ────────────────────────
    if current_price and high_52w and low_52w and high_52w > low_52w:
        range_52w = high_52w - low_52w
        pos = (current_price - low_52w) / range_52w
        if pos < 0.2:
            bullish += 1
            d.bullets.append(f"Cerca de mín. 52 sem ({pos:.0%} del rango)")
        elif pos > 0.9:
            bearish += 0.5
            d.bullets.append(f"Cerca de máx. 52 sem ({pos:.0%} del rango)")

    # ── Momentum ─────────────────────────────────────────────
    if bullish > bearish + 1:
        d.momentum = "POSITIVO"
    elif bearish > bullish + 1:
        d.momentum = "NEGATIVO"
    else:
        d.momentum = "NEUTRAL"

    # ── Trend ────────────────────────────────────────────────
    d.trend = ti.trend_signal  # ya calculado en TechnicalIndicators

    # ── Signal y confidence ──────────────────────────────────
    diff = bullish - bearish
    if diff >= 3:
        d.signal = "BUY"
        d.confidence = min(95, 60 + int(diff * 5))
    elif diff <= -3:
        d.signal = "SELL"
        d.confidence = min(95, 60 + int(abs(diff) * 5))
    else:
        d.signal = "HOLD"
        d.confidence = max(0, 50 - int(abs(diff) * 3))

    # ── Summary ──────────────────────────────────────────────
    parts = [f"Tendencia: {d.trend}", f"Momentum: {d.momentum}"]
    if d.support:
        parts.append(f"Soporte: {d.support}")
    if d.resistance:
        parts.append(f"Resistencia: {d.resistance}")
    parts.append(f"Señal: {d.signal} ({d.confidence}% conf.)")
    d.summary = " | ".join(parts)

    return d


def format_for_prompt(d: TechnicalDiagnosis) -> str:
    """
    Formatea el diagnóstico técnico como texto compacto para inyectar
    en el prompt del LLM.  Reemplaza lo que antes la IA tenía que
    deducir por sí misma.
    """
    lines = [
        f"ANÁLISIS TÉCNICO (determinista, {d.ticker}):",
        f"  Tendencia: {d.trend} | Momentum: {d.momentum} | Volatilidad: {d.volatility}",
        f"  Señal técnica: {d.signal} (confianza {d.confidence}%)",
    ]
    if d.support or d.resistance:
        sr = []
        if d.support:
            sr.append(f"Soporte: {d.support}$")
        if d.resistance:
            sr.append(f"Resistencia: {d.resistance}$")
        lines.append(f"  {' | '.join(sr)}")
    for b in d.bullets[:5]:
        lines.append(f"  • {b}")
    return "\n".join(lines)
