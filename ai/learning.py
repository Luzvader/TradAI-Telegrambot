"""
Módulo de aprendizaje – analiza operaciones pasadas, señales emitidas,
contexto de mercado y datos técnicos para extraer lecciones y mejorar
las decisiones futuras.

Fuentes de datos que alimentan el aprendizaje:
  • Operaciones cerradas (reales y backtest) con contexto enriquecido
  • AnalysisLog – predicción vs. realidad
  • Señales emitidas – precisión de score por tipo y rango
  • Contexto de mercado – correlación régimen / rentabilidad
  • Indicadores técnicos – RSI, MACD al momento de compra
  • Dividendos cobrados – retorno total ajustado
  • Diversificación del portfolio al momento de la operación
  • Origen de la operación (manual / auto / safe)
"""

import logging

from ai.analyst import _call_llm
from database import repository as repo
from database.models import LearningLog, OperationSide

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 1. Análisis de operación cerrada (core del aprendizaje)
# ─────────────────────────────────────────────────────────────


async def analyze_closed_trade(
    ticker: str,
    side: str,
    entry_price: float,
    exit_price: float,
    holding_days: int,
    market_context: str | None = None,
    source: str = "real",
    strategy_used: str | None = None,
    origin: str | None = None,
    total_dividends: float | None = None,
    entry_signal_score: float | None = None,
    entry_rsi: float | None = None,
    entry_macd_signal: str | None = None,
    diversification_score_at_entry: float | None = None,
    market_regime: str | None = None,
) -> LearningLog:
    """
    Analiza una operación cerrada y genera lecciones aprendidas
    usando la IA.  Incorpora todo el contexto enriquecido disponible:
    análisis previo, dividendos, indicadores técnicos, régimen de
    mercado, diversificación y origen de la operación.
    """
    # ── Cálculo P/L ──
    pnl_pct = round((exit_price - entry_price) / entry_price * 100, 2)

    # P/L ajustado a dividendos si hay dato
    total_return_pct = pnl_pct
    div_note = ""
    if total_dividends and total_dividends > 0 and entry_price > 0:
        div_return = total_dividends / entry_price * 100
        total_return_pct = round(pnl_pct + div_return, 2)
        div_note = (
            f"  (precio: {pnl_pct}% + dividendos: {div_return:.1f}% "
            f"= total: {total_return_pct}%)"
        )

    outcome = (
        "win" if total_return_pct > 1
        else "loss" if total_return_pct < -1
        else "breakeven"
    )

    # ── Historial previo ──
    prev_logs = await repo.get_learning_logs(limit=10)
    prev_context = "\n".join(
        f"  - {l.ticker}: {l.outcome} ({l.profit_pct}%) → {l.lessons_learned}"
        for l in prev_logs if l.lessons_learned
    ) or "Sin historial previo."

    # ── Análisis previo almacenado (predicción original) ──
    analysis_context = ""
    try:
        analysis_logs = await repo.get_analysis_logs(ticker=ticker, limit=3)
        if analysis_logs:
            parts = []
            for al in analysis_logs:
                date_str = (
                    al.created_at.strftime("%d/%m/%Y")
                    if al.created_at else "?"
                )
                score_str = f"{al.overall_score:.0f}" if al.overall_score else "?"
                parts.append(
                    f"  [{date_str}] Señal={al.signal} Score={score_str}/100 "
                    f"Precio={al.price_at_analysis} MoS={al.margin_of_safety}"
                )
                if al.reasoning:
                    parts.append(f"    Razón: {al.reasoning[:200]}")
            analysis_context = (
                "\nAnálisis previos almacenados:\n" + "\n".join(parts)
            )
    except Exception as e:
        logger.debug(f"No se pudieron obtener análisis previos de {ticker}: {e}")

    # ── Contexto de mercado al momento de compra ──
    market_ctx_text = ""
    if market_context:
        market_ctx_text = f"\nContexto de mercado al comprar: {market_context}"

    # ── Bloque de indicadores técnicos y metadata ──
    tech_parts: list[str] = []
    if entry_rsi is not None:
        tech_parts.append(f"RSI al comprar: {entry_rsi:.1f}")
    if entry_macd_signal:
        tech_parts.append(f"MACD: {entry_macd_signal}")
    if entry_signal_score is not None:
        tech_parts.append(f"Score de señal: {entry_signal_score:.0f}/100")
    if diversification_score_at_entry is not None:
        tech_parts.append(
            f"Diversificación: {diversification_score_at_entry:.0f}/100"
        )
    if market_regime:
        tech_parts.append(f"Régimen mercado: {market_regime}")
    if origin:
        tech_parts.append(f"Origen: {origin}")
    if strategy_used:
        tech_parts.append(f"Estrategia: {strategy_used}")
    tech_block = ""
    if tech_parts:
        tech_block = (
            "\nMetadatos de la operación:\n  " + " | ".join(tech_parts)
        )

    # ── Prompt LLM ──
    prompt = f"""Analiza operación cerrada:
{side} ${ticker}: {entry_price}$→{exit_price}$ | P&L: {pnl_pct}%{div_note} | {holding_days} días | {outcome}
{market_ctx_text}
{analysis_context}
{tech_block}

Historial previo:
{prev_context}

Responde 3 secciones (1-2 frases cada una):
1. ¿Qué salió bien?
2. ¿Qué salió mal?
3. Lección principal (compara predicción vs. realidad; valora si los \
indicadores técnicos ayudaron; evalúa si el régimen de mercado y la \
diversificación influyeron; distingue resultado real de dividendos)
"""

    analysis = await _call_llm(prompt, max_tokens=300)

    # ── Parsear secciones ──
    well, wrong, lesson = _parse_llm_sections(analysis)

    log = LearningLog(
        ticker=ticker.upper(),
        side=OperationSide.BUY if side.upper() == "BUY" else OperationSide.SELL,
        entry_price=entry_price,
        exit_price=exit_price,
        profit_pct=total_return_pct,
        holding_days=holding_days,
        outcome=outcome,
        what_went_well=well.strip() or analysis,
        what_went_wrong=wrong.strip(),
        lessons_learned=lesson.strip(),
        market_context_at_entry=market_context,
        source=source,
        strategy_used=strategy_used,
        origin=origin,
        total_dividends=total_dividends,
        entry_signal_score=entry_signal_score,
        entry_rsi=entry_rsi,
        entry_macd_signal=entry_macd_signal,
        diversification_score_at_entry=diversification_score_at_entry,
        market_regime=market_regime,
    )

    saved = await repo.save_learning_log(log)
    logger.info(
        f"📝 Aprendizaje registrado: {ticker} {outcome} ({total_return_pct}%) "
        f"[{source}/{origin or 'manual'}]"
    )
    return saved


# ─────────────────────────────────────────────────────────────
# 2. Insights globales de aprendizaje
# ─────────────────────────────────────────────────────────────


async def get_learning_insights() -> str:
    """Genera un resumen de aprendizaje con insights accionables.

    Incluye datos de operaciones reales, backtesting, por origen
    y por régimen de mercado.
    """
    summary = await repo.get_learning_summary()
    logs = await repo.get_learning_logs(limit=20)

    if summary["total_trades_analyzed"] == 0:
        return (
            "📝 Sin datos de aprendizaje todavía. "
            "Las operaciones cerradas y los backtests se analizarán "
            "automáticamente."
        )

    real_logs = [l for l in logs if getattr(l, "source", "real") == "real"]
    bt_logs = [l for l in logs if getattr(l, "source", "real") == "backtest"]

    lessons = "\n".join(
        f"- {'[BT]' if getattr(l, 'source', 'real') == 'backtest' else '[REAL]'} "
        f"{l.ticker} ({l.outcome}, {l.profit_pct}%): {l.lessons_learned}"
        for l in logs if l.lessons_learned
    )

    # Stats por origen (manual / auto / safe)
    origin_stats = ""
    try:
        by_origin = await repo.get_learning_stats_by_origin()
        if by_origin:
            parts = []
            for orig, stats in by_origin.items():
                parts.append(
                    f"  {orig}: {stats['total']} ops | "
                    f"Win rate: {stats['win_rate']:.0f}% | "
                    f"Avg PnL: {stats['avg_pnl']:+.1f}%"
                )
            origin_stats = "\nPor origen:\n" + "\n".join(parts)
    except Exception:
        pass

    # Stats por régimen de mercado
    regime_stats = ""
    try:
        by_regime = await repo.get_learning_stats_by_market_regime()
        if by_regime:
            parts = []
            for regime, stats in by_regime.items():
                parts.append(
                    f"  {regime}: {stats['total']} ops | "
                    f"Avg PnL: {stats['avg_pnl']:+.1f}%"
                )
            regime_stats = "\nPor régimen de mercado:\n" + "\n".join(parts)
    except Exception:
        pass

    wr = summary["wins"] / max(summary["total_trades_analyzed"], 1) * 100
    prompt = f"""Insights de trading basados en historial:
Stats: {summary['total_trades_analyzed']} ops | Win rate: {wr:.0f}% | \
Avg profit: {summary['avg_profit_pct']}%
Fuentes: {len(real_logs)} reales + {len(bt_logs)} backtest
{origin_stats}
{regime_stats}

Lecciones:
{lessons}

Genera:
1) Top 3 patrones de éxito (incluye si un origen o régimen destaca)
2) Top 3 errores a evitar
3) Recomendaciones concretas (ajustar auto-mode, umbrales de score, \
gestión en diferentes regímenes)
Nota: los datos [BT] refuerzan patrones; los [REAL] pesan más.
"""
    return await _call_llm(prompt, max_tokens=500)


# ─────────────────────────────────────────────────────────────
# 3. Bias check pre-operación
# ─────────────────────────────────────────────────────────────


async def get_learning_bias_check(ticker: str, side: str) -> str:
    """
    Antes de una operación, consulta el aprendizaje previo
    (tanto real como de backtesting), los análisis almacenados,
    indicadores técnicos históricos y régimen de mercado
    para alertar sobre sesgos o errores repetidos.
    """
    logs = await repo.get_learning_logs(limit=50)
    relevant = [
        l for l in logs
        if l.ticker == ticker.upper() or l.outcome == "loss"
    ]

    if not relevant:
        return ""

    real = [l for l in relevant if getattr(l, "source", "real") == "real"]
    bt = [l for l in relevant if getattr(l, "source", "real") == "backtest"]

    context_parts: list[str] = []
    if real:
        context_parts.append("Operaciones reales:")
        for l in real[:5]:
            if l.lessons_learned:
                line = (
                    f"  - {l.ticker} ({l.side.value} → {l.outcome}, "
                    f"{l.profit_pct}%)"
                )
                if getattr(l, "entry_rsi", None):
                    line += f" RSI:{l.entry_rsi:.0f}"
                if getattr(l, "market_regime", None):
                    line += f" [{l.market_regime}]"
                line += f": {l.lessons_learned}"
                context_parts.append(line)
    if bt:
        context_parts.append("Backtests:")
        context_parts.extend(
            f"  - {l.ticker} ({l.outcome}, {l.profit_pct}%): "
            f"{l.lessons_learned}"
            for l in bt[:5] if l.lessons_learned
        )

    # Análisis previos almacenados del ticker
    try:
        prev_analyses = await repo.get_analysis_logs(ticker=ticker, limit=3)
        if prev_analyses:
            context_parts.append("Análisis previos almacenados:")
            for al in prev_analyses:
                date_str = (
                    al.created_at.strftime("%d/%m/%Y")
                    if al.created_at else "?"
                )
                score_str = (
                    f"{al.overall_score:.0f}" if al.overall_score else "?"
                )
                context_parts.append(
                    f"  - [{date_str}] Señal={al.signal} "
                    f"Score={score_str} Precio={al.price_at_analysis}"
                )
    except Exception:
        pass

    # Estadísticas por origen (¿auto es mejor que manual?)
    try:
        by_origin = await repo.get_learning_stats_by_origin()
        if by_origin and len(by_origin) > 1:
            parts = [
                f"{o}: WR {s['win_rate']:.0f}%"
                for o, s in by_origin.items()
            ]
            context_parts.append("Por origen: " + " | ".join(parts))
    except Exception:
        pass

    if not context_parts:
        return ""

    context = "\n".join(context_parts)

    prompt = f"""{side} ${ticker} — ¿sesgo o error a tener en cuenta?
Historial:
{context}
Máx 2 frases. Los datos reales pesan más que backtests.
Si hay datos técnicos (RSI, régimen), incorpóralos en la valoración.
Si no hay sesgos, di 'Sin alertas de sesgo.'
"""
    return await _call_llm(prompt, max_tokens=150)


# ─────────────────────────────────────────────────────────────
# 4. Validación de precisión de señales
# ─────────────────────────────────────────────────────────────


async def validate_signal_accuracy(
    signal_id: int,
    ticker: str,
    signal_type: str,
    signal_score: float | None,
    signal_price: float,
    current_price: float,
    days_elapsed: int,
) -> LearningLog | None:
    """
    Valida una señal emitida hace N días comparando el precio de
    entonces con el precio actual.  Genera un ``LearningLog`` con la
    conclusión.
    """
    if signal_price <= 0:
        return None

    price_change_pct = round(
        (current_price - signal_price) / signal_price * 100, 2
    )

    # Determinar si la señal fue correcta
    if signal_type == "BUY":
        correct = price_change_pct > 2
    elif signal_type == "SELL":
        correct = price_change_pct < -2
    else:
        return None

    outcome = "win" if correct else "loss"
    score_str = f" (score: {signal_score:.0f})" if signal_score else ""

    prompt = f"""Validación de señal:
Señal {signal_type}{score_str} emitida para ${ticker} a \
{signal_price:.2f}$.
Después de {days_elapsed} días, precio actual: \
{current_price:.2f}$ ({price_change_pct:+.1f}%).
La señal fue {'correcta ✅' if correct else 'incorrecta ❌'}.

En 1 frase: ¿qué se puede aprender para calibrar umbrales de score?
"""
    lesson = await _call_llm(prompt, max_tokens=100)

    log = LearningLog(
        ticker=ticker.upper(),
        side=(
            OperationSide.BUY if signal_type == "BUY"
            else OperationSide.SELL
        ),
        entry_price=signal_price,
        exit_price=current_price,
        profit_pct=(
            price_change_pct if signal_type == "BUY"
            else -price_change_pct
        ),
        holding_days=days_elapsed,
        outcome=outcome,
        what_went_well=lesson if correct else "",
        what_went_wrong="" if correct else lesson,
        lessons_learned=lesson,
        source="signal_validation",
        entry_signal_score=signal_score,
    )

    saved = await repo.save_learning_log(log)

    # Marcar la señal como validada
    try:
        await repo.mark_signal_validated(signal_id)
    except Exception:
        pass

    logger.info(
        f"🎯 Señal validada: {signal_type} {ticker} "
        f"{signal_price:.2f}$→{current_price:.2f}$ "
        f"({price_change_pct:+.1f}%) = {outcome}"
    )
    return saved


# ─────────────────────────────────────────────────────────────
# 5. Informe de rendimiento por segmento
# ─────────────────────────────────────────────────────────────


async def get_strategy_performance_report() -> str:
    """Genera un informe comparando estrategias, orígenes y regímenes."""
    by_origin = await repo.get_learning_stats_by_origin()
    by_regime = await repo.get_learning_stats_by_market_regime()
    summary = await repo.get_learning_summary()

    if summary["total_trades_analyzed"] < 3:
        return (
            "📊 Insuficientes datos para un informe de rendimiento "
            "(mínimo 3 operaciones)."
        )

    sections: list[str] = []
    sections.append(
        f"Total: {summary['total_trades_analyzed']} ops | "
        f"Win rate: {summary['wins']}/{summary['total_trades_analyzed']} | "
        f"Avg PnL: {summary['avg_profit_pct']}%"
    )

    if by_origin:
        sections.append("\nPor origen:")
        for orig, s in sorted(
            by_origin.items(), key=lambda x: -x[1]["win_rate"]
        ):
            sections.append(
                f"  {orig}: {s['total']} ops | WR: {s['win_rate']:.0f}% | "
                f"Avg: {s['avg_pnl']:+.1f}%"
            )

    if by_regime:
        sections.append("\nPor régimen de mercado:")
        for regime, s in by_regime.items():
            sections.append(
                f"  {regime}: {s['total']} ops | Avg: {s['avg_pnl']:+.1f}%"
            )

    context = "\n".join(sections)
    prompt = f"""Informe de rendimiento del sistema de trading:
{context}

Genera un informe breve (máx 200 palabras):
1. ¿Qué origen de operación (manual/auto) funciona mejor?
2. ¿En qué régimen de mercado (fear/greed/neutral) rinde mejor?
3. Recomendaciones concretas para optimizar
"""
    return await _call_llm(prompt, max_tokens=400)


# ─────────────────────────────────────────────────────────────
# Utilidades internas
# ─────────────────────────────────────────────────────────────


def _parse_llm_sections(text: str) -> tuple[str, str, str]:
    """Parsea la respuesta LLM en las 3 secciones esperadas."""
    lines = text.strip().split("\n")
    well = ""
    wrong = ""
    lesson = ""
    current = ""
    for line in lines:
        line_lower = line.lower().strip()
        if "salió bien" in line_lower or line_lower[:3] == "1.":
            current = "well"
            well = line.split(":", 1)[-1].strip() if ":" in line else ""
        elif "salió mal" in line_lower or line_lower[:3] == "2.":
            current = "wrong"
            wrong = line.split(":", 1)[-1].strip() if ":" in line else ""
        elif "lección" in line_lower or line_lower[:3] == "3.":
            current = "lesson"
            lesson = line.split(":", 1)[-1].strip() if ":" in line else ""
        else:
            if current == "well":
                well += " " + line.strip()
            elif current == "wrong":
                wrong += " " + line.strip()
            elif current == "lesson":
                lesson += " " + line.strip()
    return well, wrong, lesson
