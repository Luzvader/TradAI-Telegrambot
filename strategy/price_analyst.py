"""
Analizador de precio y valoración determinista — genera diagnósticos
de valoración SIN usar la IA.  El resultado se inyecta como contexto
pre-computado en los prompts del LLM.

Análisis incluidos:
  • Posición en rango de 52 semanas
  • Distancia a medias móviles (50d / 200d)
  • Margen de seguridad vs target de consenso
  • Valoración relativa (P/E, P/B, P/S)
  • Estimación de precio justo simplificada
"""

import logging
from dataclasses import dataclass, field

from data.fundamentals import FundamentalData

logger = logging.getLogger(__name__)

# ── Benchmarks sectoriales por defecto (P/E medio) ──────────────
_SECTOR_PE: dict[str, float] = {
    "Technology": 28,
    "Communication Services": 22,
    "Consumer Cyclical": 20,
    "Consumer Defensive": 22,
    "Healthcare": 24,
    "Financial Services": 14,
    "Industrials": 20,
    "Energy": 12,
    "Utilities": 18,
    "Real Estate": 35,
    "Basic Materials": 15,
}
_DEFAULT_PE = 20.0


@dataclass(slots=True)
class PriceDiagnosis:
    """Resultado del diagnóstico de precio y valoración."""
    ticker: str
    current_price: float | None = None

    # Rango 52w
    high_52w: float | None = None
    low_52w: float | None = None
    range_position: float | None = None     # 0.0 (mín) – 1.0 (máx)

    # Medias móviles
    avg_50d: float | None = None
    avg_200d: float | None = None
    pct_vs_50d: float | None = None         # % sobre/bajo SMA50
    pct_vs_200d: float | None = None        # % sobre/bajo SMA200

    # Valoración
    pe_ratio: float | None = None
    forward_pe: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    pe_sector_avg: float | None = None      # referencia sectorial
    pe_discount_pct: float | None = None    # % descuento vs sector

    # Target y margen de seguridad
    target_price: float | None = None
    margin_of_safety: float | None = None   # % upside al target
    recommendation: str | None = None

    # Estimación de precio justo simplificada
    fair_value_pe: float | None = None      # precio si cotizara al P/E sector
    fair_value_consensus: float | None = None

    # Señal
    valuation_signal: str = "NEUTRAL"       # UNDERVALUED / OVERVALUED / NEUTRAL
    confidence: int = 50
    bullets: list[str] = field(default_factory=list)
    summary: str = ""


def diagnose(fd: FundamentalData) -> PriceDiagnosis:
    """
    Genera un diagnóstico de precio/valoración 100% determinista
    a partir de FundamentalData.
    """
    d = PriceDiagnosis(
        ticker=fd.ticker,
        current_price=fd.current_price,
        high_52w=fd.high_52w,
        low_52w=fd.low_52w,
        avg_50d=fd.avg_50d,
        avg_200d=fd.avg_200d,
        pe_ratio=fd.pe_ratio,
        forward_pe=fd.forward_pe,
        pb_ratio=fd.pb_ratio,
        ps_ratio=fd.ps_ratio,
        target_price=fd.target_price,
        recommendation=fd.recommendation,
    )

    undervalued = 0.0
    overvalued = 0.0
    price = fd.current_price

    # ── Posición en rango 52 semanas ─────────────────────────
    if price and fd.high_52w and fd.low_52w and fd.high_52w > fd.low_52w:
        rng = fd.high_52w - fd.low_52w
        d.range_position = round((price - fd.low_52w) / rng, 3)
        if d.range_position < 0.2:
            undervalued += 1.5
            d.bullets.append(f"📉 Cerca mín. 52 sem ({d.range_position:.0%} del rango)")
        elif d.range_position > 0.85:
            overvalued += 0.5
            d.bullets.append(f"📈 Cerca máx. 52 sem ({d.range_position:.0%} del rango)")

    # ── Distancia a medias móviles ───────────────────────────
    if price and fd.avg_50d:
        d.pct_vs_50d = round((price - fd.avg_50d) / fd.avg_50d * 100, 2)
        if d.pct_vs_50d < -5:
            undervalued += 0.5
            d.bullets.append(f"Precio {d.pct_vs_50d:+.1f}% vs SMA50")
        elif d.pct_vs_50d > 10:
            overvalued += 0.5
            d.bullets.append(f"Precio {d.pct_vs_50d:+.1f}% vs SMA50")

    if price and fd.avg_200d:
        d.pct_vs_200d = round((price - fd.avg_200d) / fd.avg_200d * 100, 2)
        if d.pct_vs_200d < -10:
            undervalued += 1
            d.bullets.append(f"Precio {d.pct_vs_200d:+.1f}% vs SMA200")
        elif d.pct_vs_200d > 15:
            overvalued += 0.5

    # ── Valoración relativa (P/E vs sector) ──────────────────
    sector = fd.sector if fd.sector and fd.sector != "N/A" else None
    d.pe_sector_avg = _SECTOR_PE.get(sector, _DEFAULT_PE) if sector else _DEFAULT_PE

    effective_pe = fd.forward_pe or fd.pe_ratio
    if effective_pe and effective_pe > 0 and d.pe_sector_avg:
        d.pe_discount_pct = round((d.pe_sector_avg - effective_pe) / d.pe_sector_avg * 100, 1)
        if d.pe_discount_pct > 20:
            undervalued += 1.5
            d.bullets.append(f"P/E ({effective_pe:.1f}) con {d.pe_discount_pct:.0f}% dcto. vs sector ({d.pe_sector_avg:.0f})")
        elif d.pe_discount_pct < -30:
            overvalued += 1
            d.bullets.append(f"P/E ({effective_pe:.1f}) con {abs(d.pe_discount_pct):.0f}% prima vs sector ({d.pe_sector_avg:.0f})")
        else:
            d.bullets.append(f"P/E ({effective_pe:.1f}) en línea con sector ({d.pe_sector_avg:.0f})")

    # ── P/B y P/S ────────────────────────────────────────────
    if fd.pb_ratio is not None:
        if fd.pb_ratio < 1.0:
            undervalued += 1
            d.bullets.append(f"P/B bajo ({fd.pb_ratio:.2f})")
        elif fd.pb_ratio > 5.0:
            overvalued += 0.5

    if fd.ps_ratio is not None:
        if fd.ps_ratio < 1.5:
            undervalued += 0.5
        elif fd.ps_ratio > 10:
            overvalued += 0.5

    # ── Margen de seguridad vs consenso ──────────────────────
    if price and fd.target_price and fd.target_price > 0:
        d.margin_of_safety = round((fd.target_price - price) / fd.target_price * 100, 2)
        d.fair_value_consensus = fd.target_price
        if d.margin_of_safety > 20:
            undervalued += 2
            d.bullets.append(f"🎯 Target consenso {fd.target_price:.2f}$ (+{d.margin_of_safety:.0f}% upside)")
        elif d.margin_of_safety > 5:
            undervalued += 0.5
            d.bullets.append(f"🎯 Target consenso {fd.target_price:.2f}$ (+{d.margin_of_safety:.0f}% upside)")
        elif d.margin_of_safety < -10:
            overvalued += 1.5
            d.bullets.append(f"⚠️ Precio sobre target consenso ({d.margin_of_safety:+.0f}%)")

    # ── Estimación de precio justo por P/E sectorial ─────────
    if price and effective_pe and effective_pe > 0 and d.pe_sector_avg:
        d.fair_value_pe = round(price * (d.pe_sector_avg / effective_pe), 2)

    # ── Recomendación de analistas ───────────────────────────
    if fd.recommendation:
        rec = fd.recommendation.lower()
        if rec in ("buy", "strong_buy", "strong buy"):
            undervalued += 1
            d.bullets.append(f"Consenso analistas: {fd.recommendation}")
        elif rec in ("sell", "strong_sell", "strong sell"):
            overvalued += 1
            d.bullets.append(f"Consenso analistas: {fd.recommendation}")

    # ── Señal final ──────────────────────────────────────────
    diff = undervalued - overvalued
    if diff >= 2.5:
        d.valuation_signal = "UNDERVALUED"
        d.confidence = min(95, 55 + int(diff * 5))
    elif diff <= -2.5:
        d.valuation_signal = "OVERVALUED"
        d.confidence = min(95, 55 + int(abs(diff) * 5))
    else:
        d.valuation_signal = "NEUTRAL"
        d.confidence = max(0, 50 - int(abs(diff) * 3))

    # ── Summary ──────────────────────────────────────────────
    parts = [f"Valoración: {d.valuation_signal}"]
    if d.margin_of_safety is not None:
        parts.append(f"Margen seguridad: {d.margin_of_safety:+.1f}%")
    if d.pe_discount_pct is not None:
        parts.append(f"P/E vs sector: {d.pe_discount_pct:+.0f}%")
    parts.append(f"Señal: {d.valuation_signal} ({d.confidence}%)")
    d.summary = " | ".join(parts)

    return d


def format_for_prompt(d: PriceDiagnosis) -> str:
    """
    Formatea el diagnóstico de precio como texto compacto para
    inyectar en el prompt del LLM.
    """
    lines = [
        f"ANÁLISIS DE PRECIO/VALORACIÓN (determinista, {d.ticker}):",
        f"  Valoración: {d.valuation_signal} (confianza {d.confidence}%)",
    ]
    if d.current_price:
        price_parts = [f"Precio: {d.current_price:.2f}$"]
        if d.range_position is not None:
            price_parts.append(f"Rango 52s: {d.range_position:.0%}")
        if d.pct_vs_200d is not None:
            price_parts.append(f"vs SMA200: {d.pct_vs_200d:+.1f}%")
        lines.append(f"  {' | '.join(price_parts)}")

    if d.fair_value_pe or d.fair_value_consensus:
        fv = []
        if d.fair_value_pe:
            fv.append(f"P/E sect.: {d.fair_value_pe:.2f}$")
        if d.fair_value_consensus:
            fv.append(f"Consenso: {d.fair_value_consensus:.2f}$")
        lines.append(f"  Precio justo → {' | '.join(fv)}")

    for b in d.bullets[:5]:
        lines.append(f"  • {b}")
    return "\n".join(lines)
