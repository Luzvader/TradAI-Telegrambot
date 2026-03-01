"""
Puente Backtesting ↔ Learning.

Conecta el motor de backtesting con el sistema de aprendizaje:
  • Alimenta automáticamente los trades del backtest al módulo de learning.
  • Consulta el historial de aprendizaje para ajustar scores de decisión.
  • Genera análisis agregado de sesiones de backtesting completas.

De esta forma, cada backtest refuerza el conocimiento del bot y las
futuras decisiones (tanto reales como de backtesting) mejoran
progresivamente.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from ai.analyst import _call_llm
from database import repository as repo
from database.models import LearningLog, OperationSide

logger = logging.getLogger(__name__)

# ── Ajuste de scores basado en aprendizaje ───────────────────


async def get_learning_adjustments(
    tickers: list[str],
) -> dict[str, float]:
    """
    Consulta el historial de aprendizaje y devuelve un ajuste de score
    por ticker basado en el track record del bot con ese activo.

    Retorna: {ticker: ajuste} donde ajuste ∈ [-15, +15].
      - Positivo: el bot ha tenido éxito histórico → refuerza la señal.
      - Negativo: el bot ha perdido repetidamente → penaliza.
      - 0: sin historial relevante.
    """
    logs = await repo.get_learning_logs(limit=200)
    if not logs:
        return {t: 0.0 for t in tickers}

    adjustments: dict[str, float] = {}

    for ticker in tickers:
        relevant = [l for l in logs if l.ticker == ticker.upper()]
        if not relevant:
            adjustments[ticker] = 0.0
            continue

        wins = sum(1 for l in relevant if l.outcome == "win")
        losses = sum(1 for l in relevant if l.outcome == "loss")
        total = wins + losses

        if total == 0:
            adjustments[ticker] = 0.0
            continue

        # Win rate del ticker
        win_rate = wins / total

        # Profit medio
        profits = [l.profit_pct for l in relevant if l.profit_pct is not None]
        avg_profit = sum(profits) / len(profits) if profits else 0.0

        # Ajuste: combinación de win rate y profit medio
        # Win rate > 60% → bonus, < 40% → penalización
        wr_adj = (win_rate - 0.5) * 20  # [-10, +10]

        # Profit medio contribuye ±5
        profit_adj = max(min(avg_profit * 0.5, 5), -5)

        # Decaimiento por antigüedad: los más recientes pesan más
        recency_factor = min(1.0, 5 / total)  # Máxima confianza con 5+ trades

        raw = (wr_adj + profit_adj) * recency_factor
        adjustments[ticker] = round(max(min(raw, 15), -15), 2)

    return adjustments


async def get_learning_context_for_decisions() -> str:
    """
    Genera un resumen compacto de las lecciones aprendidas más
    relevantes para informar las decisiones de rebalanceo.

    Returns: texto con los patrones clave, o cadena vacía si no hay historial.
    """
    summary = await repo.get_learning_summary()
    if summary["total_trades_analyzed"] == 0:
        return ""

    logs = await repo.get_learning_logs(limit=30)
    if not logs:
        return ""

    # Extraer patrones clave
    wins = [l for l in logs if l.outcome == "win"]
    losses = [l for l in logs if l.outcome == "loss"]

    lines = []
    if wins:
        win_lessons = [l.lessons_learned for l in wins[:5] if l.lessons_learned]
        if win_lessons:
            lines.append("Patrones de éxito: " + " | ".join(win_lessons[:3]))

    if losses:
        loss_lessons = [l.lessons_learned for l in losses[:5] if l.lessons_learned]
        if loss_lessons:
            lines.append("Errores a evitar: " + " | ".join(loss_lessons[:3]))

    wr = summary['wins'] / max(summary['total_trades_analyzed'], 1) * 100
    lines.append(
        f"Stats: {summary['total_trades_analyzed']} ops | "
        f"WR: {wr:.0f}% | Avg: {summary['avg_profit_pct']}%"
    )

    return "\n".join(lines)


# ── Calcular señales técnicas históricas ─────────────────────


def compute_technical_signal_at_date(
    df_ticker, date, lookback: int = 20
) -> dict[str, Any]:
    """
    Calcula indicadores técnicos simplificados en una fecha específica
    del histórico, para enriquecer las decisiones del backtest.

    Returns: dict con rsi, macd_bullish, bb_position, trend, signal_adj
    """
    import pandas as pd
    from data.technical import (
        calculate_rsi,
        calculate_macd,
        calculate_bollinger_bands,
    )

    result = {
        "rsi": None,
        "macd_bullish": None,
        "bb_position": None,
        "trend": "NEUTRAL",
        "signal_adj": 0.0,  # Ajuste técnico al score [-10, +10]
    }

    if df_ticker is None or df_ticker.empty:
        return result

    # Obtener datos hasta la fecha indicada
    mask = df_ticker.index <= date
    df_slice = df_ticker.loc[mask]

    if len(df_slice) < lookback + 5:
        return result

    close = df_slice["Close"]

    # RSI
    rsi = calculate_rsi(close)
    result["rsi"] = rsi

    # MACD
    macd_l, macd_s, macd_h = calculate_macd(close)
    if macd_l is not None and macd_s is not None:
        result["macd_bullish"] = macd_l > macd_s

    # Bollinger
    _, _, _, bb_pos = calculate_bollinger_bands(close)
    result["bb_position"] = bb_pos

    # Calcular ajuste técnico combinado
    bullish = 0.0
    bearish = 0.0

    if rsi is not None:
        if rsi < 30:
            bullish += 3.0   # Sobreventa → oportunidad
        elif rsi > 70:
            bearish += 3.0   # Sobrecompra → evitar
        elif rsi > 55:
            bullish += 1.0
        elif rsi < 45:
            bearish += 1.0

    if result["macd_bullish"] is True:
        bullish += 2.0
    elif result["macd_bullish"] is False:
        bearish += 2.0

    if bb_pos is not None:
        if bb_pos < 0.15:
            bullish += 2.0   # Cerca de banda inferior
        elif bb_pos > 0.85:
            bearish += 2.0   # Cerca de banda superior

    # SMA 50/200 si hay datos suficientes
    if len(close) >= 200:
        sma50 = float(close.rolling(50).mean().iloc[-1])
        sma200 = float(close.rolling(200).mean().iloc[-1])
        if sma50 > sma200:
            bullish += 1.5   # Golden cross
        else:
            bearish += 1.5   # Death cross
    elif len(close) >= 50:
        sma50 = float(close.rolling(50).mean().iloc[-1])
        current = float(close.iloc[-1])
        if current > sma50:
            bullish += 1.0
        else:
            bearish += 1.0

    # Trend
    if bullish > bearish + 1:
        result["trend"] = "BULLISH"
    elif bearish > bullish + 1:
        result["trend"] = "BEARISH"

    # Ajuste: escala [-10, +10]
    result["signal_adj"] = round(max(min(bullish - bearish, 10), -10), 2)

    return result


# ── Alimentar learning con trades del backtest ───────────────


async def process_backtest_trades_for_learning(
    trades: list[dict[str, Any]],
    strategy: str,
    config_summary: str | None = None,
) -> list[LearningLog]:
    """
    Procesa TODOS los trades cerrados (SELL) de un backtest y los
    registra como aprendizaje. Las lecciones se generan usando la IA
    en lote para ser eficiente.

    Args:
        trades: Lista de trades del backtest ([{ticker, side, price, shares, pnl, date}]).
        strategy: Nombre de la estrategia usada.
        config_summary: Descripción breve de la config del backtest.

    Returns: Lista de LearningLog creados.
    """
    # Filtrar solo ventas (operaciones cerradas con PnL)
    sells = [t for t in trades if t.get("side") == "SELL"]

    if not sells:
        logger.info("Backtest sin ventas, nada que aprender")
        return []

    # Emparejar BUY→SELL para calcular holding_days y entry_price
    buys: dict[str, dict] = {}
    for t in trades:
        if t.get("side") == "BUY":
            buys[t["ticker"]] = t  # Último BUY de cada ticker

    learning_logs: list[LearningLog] = []

    # Analizar en lote (máx 10 trades para no saturar el LLM)
    batch = sells[:10]
    remaining = sells[10:]

    if batch:
        # Generar análisis por lote con LLM
        batch_logs = await _analyze_trade_batch(batch, buys, strategy, config_summary)
        learning_logs.extend(batch_logs)

    # Para los restantes, generar lecciones estadísticas sin LLM
    for trade in remaining:
        log = _create_statistical_learning(trade, buys, strategy)
        saved = await repo.save_learning_log(log)
        learning_logs.append(saved)

    logger.info(
        f"📝 Backtest→Learning: {len(learning_logs)} trades procesados "
        f"(estrategia: {strategy})"
    )
    return learning_logs


async def _analyze_trade_batch(
    sells: list[dict],
    buys: dict[str, dict],
    strategy: str,
    config_summary: str | None,
) -> list[LearningLog]:
    """Analiza un lote de trades con el LLM y genera LearningLogs."""
    # Construir prompt con todos los trades
    trade_lines = []
    for i, sell in enumerate(sells, 1):
        buy = buys.get(sell["ticker"], {})
        entry = buy.get("price", sell.get("price", 0))
        exit_p = sell.get("price", 0)
        pnl = sell.get("pnl", 0)
        pnl_pct = round((exit_p - entry) / entry * 100, 2) if entry > 0 else 0
        buy_date = buy.get("date", "?")
        sell_date = sell.get("date", "?")
        trade_lines.append(
            f"{i}. {sell['ticker']}: BUY@{entry:.2f}({buy_date}) → "
            f"SELL@{exit_p:.2f}({sell_date}) | PnL: {pnl_pct:+.1f}%"
        )

    trades_text = "\n".join(trade_lines)

    prompt = f"""Analiza estos trades de un backtest (estrategia: {strategy}):
{trades_text}
{f'Config: {config_summary}' if config_summary else ''}

Para CADA trade, responde en una línea con formato:
N. [TICKER] | Bien: ... | Mal: ... | Lección: ...

Al final, añade:
RESUMEN: Una lección general del lote en 1 frase.
"""

    try:
        analysis = await _call_llm(prompt, max_tokens=600, context="backtest_learning")
    except Exception as e:
        logger.warning(f"Error LLM en backtest learning: {e}")
        analysis = ""

    # Parsear respuestas y crear logs
    logs: list[LearningLog] = []
    analysis_lines = analysis.strip().split("\n") if analysis else []
    general_lesson = ""

    # Extraer resumen general
    for line in analysis_lines:
        if line.upper().startswith("RESUMEN"):
            general_lesson = line.split(":", 1)[-1].strip() if ":" in line else ""

    for sell in sells:
        buy = buys.get(sell["ticker"], {})
        entry = buy.get("price", sell.get("price", 0))
        exit_p = sell.get("price", 0)
        pnl_pct = round((exit_p - entry) / entry * 100, 2) if entry > 0 else 0
        outcome = "win" if pnl_pct > 1 else "loss" if pnl_pct < -1 else "breakeven"

        # Buscar análisis específico
        well, wrong, lesson = "", "", ""
        for line in analysis_lines:
            if sell["ticker"] in line.upper():
                parts = line.split("|")
                for p in parts:
                    p_strip = p.strip().lower()
                    if p_strip.startswith("bien:"):
                        well = p.split(":", 1)[-1].strip()
                    elif p_strip.startswith("mal:"):
                        wrong = p.split(":", 1)[-1].strip()
                    elif p_strip.startswith("lecc"):
                        lesson = p.split(":", 1)[-1].strip()
                break

        # Calcular holding_days
        holding_days = 0
        buy_date = buy.get("date")
        sell_date = sell.get("date")
        if buy_date and sell_date:
            try:
                from datetime import datetime
                bd = datetime.fromisoformat(buy_date)
                sd = datetime.fromisoformat(sell_date)
                holding_days = (sd - bd).days
            except Exception as e:
                logger.debug(f"Error parseando fechas de operación: {e}")

        log = LearningLog(
            ticker=sell["ticker"].upper(),
            side=OperationSide.SELL,
            entry_price=entry,
            exit_price=exit_p,
            profit_pct=pnl_pct,
            holding_days=holding_days,
            outcome=outcome,
            what_went_well=well or (f"Trade cerrado con {pnl_pct:+.1f}%" if pnl_pct > 0 else ""),
            what_went_wrong=wrong or (f"Pérdida de {pnl_pct:.1f}%" if pnl_pct < 0 else ""),
            lessons_learned=lesson or general_lesson,
            market_context_at_entry=f"Backtest {strategy}",
            source="backtest",
            strategy_used=strategy,
        )
        saved = await repo.save_learning_log(log)
        logs.append(saved)

    return logs


def _create_statistical_learning(
    sell: dict, buys: dict[str, dict], strategy: str
) -> LearningLog:
    """Crea un LearningLog estadístico sin LLM (para trades extra)."""
    buy = buys.get(sell["ticker"], {})
    entry = buy.get("price", sell.get("price", 0))
    exit_p = sell.get("price", 0)
    pnl_pct = round((exit_p - entry) / entry * 100, 2) if entry > 0 else 0
    outcome = "win" if pnl_pct > 1 else "loss" if pnl_pct < -1 else "breakeven"

    holding_days = 0
    buy_date = buy.get("date")
    sell_date = sell.get("date")
    if buy_date and sell_date:
        try:
            from datetime import datetime
            bd = datetime.fromisoformat(buy_date)
            sd = datetime.fromisoformat(sell_date)
            holding_days = (sd - bd).days
        except Exception:
            pass

    if outcome == "win":
        well = f"Trade rentable: {pnl_pct:+.1f}% en {holding_days}d"
        wrong = ""
        lesson = f"Score {strategy} acertó en {sell['ticker']}"
    elif outcome == "loss":
        well = ""
        wrong = f"Pérdida: {pnl_pct:.1f}% en {holding_days}d"
        lesson = f"Revisar criterios de {strategy} para {sell['ticker']}"
    else:
        well = "Trade neutral"
        wrong = "Sin ganancia significativa"
        lesson = "Posición sin movimiento relevante"

    return LearningLog(
        ticker=sell["ticker"].upper(),
        side=OperationSide.SELL,
        entry_price=entry,
        exit_price=exit_p,
        profit_pct=pnl_pct,
        holding_days=holding_days,
        outcome=outcome,
        what_went_well=well,
        what_went_wrong=wrong,
        lessons_learned=lesson,
        market_context_at_entry=f"Backtest {strategy}",
        source="backtest",
        strategy_used=strategy,
    )


# ── Análisis agregado de sesión de backtest ──────────────────


async def analyze_backtest_session(
    trades: list[dict[str, Any]],
    metrics_summary: str,
    strategy: str,
) -> str:
    """
    Genera un análisis IA completo de una sesión de backtesting.
    Identifica patrones de éxito/fracaso y recomendaciones.

    Returns: texto con el análisis para mostrar al usuario y almacenar.
    """
    sells = [t for t in trades if t.get("side") == "SELL"]
    buys = [t for t in trades if t.get("side") == "BUY"]

    winners = [t for t in sells if t.get("pnl", 0) > 0]
    losers = [t for t in sells if t.get("pnl", 0) < 0]

    # Contexto de aprendizaje previo
    prev_logs = await repo.get_learning_logs(limit=10)
    prev_lessons = "\n".join(
        f"  - {l.ticker} ({l.outcome}): {l.lessons_learned}"
        for l in prev_logs if l.lessons_learned
    ) or "Sin historial previo."

    prompt = f"""Analiza esta sesión de backtesting (estrategia: {strategy}):

{metrics_summary}

Operaciones: {len(buys)} compras, {len(sells)} ventas
Ganadoras: {len(winners)} | Perdedoras: {len(losers)}

Tickers ganadores: {', '.join(set(t['ticker'] for t in winners)) or 'ninguno'}
Tickers perdedores: {', '.join(set(t['ticker'] for t in losers)) or 'ninguno'}

Historial de aprendizaje previo:
{prev_lessons}

Genera:
1. Patrón principal de éxito identificado
2. Error principal identificado
3. ¿La estrategia {strategy} fue adecuada? (sí/no + por qué)
4. Recomendación concreta para mejorar
5. ¿Qué debería hacer diferente el bot la próxima vez?
"""

    try:
        analysis = await _call_llm(prompt, max_tokens=500, context="backtest_session_analysis")
    except Exception as e:
        logger.warning(f"Error en análisis de sesión: {e}")
        analysis = (
            f"Sesión {strategy}: {len(sells)} trades cerrados, "
            f"{len(winners)} ganadores, {len(losers)} perdedores."
        )

    return analysis
