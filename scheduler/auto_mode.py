"""
Modo Automático – ejecuta ciclos periódicos de análisis completo:
  • Scan de oportunidades value
  • Análisis macro/geopolítico
  • Re-análisis de posiciones abiertas
  • Gestión automática de watchlist
  • Resumen diario a las 9:00 (hora España)
  • Envío de señales relevantes por Telegram

Se configura con /auto on|off|safe y /auto config.

Modos:
  • OFF  – desactivado
  • ON   – full auto, ejecuta operaciones sin intervención
  • SAFE – auto con confirmación, pide aprobación antes de operar
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from ai.analyst import analyze_with_context, get_macro_analysis, get_deep_macro_analysis
from ai.watchlist import ai_generate_watchlist, refresh_watchlist_analysis
from broker.bridge import (
    get_broker_account_cash,
    sync_cash_from_broker,
)
from config import settings
from config.markets import market_display, MARKET_CURRENCY, format_price, get_currency_symbol
from config.settings import ACCOUNT_CURRENCY, TIMEZONE
from data.market_data import get_open_markets, is_market_open, is_any_trading_day, refresh_broker_prices
from data.news import save_context_snapshot
from database import repository as repo
from database.models import AutoModeType, OperationOrigin, PortfolioType
from portfolio.portfolio_manager import (
    check_alerts,
    execute_buy,
    execute_sell,
    get_portfolio_summary,
    update_all_prices,
)
from notifications import notify as _notify, notify_with_buttons, set_notification_bot
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

    # ── Comprobar si hoy es día de trading y si hay mercados abiertos ──
    trading_day = is_any_trading_day()
    open_markets = get_open_markets()
    markets_open = len(open_markets) > 0

    # Si no es día de trading, solo permitimos el resumen diario
    if not trading_day:
        await _check_daily_summary(config, now)
        return

    # ── Sync con Trading212 al inicio de cada ciclo (siempre en día de trading) ──
    await _auto_sync_broker(portfolio_id)

    # ── Scan de oportunidades (solo con mercados abiertos) ──
    if markets_open and _should_run(config.last_scan_at, config.scan_interval_minutes, now):
        await _auto_scan(portfolio_id, config.mode)
        await repo.update_auto_mode_timestamps(
            portfolio_id, last_scan_at=now
        )

    # ── Análisis macro profundo (solo en días de trading: apertura ~7:30 y cierre ~18:00) ──
    macro_session = _get_macro_session(now)
    if macro_session and _should_run_macro_session(config, now, macro_session):
        await _auto_macro(portfolio_id, session=macro_session)
        await repo.update_auto_mode_timestamps(
            portfolio_id, last_macro_at=now
        )

    # ── Re-análisis de posiciones (solo con mercados abiertos) ──
    if markets_open and _should_run(
        config.last_analyze_at, config.analyze_interval_minutes, now
    ):
        await _auto_analyze_positions(portfolio_id, config)
        await repo.update_auto_mode_timestamps(
            portfolio_id, last_analyze_at=now
        )

    # ── Gestión de watchlist (solo con mercados abiertos) ──
    if config.watchlist_auto_manage and markets_open:
        last_wl = _last_watchlist_run.get(portfolio_id)
        if _should_run(last_wl, config.scan_interval_minutes, now):
            await _auto_manage_watchlist(portfolio_id, config)
            _last_watchlist_run[portfolio_id] = now

    # ── Resumen diario (siempre) ──
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


# Ventanas horarias para el macro profundo (hora local TIMEZONE)
_MACRO_MORNING_WINDOW = (7, 15, 8, 30)   # 7:15 – 8:30 (pre-apertura EU)
_MACRO_EVENING_WINDOW = (17, 30, 19, 0)  # 17:30 – 19:00 (post-cierre EU)


def _get_macro_session(now: datetime) -> str | None:
    """Devuelve 'apertura' o 'cierre' si estamos en ventana macro, None si no."""
    spain_tz = ZoneInfo(TIMEZONE)
    local = now.astimezone(spain_tz)
    t = local.hour * 60 + local.minute  # minutos desde medianoche

    morning_start = _MACRO_MORNING_WINDOW[0] * 60 + _MACRO_MORNING_WINDOW[1]
    morning_end = _MACRO_MORNING_WINDOW[2] * 60 + _MACRO_MORNING_WINDOW[3]
    evening_start = _MACRO_EVENING_WINDOW[0] * 60 + _MACRO_EVENING_WINDOW[1]
    evening_end = _MACRO_EVENING_WINDOW[2] * 60 + _MACRO_EVENING_WINDOW[3]

    if morning_start <= t <= morning_end:
        return "apertura"
    if evening_start <= t <= evening_end:
        return "cierre"
    return None


def _should_run_macro_session(config, now: datetime, session: str) -> bool:
    """Comprueba si el macro de esta sesión ya se ejecutó hoy."""
    spain_tz = ZoneInfo(TIMEZONE)
    local_now = now.astimezone(spain_tz)

    if config.last_macro_at is None:
        return True

    last_local = config.last_macro_at.astimezone(spain_tz)

    # Si la última ejecución fue otro día, siempre ejecutar
    if last_local.date() != local_now.date():
        return True

    # Mismo día: comprobar si ya se ejecutó en esta sesión
    last_t = last_local.hour * 60 + last_local.minute
    morning_start = _MACRO_MORNING_WINDOW[0] * 60 + _MACRO_MORNING_WINDOW[1]
    morning_end = _MACRO_MORNING_WINDOW[2] * 60 + _MACRO_MORNING_WINDOW[3]

    if session == "apertura":
        # Ya se ejecutó en la ventana de mañana hoy?
        return not (morning_start <= last_t <= morning_end)
    else:  # cierre
        # Ya se ejecutó en la ventana de tarde hoy?
        evening_start = _MACRO_EVENING_WINDOW[0] * 60 + _MACRO_EVENING_WINDOW[1]
        evening_end = _MACRO_EVENING_WINDOW[2] * 60 + _MACRO_EVENING_WINDOW[3]
        return not (evening_start <= last_t <= evening_end)


# ── Tareas automáticas ───────────────────────────────────────


async def _auto_sync_broker(portfolio_id: int) -> None:
    """
    Sincroniza precios y cash desde Trading212 al inicio del ciclo auto.
    Silencioso: no notifica al usuario, solo actualiza datos internos.
    """
    try:
        # Refrescar precios T212 para que get_prices_batch los use
        await refresh_broker_prices()
    except Exception as e:
        logger.debug(f"[AUTO] Error refrescando precios T212: {e}")

    try:
        # Sincronizar cash real del broker con la BD local
        portfolio = await repo.get_portfolio(portfolio_id)
        if portfolio and portfolio.portfolio_type == PortfolioType.REAL:
            result = await sync_cash_from_broker(portfolio_id)
            if result.get("success") and abs(result.get("diff", 0)) > 1.0:
                logger.info(
                    f"[AUTO] Cash sincronizado: "
                    f"{result['old_cash']:.2f} → {result['new_cash']:.2f}"
                )
    except Exception as e:
        logger.debug(f"[AUTO] Error sincronizando cash: {e}")


async def _auto_scan(portfolio_id: int, mode: AutoModeType) -> None:
    """Ejecuta un scan de oportunidades.

    - ON:   notifica y ejecuta compras automáticamente.
    - SAFE: notifica y envía botones de confirmación.
    """
    logger.info(f"🤖 [AUTO-{mode.value.upper()}] Escaneando oportunidades para portfolio {portfolio_id}")

    try:
        opportunities = await scan_opportunities(
            max_results=5, portfolio_id=portfolio_id
        )
        if not opportunities:
            return

        # Filtrar solo BUY con score alto
        strong = [o for o in opportunities if o["signal"] == "BUY" and o["overall_score"] >= settings.SIGNAL_BUY_THRESHOLD]
        if not strong:
            return

        # ── Persistir análisis de scan para aprendizaje ──
        for opp in strong:
            try:
                from database.models import AnalysisLog
                reasoning_list = opp.get("reasoning", [])
                reasoning_text = "\n".join(reasoning_list) if isinstance(reasoning_list, list) else str(reasoning_list)
                log = AnalysisLog(
                    ticker=opp.get("ticker", ""),
                    market=opp.get("market", "NASDAQ"),
                    strategy_used=str(opp.get("strategy", "")),
                    signal=opp.get("signal", "BUY"),
                    overall_score=opp.get("overall_score"),
                    value_score=opp.get("value_score"),
                    quality_score=opp.get("quality_score"),
                    safety_score=opp.get("safety_score"),
                    price_at_analysis=opp.get("price"),
                    margin_of_safety=opp.get("margin_of_safety"),
                    pe_ratio=opp.get("pe_ratio"),
                    roe=opp.get("roe"),
                    debt_to_equity=opp.get("debt_to_equity"),
                    dividend_yield=opp.get("dividend_yield"),
                    reasoning=reasoning_text,
                    tech_summary=opp.get("tech_summary", ""),
                    price_summary=opp.get("price_summary", ""),
                    source="auto",
                )
                await repo.save_analysis_log(log)
            except Exception as e:
                logger.debug(f"Error guardando análisis auto de {opp.get('ticker')}: {e}")

        mode_label = "🟢 ON" if mode == AutoModeType.ON else "🛡️ SAFE"
        text = f"🤖 *MODO AUTO ({mode_label}) — Oportunidades detectadas*\n\n"
        for i, opp in enumerate(strong, 1):
            opp_ccy = MARKET_CURRENCY.get(opp.get('market', 'NASDAQ'), 'USD')
            price_str = format_price(opp['price'], opp_ccy) if opp.get('price') else "N/A"
            text += (
                f"{i}. 🟢 *{opp['ticker']}* — Score: {opp['overall_score']:.0f}/100 | Precio: {price_str}\n"
                f"   V:{opp['value_score']:.0f} Q:{opp['quality_score']:.0f} S:{opp['safety_score']:.0f}\n"
                f"   MoS: {opp.get('margin_of_safety', 'N/A')}%\n\n"
            )

        if mode == AutoModeType.ON:
            # Full auto: ejecutar compras y notificar resultado
            for opp in strong:
                await _auto_execute_buy(portfolio_id, opp)
            text += "_Operaciones ejecutadas automáticamente._\n"
            await _notify(text)

        elif mode == AutoModeType.SAFE:
            # Safe: enviar cada oportunidad con botones de confirmación
            await _notify(text)
            for opp in strong:
                await _send_buy_confirmation(portfolio_id, opp)

    except Exception as e:
        logger.error(f"Error en auto_scan: {e}")


async def _auto_macro(portfolio_id: int, session: str = "apertura") -> None:
    """Ejecuta análisis macro profundo y guarda contexto.

    Se ejecuta dos veces al día: pre-apertura (~7:30) y post-cierre (~18:00).
    Genera un análisis detallado con contexto geopolítico, sectorial,
    flujos de mercado y recomendaciones de exposición.
    """
    logger.info(f"🤖 [AUTO] Análisis macro profundo ({session}) para portfolio {portfolio_id}")
    try:
        # Guardar contexto antes del análisis
        await save_context_snapshot()

        # Obtener resumen del portfolio para contextualizar
        portfolio_summary = None
        try:
            portfolio_summary = await get_portfolio_summary(portfolio_id)
        except Exception:
            pass

        # Obtener estrategia activa
        strategy = None
        try:
            portfolio = await repo.get_portfolio(portfolio_id)
            if portfolio and portfolio.strategy:
                strategy = portfolio.strategy.value if hasattr(portfolio.strategy, 'value') else str(portfolio.strategy)
        except Exception:
            pass

        macro = await get_deep_macro_analysis(
            strategy=strategy,
            session=session,
            portfolio_summary=portfolio_summary,
        )
        if macro and "Error" not in macro:
            session_emoji = "🌅" if session == "apertura" else "🌆"
            text = (
                f"🤖 *MODO AUTO — Análisis Macro Profundo*\n"
                f"{session_emoji} *Sesión de {session.upper()}*\n"
                f"{'=' * 35}\n\n"
                f"{macro}"
            )
            await _notify(text)
    except Exception as e:
        logger.error(f"Error en auto_macro ({session}): {e}")


async def _auto_analyze_positions(portfolio_id: int, config) -> None:
    """Re-analiza todas las posiciones y envía señales activas.

    - ON:   ejecuta ventas automáticamente si hay señal SELL.
    - SAFE: envía señales con botones de confirmación.
    """
    mode = config.mode
    logger.info(f"🤖 [AUTO-{mode.value.upper()}] Analizando posiciones del portfolio {portfolio_id}")

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
                mode_label = "🟢 ON" if mode == AutoModeType.ON else "🛡️ SAFE"
                text = f"🤖 *MODO AUTO ({mode_label}) — Señales*\n\n"
                for s in actionable:
                    emoji = "🟢" if s["type"] == "BUY" else "🔴"
                    sig_ccy = MARKET_CURRENCY.get(s.get('market', 'NASDAQ'), 'USD')
                    price_str = format_price(s['price'], sig_ccy) if s.get('price') else "N/A"
                    score_val = s.get('overall_score', s.get('score'))
                    score_str = f" | Score: {score_val:.0f}" if score_val else ""
                    text += f"{emoji} *{s['ticker']}* → {s['type']} | Precio: {price_str}{score_str}\n"
                    if s.get("pnl_pct") is not None:
                        text += f"   💰 PnL: {s['pnl_pct']}%\n"
                    # Mostrar campos estructurados relevantes
                    if s.get("margin_of_safety"):
                        text += f"   📏 MoS: {s['margin_of_safety']}%\n"
                    reason_line = s.get('reason') or s.get('reasoning')
                    if reason_line:
                        # Primera frase como resumen
                        first_sentence = reason_line.split('.')[0].strip()
                        if first_sentence:
                            text += f"   📝 {first_sentence}.\n"
                    text += "\n"

                if mode == AutoModeType.ON:
                    # Full auto: ejecutar operaciones
                    for s in actionable:
                        if s["type"] == "SELL":
                            await _auto_execute_sell(portfolio_id, s)
                        elif s["type"] == "BUY":
                            await _auto_execute_buy(portfolio_id, s)
                    text += "_Operaciones ejecutadas automáticamente._\n"
                    await _notify(text)

                elif mode == AutoModeType.SAFE:
                    # Safe: notificar y pedir confirmación
                    await _notify(text)
                    for s in actionable:
                        if s["type"] == "SELL":
                            await _send_sell_confirmation(portfolio_id, s)
                        elif s["type"] == "BUY":
                            await _send_buy_confirmation(portfolio_id, s)

            # Alertas SL/TP
            if alerts:
                text = f"🤖 *MODO AUTO — ⚠️ Alertas*\n\n"
                for a in alerts:
                    aa_ccy = MARKET_CURRENCY.get(a.get('market', 'NASDAQ'), 'USD')
                    text += (
                        f"{a['type']} *{a['ticker']}*\n"
                        f"   Precio: {format_price(a['current_price'], aa_ccy)} | PnL: {a['pnl_pct']}%\n\n"
                    )
                await _notify(text)

    except Exception as e:
        logger.error(f"Error en auto_analyze_positions: {e}")


# ── Ejecución automática (modo ON) ──────────────────────────


async def _auto_execute_buy(portfolio_id: int, signal: dict) -> None:
    """Ejecuta una compra automática basada en una señal."""
    ticker = signal.get("ticker", "")
    price = signal.get("price")
    market = signal.get("market", "NASDAQ")
    if not ticker or not price:
        return

    # Guard: no operar si el mercado del ticker está cerrado
    if not is_market_open(market):
        logger.info(f"[AUTO-ON] Mercado {market} cerrado, compra de {ticker} aplazada")
        return

    try:
        # Calcular tamaño de posición basado en el portfolio
        portfolio = await repo.get_portfolio(portfolio_id)
        if portfolio is None or portfolio.cash <= 0:
            logger.warning(f"[AUTO-ON] Sin cash disponible para comprar {ticker}")
            return

        # Usar un máximo del 5% del valor total o el cash disponible
        summary = await get_portfolio_summary(portfolio_id)
        max_amount = min(
            portfolio.cash,
            summary["total_value"] * 0.05,
        )
        if max_amount < 10:
            return

        shares = max_amount / price
        result = await execute_buy(
            portfolio_id=portfolio_id,
            ticker=ticker,
            market=market,
            price=price,
            shares=shares,
            origin=OperationOrigin.AUTO,
        )

        if result["success"]:
            buy_ccy = MARKET_CURRENCY.get(market, 'USD')
            text = (
                f"🤖 *AUTO-ON — Compra ejecutada* ✅\n\n"
                f"📌 *{ticker}* ({market})\n"
                f"💵 Precio: {format_price(price, buy_ccy)}\n"
                f"📊 Acciones: {result.get('shares', shares):.4f}\n"
                f"💰 Total: {format_price(result.get('amount', 0), buy_ccy)}\n"
            )
            if result.get("broker_executed"):
                text += "🏦 Broker: Trading212 ✅\n"
            await _notify(text)
        else:
            logger.error(f"[AUTO-ON] Error comprando {ticker}: {result.get('error')}")
            await _notify(f"🤖 ❌ AUTO-ON — Error comprando *{ticker}*: {result.get('error')}")

    except Exception as e:
        logger.error(f"[AUTO-ON] Excepción comprando {ticker}: {e}")


async def _auto_execute_sell(portfolio_id: int, signal: dict) -> None:
    """Ejecuta una venta automática basada en una señal."""
    ticker = signal.get("ticker", "")
    price = signal.get("price")
    market = signal.get("market", "NASDAQ")
    if not ticker or not price:
        return

    # Guard: no operar si el mercado del ticker está cerrado
    if not is_market_open(market):
        logger.info(f"[AUTO-ON] Mercado {market} cerrado, venta de {ticker} aplazada")
        return

    try:
        # Obtener posición actual
        positions = await repo.get_open_positions(portfolio_id)
        position = next((p for p in positions if p.ticker == ticker), None)
        if position is None or position.shares <= 0:
            return

        result = await execute_sell(
            portfolio_id=portfolio_id,
            ticker=ticker,
            market=market,
            price=price,
            shares_to_sell=position.shares,  # Venta total
            origin=OperationOrigin.AUTO,
        )

        if result["success"]:
            pnl = result.get("pnl", 0)
            pnl_pct = result.get("pnl_pct", 0)
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            sell_ccy = MARKET_CURRENCY.get(market, 'USD')
            sell_sym = get_currency_symbol(sell_ccy)
            text = (
                f"🤖 *AUTO-ON — Venta ejecutada* ✅\n\n"
                f"📌 *{ticker}* ({market})\n"
                f"💵 Precio: {format_price(price, sell_ccy)}\n"
                f"📊 Acciones: {result.get('shares_sold', position.shares):.4f}\n"
                f"{pnl_emoji} PnL: {pnl:+.2f}{sell_sym} ({pnl_pct:+.2f}%)\n"
            )
            if result.get("broker_executed"):
                text += "🏦 Broker: Trading212 ✅\n"
            await _notify(text)
        else:
            logger.error(f"[AUTO-ON] Error vendiendo {ticker}: {result.get('error')}")
            await _notify(f"🤖 ❌ AUTO-ON — Error vendiendo *{ticker}*: {result.get('error')}")

    except Exception as e:
        logger.error(f"[AUTO-ON] Excepción vendiendo {ticker}: {e}")


# ── Confirmación interactiva (modo SAFE) ────────────────────


async def _send_buy_confirmation(portfolio_id: int, signal: dict) -> None:
    """Envía un mensaje con botones para confirmar/rechazar una compra."""
    ticker = signal.get("ticker", "")
    price = signal.get("price")
    market = signal.get("market", "NASDAQ")
    score = signal.get("overall_score", signal.get("score", "?"))
    if not ticker or not price:
        return

    # Calcular monto sugerido (5% del portfolio)
    try:
        portfolio = await repo.get_portfolio(portfolio_id)
        if portfolio is None or portfolio.cash <= 0:
            return
        summary = await get_portfolio_summary(portfolio_id)
        amount = min(portfolio.cash, summary["total_value"] * 0.05)
        shares = amount / price
    except Exception:
        shares = 0
        amount = 0

    safe_buy_ccy = MARKET_CURRENCY.get(market, 'USD')
    text = (
        f"🛡️ *MODO SAFE — ¿Confirmar COMPRA?*\n\n"
        f"📌 *{ticker}* ({market})\n"
        f"💵 Precio: {format_price(price, safe_buy_ccy)}\n"
        f"📊 Acciones: ~{shares:.4f} (~{format_price(amount, safe_buy_ccy)})\n"
        f"⭐ Score: {score}\n"
    )
    reason = signal.get("reasoning", signal.get("reason", ""))
    if reason:
        first_sentence = reason.split('.')[0].strip()
        if first_sentence:
            text += f"📝 {first_sentence}.\n"
    if signal.get("margin_of_safety"):
        text += f"📏 MoS: {signal['margin_of_safety']}%\n"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Comprar",
                callback_data=f"auto_buy:{ticker}:{market}:{shares:.6f}:{price:.2f}",
            ),
            InlineKeyboardButton("❌ Rechazar", callback_data="auto_reject"),
        ]
    ])
    await notify_with_buttons(text, reply_markup=keyboard)


async def _send_sell_confirmation(portfolio_id: int, signal: dict) -> None:
    """Envía un mensaje con botones para confirmar/rechazar una venta."""
    ticker = signal.get("ticker", "")
    price = signal.get("price")
    market = signal.get("market", "NASDAQ")
    if not ticker or not price:
        return

    # Obtener posición
    try:
        positions = await repo.get_open_positions(portfolio_id)
        position = next((p for p in positions if p.ticker == ticker), None)
        if position is None or position.shares <= 0:
            return
        shares = position.shares
        pnl_pct = ((price - position.avg_price) / position.avg_price * 100) if position.avg_price else 0
    except Exception:
        shares = 0
        pnl_pct = 0

    pnl_emoji = "🟢" if pnl_pct >= 0 else "🔴"
    safe_sell_ccy = MARKET_CURRENCY.get(market, 'USD')
    text = (
        f"🛡️ *MODO SAFE — ¿Confirmar VENTA?*\n\n"
        f"📌 *{ticker}* ({market})\n"
        f"💵 Precio: {format_price(price, safe_sell_ccy)}\n"
        f"📊 Acciones: {shares:.4f}\n"
        f"{pnl_emoji} PnL estimado: {pnl_pct:+.2f}%\n"
    )
    reason = signal.get("reasoning", signal.get("reason", ""))
    if reason:
        first_sentence = reason.split('.')[0].strip()
        if first_sentence:
            text += f"📝 {first_sentence}.\n"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Vender",
                callback_data=f"auto_sell:{ticker}:{market}:{shares:.6f}:{price:.2f}",
            ),
            InlineKeyboardButton("❌ Rechazar", callback_data="auto_reject"),
        ]
    ])
    await notify_with_buttons(text, reply_markup=keyboard)


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
    acct_ccy = summary.get('account_currency', ACCOUNT_CURRENCY)
    acct_sym = get_currency_symbol(acct_ccy)
    text += (
        f"💰 *CARTERA {portfolio.name.upper()}*\n"
        f"   Valor: {summary['total_value']:,.2f}{acct_sym}\n"
        f"   Invertido: {summary['total_invested']:,.2f}{acct_sym}\n"
        f"   PnL: {summary['total_pnl']:+,.2f}{acct_sym} ({summary['total_pnl_pct']:+.2f}%)\n"
        f"   Posiciones: {summary['num_positions']}\n"
    )

    # Datos de cuenta T212 (cash real, PnL real)
    broker_acc = await get_broker_account_cash()
    if broker_acc:
        text += (
            f"\n🏦 *Trading212 ({broker_acc.get('currency', 'EUR')})*\n"
            f"   Cash real: {broker_acc['cash']:,.2f}\n"
            f"   Invertido: {broker_acc['invested']:,.2f}\n"
            f"   Valor total: {broker_acc['portfolio_value']:,.2f}\n"
            f"   PnL broker: {broker_acc['pnl']:+,.2f} ({broker_acc.get('pnl_pct', 0):+.2f}%)\n"
        )
    text += "\n"

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
            pos_ccy = p.get('currency', MARKET_CURRENCY.get(p.get('market', 'NASDAQ'), 'USD'))
            pos_sym = get_currency_symbol(pos_ccy)
            text += (
                f"  {emoji} {p['ticker']} — {p['pnl']:+.2f}{pos_sym} "
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
            if sig.price:
                sig_mkt = getattr(sig, 'market', None) or 'NASDAQ'
                sig_ccy = MARKET_CURRENCY.get(sig_mkt, 'USD')
                price_str = f" | {format_price(sig.price, sig_ccy)}"
            else:
                price_str = ""
            text += (
                f"  {emoji} {sig.ticker} → {sig.signal_type.value}{price_str}"
            )
            if sig.value_score:
                text += f" (Score: {sig.value_score:.0f})"
            text += "\n"
        text += "\n"
    else:
        text += "📡 _Sin señales en las últimas 24h_\n\n"

    # ── 3. Estado de la watchlist (resumen: ticker + mercado + sector) ──
    watchlist = await repo.get_active_watchlist()
    if watchlist:
        text += f"📋 *Watchlist ({len(watchlist)}/25):*\n"
        for w in watchlist:
            sector_str = f" | {w.sector}" if w.sector else ""
            text += f"  📌 {w.ticker} ({market_display(w.market)}){sector_str}\n"
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
            pos_summary += f"  {p['ticker']}: PnL {p['pnl_pct']:+.1f}%, peso {p['weight_pct']:.1f}%\n"

        sector_str = ", ".join(
            f"{s}:{w:.0f}%" for s, w in sorted(
                summary.get("sector_weights", {}).items(), key=lambda x: -x[1]
            )[:5]
        )

        analysis_prompt = f"""Análisis breve de cartera {strategy}:
Valor: {summary['total_value']:,.0f}{acct_sym} | Invertido: {summary['total_invested']:,.0f}{acct_sym} | PnL: {summary['total_pnl_pct']:+.1f}%
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

    # Obtener config para mostrar el modo
    config = await repo.get_auto_mode_config(portfolio_id)
    mode_str = config.mode.value.upper() if config else "ON"
    text += f"\n⚙️ _Modo auto {mode_str} activo | /auto off para desactivar_"

    await _notify(text)
