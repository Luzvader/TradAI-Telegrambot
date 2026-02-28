"""
Modo Automático – ejecuta ciclos periódicos de análisis completo:
  • Scan de oportunidades value
  • Análisis macro/geopolítico
  • Re-análisis de posiciones abiertas
  • Gestión automática de watchlist
  • Resumen diario a las 9:00 (hora España)
  • Envío de señales relevantes por Telegram

Se activa/desactiva con /auto on|off y se configura con /auto config.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Bot

from ai.analyst import analyze_with_context, get_macro_analysis
from ai.watchlist import ai_generate_watchlist, refresh_watchlist_analysis
from config import settings
from config.markets import market_display
from config.settings import TIMEZONE
from data.news import save_context_snapshot
from database import repository as repo
from database.models import PortfolioType
from portfolio.portfolio_manager import (
    check_alerts,
    get_portfolio_summary,
    update_all_prices,
)
from notifications import notify as _notify, set_notification_bot
from signals.signal_engine import (

    analyze_ticker,
    generate_signals_for_portfolio,
    scan_opportunities,
)

logger = logging.getLogger(__name__)

# Tracking en memoria para la watchlist (no tiene columna dedicada en BD)
_last_watchlist_run: dict[int, datetime] = {}  # portfolio_id -> last run UTC


def set_auto_mode_bot(bot: Bot | None) -> None:
    """Establece la referencia al bot de Telegram (delegado al módulo compartido)."""
    set_notification_bot(bot)


# ── Ciclo principal del modo auto ────────────────────────────


async def auto_mode_cycle() -> None:
    """
    Ciclo principal: comprueba qué portfolios tienen modo auto activo
    y ejecuta las tareas pendientes según sus intervalos.
    """
    active_configs = await repo.get_all_active_auto_modes()
    if not active_configs:
        return

    now = datetime.now(UTC)

    for config in active_configs:
        try:
            await _process_auto_portfolio(config, now)
        except Exception as e:
            logger.error(
                f"Error en auto_mode portfolio_id={config.portfolio_id}: {e}"
            )


async def _process_auto_portfolio(config, now: datetime) -> None:
    """Procesa un portfolio en modo auto."""
    portfolio_id = config.portfolio_id

    # ── Scan de oportunidades ──
    if _should_run(config.last_scan_at, config.scan_interval_minutes, now):
        await _auto_scan(portfolio_id)
        await repo.update_auto_mode_timestamps(
            portfolio_id, last_scan_at=now
        )

    # ── Análisis macro ──
    if _should_run(config.last_macro_at, config.macro_interval_minutes, now):
        await _auto_macro(portfolio_id)
        await repo.update_auto_mode_timestamps(
            portfolio_id, last_macro_at=now
        )

    # ── Re-análisis de posiciones ──
    if _should_run(
        config.last_analyze_at, config.analyze_interval_minutes, now
    ):
        await _auto_analyze_positions(portfolio_id, config)
        await repo.update_auto_mode_timestamps(
            portfolio_id, last_analyze_at=now
        )

    # ── Gestión de watchlist (usa el mismo intervalo que scan) ──
    if config.watchlist_auto_manage:
        last_wl = _last_watchlist_run.get(portfolio_id)
        if _should_run(last_wl, config.scan_interval_minutes, now):
            await _auto_manage_watchlist(portfolio_id, config)
            _last_watchlist_run[portfolio_id] = now

    # ── Resumen diario ──
    await _check_daily_summary(config, now)


def _should_run(
    last_run: datetime | None, interval_minutes: int, now: datetime
) -> bool:
    """Comprueba si una tarea debe ejecutarse según su intervalo."""
    if last_run is None:
        return True
    elapsed = (now - last_run).total_seconds() / 60
    should = elapsed >= interval_minutes
    if should:
        logger.debug(
            f"⏱️ Tarea lista: {elapsed:.1f} min transcurridos "
            f"(intervalo: {interval_minutes} min)"
        )
    return should


# ── Tareas automáticas ───────────────────────────────────────


async def _auto_scan(portfolio_id: int) -> None:
    """Ejecuta un scan de oportunidades y notifica las mejores."""
    logger.info(f"🤖 [AUTO] Escaneando oportunidades para portfolio {portfolio_id}")

    try:
        opportunities = await scan_opportunities(
            max_results=5, portfolio_id=portfolio_id
        )
        if not opportunities:
            return

        # Filtrar solo BUY con score alto
        strong = [o for o in opportunities if o["signal"] == "BUY" and o["overall_score"] >= settings.SIGNAL_BUY_THRESHOLD]
        if strong:
            text = "🤖 *MODO AUTO — Oportunidades detectadas*\n\n"
            for i, opp in enumerate(strong, 1):
                price_str = f"{opp['price']:.2f}$" if opp.get('price') else "N/A"
                text += (
                    f"{i}. 🟢 *${opp['ticker']}* — Score: {opp['overall_score']:.0f}/100 | Precio: {price_str}\n"
                    f"   V:{opp['value_score']:.0f} Q:{opp['quality_score']:.0f} S:{opp['safety_score']:.0f}\n"
                    f"   MoS: {opp.get('margin_of_safety', 'N/A')}%\n\n"
                )
            await _notify(text)
    except Exception as e:
        logger.error(f"Error en auto_scan: {e}")


async def _auto_macro(portfolio_id: int) -> None:
    """Ejecuta análisis macro y guarda contexto."""
    logger.info(f"🤖 [AUTO] Análisis macro para portfolio {portfolio_id}")
    try:
        await save_context_snapshot()

        macro = await get_macro_analysis()
        if macro and "Error" not in macro:
            text = "🤖 *MODO AUTO — Actualización Macro*\n\n" + macro
            await _notify(text)
    except Exception as e:
        logger.error(f"Error en auto_macro: {e}")


async def _auto_analyze_positions(portfolio_id: int, config) -> None:
    """Re-analiza todas las posiciones y envía señales activas."""
    logger.info(f"🤖 [AUTO] Analizando posiciones del portfolio {portfolio_id}")

    try:
        # Actualizar precios
        await update_all_prices(portfolio_id)

        # Generar señales
        signals = await generate_signals_for_portfolio(portfolio_id)

        # Comprobar alertas SL/TP
        alerts = await check_alerts(portfolio_id)

        # Notificar señales accionables
        if config.notify_signals:
            actionable = [s for s in signals if s.get("type") in ("BUY", "SELL")]
            if actionable:
                text = "🤖 *MODO AUTO — Señales*\n\n"
                for s in actionable:
                    emoji = "🟢" if s["type"] == "BUY" else "🔴"
                    price_str = f"{s['price']:.2f}$" if s.get('price') else "N/A"
                    text += (
                        f"{emoji} *${s['ticker']}* → {s['type']} | Precio: {price_str}\n"
                        f"   {s.get('reason', s.get('reasoning', 'N/A')[:80])}\n"
                    )
                    if s.get("pnl_pct") is not None:
                        text += f"   PnL: {s['pnl_pct']}%\n"
                    text += "\n"
                await _notify(text)

            # Alertas SL/TP
            if alerts:
                text = "🤖 *MODO AUTO — ⚠️ Alertas*\n\n"
                for a in alerts:
                    text += (
                        f"{a['type']} *${a['ticker']}*\n"
                        f"   Precio: {a['current_price']}$ | PnL: {a['pnl_pct']}%\n\n"
                    )
                await _notify(text)

    except Exception as e:
        logger.error(f"Error en auto_analyze_positions: {e}")


async def _auto_manage_watchlist(portfolio_id: int, config) -> None:
    """Gestiona la watchlist automáticamente (sin notificar; se ve con /watchlist o resumen diario)."""
    try:
        watchlist = await repo.get_active_watchlist()

        # Si la watchlist está vacía, generar nuevas sugerencias
        if not watchlist:
            portfolio = await repo.get_portfolio(portfolio_id)
            if portfolio is None:
                return
            positions = await repo.get_open_positions(portfolio_id)
            portfolio_tickers = [p.ticker for p in positions]
            await ai_generate_watchlist(portfolio_tickers)
            return

        # Re-analizar watchlist existente (actualiza scores en silencio)
        await refresh_watchlist_analysis()

    except Exception as e:
        logger.error(f"Error en auto_manage_watchlist: {e}")


# ── Resumen diario ───────────────────────────────────────────


async def _check_daily_summary(config, now: datetime) -> None:
    """Comprueba si es hora de enviar el resumen diario."""
    spain_tz = ZoneInfo(TIMEZONE)
    now_spain = now.astimezone(spain_tz)

    target_hour = config.daily_summary_hour
    target_minute = config.daily_summary_minute

    # Comprobar si ya se envió hoy
    if config.last_daily_summary_at:
        last_spain = config.last_daily_summary_at.astimezone(spain_tz)
        if last_spain.date() == now_spain.date():
            return  # Ya se envió hoy

    # Comprobar si es la hora correcta (ventana de 5 min, sin disparar antes)
    target_time = now_spain.replace(
        hour=target_hour, minute=target_minute, second=0, microsecond=0
    )
    window_end = target_time + timedelta(minutes=5)
    if target_time <= now_spain <= window_end:
        await _send_daily_summary(config.portfolio_id)
        await repo.update_auto_mode_timestamps(
            config.portfolio_id, last_daily_summary_at=now
        )


async def _send_daily_summary(portfolio_id: int) -> None:
    """Genera y envía el resumen diario completo."""
    logger.info(f"🤖 [AUTO] Generando resumen diario para portfolio {portfolio_id}")

    spain_tz = ZoneInfo(TIMEZONE)
    now_spain = datetime.now(spain_tz)

    text = "🤖 *RESUMEN DIARIO — Modo Auto*\n"
    text += f"📅 {now_spain.strftime('%d/%m/%Y %H:%M')} (hora España)\n"
    text += "=" * 35 + "\n\n"

    # ── 1. Estado de la cartera ──
    portfolio = await repo.get_portfolio(portfolio_id)
    if portfolio is None:
        return

    strategy = portfolio.strategy.value if portfolio.strategy else "value"
    text += f"📋 *Estrategia activa:* {strategy.upper()}\n\n"

    summary = await get_portfolio_summary(portfolio_id)
    text += (
        f"💰 *CARTERA {portfolio.name.upper()}*\n"
        f"   Valor: {summary['total_value']:,.2f}$\n"
        f"   Invertido: {summary['total_invested']:,.2f}$\n"
        f"   PnL: {summary['total_pnl']:+,.2f}$ ({summary['total_pnl_pct']:+.2f}%)\n"
        f"   Posiciones: {summary['num_positions']}\n\n"
    )

    # Detalle de posiciones
    if summary["positions"]:
        text += "*Posiciones:*\n"
        for p in summary["positions"]:
            emoji = "🟢" if p["pnl"] >= 0 else "🔴"
            alert = ""
            if p.get("stop_loss_hit"):
                alert = " ⚠️ SL!"
            elif p.get("take_profit_hit"):
                alert = " 🎯 TP!"
            text += (
                f"  {emoji} {p['ticker']} — {p['pnl']:+.2f}$ "
                f"({p['pnl_pct']:+.1f}%) | Peso: {p['weight_pct']:.1f}%{alert}\n"
            )
        text += "\n"

    # Concentración sectorial
    if summary.get("sector_weights"):
        text += "*Sectores:*\n"
        for sector, weight in sorted(
            summary["sector_weights"].items(), key=lambda x: -x[1]
        ):
            bar = "█" * int(weight / 5) if weight > 0 else ""
            text += f"  {sector.replace('_', ' ')}: {weight:.1f}% {bar}\n"
        text += "\n"

    # ── 2. Señales del día anterior ──
    yesterday_utc = datetime.now(UTC) - timedelta(days=1)
    signals = await repo.get_signals_since(yesterday_utc)
    if signals:
        text += f"📡 *Señales últimas 24h ({len(signals)}):*\n"
        for sig in signals[:10]:
            emoji = "🟢" if sig.signal_type.value == "BUY" else "🔴" if sig.signal_type.value == "SELL" else "🟡"
            price_str = f" | {sig.price:.2f}$" if sig.price else ""
            text += (
                f"  {emoji} {sig.ticker} → {sig.signal_type.value}{price_str}"
            )
            if sig.value_score:
                text += f" (Score: {sig.value_score:.0f})"
            text += "\n"
        text += "\n"
    else:
        text += "📡 _Sin señales en las últimas 24h_\n\n"

    # ── 3. Estado de la watchlist ──
    watchlist = await repo.get_active_watchlist()
    if watchlist:
        text += f"📋 *Watchlist ({len(watchlist)}/5):*\n"
        for w in watchlist:
            text += f"  📌 {w.ticker} ({market_display(w.market)}) — {w.reason or 'En estudio'}\n"
        text += "\n"
    else:
        text += "📋 _Watchlist vacía_\n\n"

    # ── 4. Próximos earnings ──
    positions = await repo.get_open_positions(portfolio_id)
    tickers = [(p.ticker, p.market) for p in positions]
    if tickers:
        from data.earnings import check_upcoming_earnings
        upcoming = await check_upcoming_earnings(tickers)
        near = [e for e in upcoming if e.get("days_until") is not None and e["days_until"] <= 14]
        if near:
            text += "📅 *Earnings próximos (14 días):*\n"
            for e in near:
                mkt = e.get("market")
                mkt_str = f" ({market_display(mkt)})" if mkt else ""
                text += f"  {e['ticker']}{mkt_str} en {e['days_until']} días\n"
            text += "\n"

    # ── 5. Análisis financiero IA ──
    try:
        from ai.analyst import _call_llm
        # Resumen compacto de posiciones (no enviar JSON completo)
        pos_summary = ""
        for p in summary.get("positions", []):
            pos_summary += f"  ${p['ticker']}: PnL {p['pnl_pct']:+.1f}%, peso {p['weight_pct']:.1f}%\n"

        sector_str = ", ".join(
            f"{s}:{w:.0f}%" for s, w in sorted(
                summary.get("sector_weights", {}).items(), key=lambda x: -x[1]
            )[:5]
        )

        analysis_prompt = f"""Análisis breve de cartera {strategy}:
Valor: {summary['total_value']:,.0f}$ | Invertido: {summary['total_invested']:,.0f}$ | PnL: {summary['total_pnl_pct']:+.1f}%
Posiciones ({summary['num_positions']}):
{pos_summary}Sectores: {sector_str}

Responde (máx 150 palabras):
1. Evaluación del rendimiento
2. Riesgo de concentración
3. Posiciones que requieren atención
4. Recomendación para hoy
"""
        ai_analysis = await _call_llm(analysis_prompt, max_tokens=400)
        text += f"🧠 *Análisis IA:*\n{ai_analysis}\n"
    except Exception as e:
        logger.warning(f"Error en análisis IA del resumen diario: {e}")

    text += f"\n⚙️ _Modo auto activo | /auto off para desactivar_"

    await _notify(text)
