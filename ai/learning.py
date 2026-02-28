"""
Módulo de aprendizaje – analiza operaciones pasadas para extraer
lecciones y mejorar las decisiones futuras.
"""

import logging
from typing import Any

from ai.analyst import _call_llm
from database import repository as repo
from database.models import LearningLog, OperationSide

logger = logging.getLogger(__name__)


async def analyze_closed_trade(
    ticker: str,
    side: str,
    entry_price: float,
    exit_price: float,
    holding_days: int,
    market_context: str | None = None,
    source: str = "real",
    strategy_used: str | None = None,
) -> LearningLog:
    """
    Analiza una operación cerrada y genera lecciones aprendidas
    usando la IA.
    """
    pnl_pct = round((exit_price - entry_price) / entry_price * 100, 2)
    outcome = "win" if pnl_pct > 1 else "loss" if pnl_pct < -1 else "breakeven"

    # Obtener historial previo para contexto
    prev_logs = await repo.get_learning_logs(limit=10)
    prev_context = "\n".join(
        [f"  - {l.ticker}: {l.outcome} ({l.profit_pct}%) → {l.lessons_learned}"
         for l in prev_logs if l.lessons_learned]
    ) or "Sin historial previo."

    prompt = f"""Analiza operación cerrada:
{side} ${ticker}: {entry_price}$→{exit_price}$ | P&L: {pnl_pct}% | {holding_days} días | {outcome}
Contexto: {market_context or 'N/D'}

Historial previo:
{prev_context}

Responde 3 secciones (1-2 frases cada una):
1. ¿Qué salió bien?
2. ¿Qué salió mal?
3. Lección principal
"""

    analysis = await _call_llm(prompt, max_tokens=300)

    # Parsear las secciones
    lines = analysis.strip().split("\n")
    well = ""
    wrong = ""
    lesson = ""
    current = ""
    for line in lines:
        line_lower = line.lower().strip()
        if "salió bien" in line_lower or "1." in line_lower[:3]:
            current = "well"
            well = line.split(":", 1)[-1].strip() if ":" in line else ""
        elif "salió mal" in line_lower or "2." in line_lower[:3]:
            current = "wrong"
            wrong = line.split(":", 1)[-1].strip() if ":" in line else ""
        elif "lección" in line_lower or "3." in line_lower[:3]:
            current = "lesson"
            lesson = line.split(":", 1)[-1].strip() if ":" in line else ""
        else:
            if current == "well":
                well += " " + line.strip()
            elif current == "wrong":
                wrong += " " + line.strip()
            elif current == "lesson":
                lesson += " " + line.strip()

    log = LearningLog(
        ticker=ticker.upper(),
        side=OperationSide.BUY if side.upper() == "BUY" else OperationSide.SELL,
        entry_price=entry_price,
        exit_price=exit_price,
        profit_pct=pnl_pct,
        holding_days=holding_days,
        outcome=outcome,
        what_went_well=well.strip() or analysis,
        what_went_wrong=wrong.strip(),
        lessons_learned=lesson.strip(),
        market_context_at_entry=market_context,
        source=source,
        strategy_used=strategy_used,
    )

    saved = await repo.save_learning_log(log)
    logger.info(
        f"📝 Aprendizaje registrado: {ticker} {outcome} ({pnl_pct}%)"
    )
    return saved


async def get_learning_insights() -> str:
    """Genera un resumen de aprendizaje con insights accionables.
    Incluye datos tanto de operaciones reales como de backtesting."""
    summary = await repo.get_learning_summary()
    logs = await repo.get_learning_logs(limit=20)

    if summary["total_trades_analyzed"] == 0:
        return "📝 Sin datos de aprendizaje todavía. Las operaciones cerradas y los backtests se analizarán automáticamente."

    # Separar por fuente
    real_logs = [l for l in logs if getattr(l, 'source', 'real') == 'real']
    bt_logs = [l for l in logs if getattr(l, 'source', 'real') == 'backtest']

    # Construir contexto
    lessons = "\n".join(
        [f"- {'[BT]' if getattr(l, 'source', 'real') == 'backtest' else '[REAL]'} "
         f"{l.ticker} ({l.outcome}, {l.profit_pct}%): {l.lessons_learned}"
         for l in logs if l.lessons_learned]
    )

    wr = summary['wins']/max(summary['total_trades_analyzed'],1)*100
    prompt = f"""Insights de trading basados en historial:
Stats: {summary['total_trades_analyzed']} ops | Win rate: {wr:.0f}% | Avg profit: {summary['avg_profit_pct']}%
Fuentes: {len(real_logs)} reales + {len(bt_logs)} backtest

Lecciones:
{lessons}

Genera: 1) Top 3 patrones de éxito 2) Top 3 errores a evitar 3) Recomendaciones concretas
Nota: los datos de [BT] backtest refuerzan patrones, los [REAL] tienen más peso.
"""
    return await _call_llm(prompt, max_tokens=500)


async def get_learning_bias_check(
    ticker: str, side: str
) -> str:
    """
    Antes de una operación, consulta el aprendizaje previo
    (tanto real como de backtesting) para alertar sobre sesgos
    o errores repetidos.
    """
    logs = await repo.get_learning_logs(limit=50)
    # Incluir logs del ticker específico y losses generales
    relevant = [l for l in logs if l.ticker == ticker.upper() or l.outcome == "loss"]

    if not relevant:
        return ""

    # Separar por fuente para dar más peso a reales
    real = [l for l in relevant if getattr(l, 'source', 'real') == 'real']
    bt = [l for l in relevant if getattr(l, 'source', 'real') == 'backtest']

    context_parts = []
    if real:
        context_parts.append("Operaciones reales:")
        context_parts.extend(
            f"  - {l.ticker} ({l.side.value} → {l.outcome}, {l.profit_pct}%): {l.lessons_learned}"
            for l in real[:5] if l.lessons_learned
        )
    if bt:
        context_parts.append("Backtests:")
        context_parts.extend(
            f"  - {l.ticker} ({l.outcome}, {l.profit_pct}%): {l.lessons_learned}"
            for l in bt[:5] if l.lessons_learned
        )

    if not context_parts:
        return ""

    context = "\n".join(context_parts)

    prompt = f"""{side} ${ticker} — ¿sesgo o error a tener en cuenta?
Historial:
{context}
Máx 2 frases. Los datos reales tienen más peso que backtests. Si no hay sesgos, di 'Sin alertas de sesgo.'
"""
    return await _call_llm(prompt, max_tokens=150)
