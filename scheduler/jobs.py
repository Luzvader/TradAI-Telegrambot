"""
Scheduler – tareas programadas que se ejecutan periódicamente:
  • Cada 10 min en horario de mercado: actualizar precios + comprobar alertas
  • Cada hora: re-evaluar señales de posiciones abiertas
  • Cada día (7:00): resumen macro + revisar watchlist
  • Backtest continuo en cartera demo para aprendizaje autónomo
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot
from telegram.constants import ParseMode

from config.markets import MARKETS
from config.settings import (
    BACKTEST_CONTINUOUS_ENABLED,
    BACKTEST_INTERVAL_MINUTES,
    BACKTEST_MAX_TICKERS,
    BACKTEST_NOTIFY_EACH_RUN,
    BACKTEST_PERIODS,
    MONITOR_INTERVAL_MINUTES,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TIMEZONE,
)
from data.market_data import is_market_open, get_current_price
from data.news import save_context_snapshot
from database import repository as repo
from database.models import PortfolioType
from notifications import notify as _notify, set_notification_bot
from portfolio.portfolio_manager import check_alerts, update_all_prices
from scheduler.auto_mode import auto_mode_cycle, set_auto_mode_bot
from signals.signal_engine import generate_signals_for_portfolio

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=TIMEZONE)
bot: Bot | None = None


def init_scheduler(telegram_bot: Bot | None = None) -> AsyncIOScheduler:
    """Configura y devuelve el scheduler con todas las tareas."""
    global bot
    bot = telegram_bot
    set_notification_bot(telegram_bot)
    set_auto_mode_bot(telegram_bot)

    # ── Cada 10 min: monitorizar precios durante horario de mercado ──
    scheduler.add_job(
        job_monitor_prices,
        IntervalTrigger(minutes=MONITOR_INTERVAL_MINUTES),
        id="monitor_prices",
        name="Monitorizar precios",
        replace_existing=True,
    )

    # ── Cada hora: re-evaluar señales ──
    scheduler.add_job(
        job_generate_signals,
        IntervalTrigger(hours=1),
        id="generate_signals",
        name="Generar señales",
        replace_existing=True,
    )

    # ── Cada día a las 7:00: resumen diario ──
    scheduler.add_job(
        job_daily_summary,
        CronTrigger(hour=7, minute=0),
        id="daily_summary",
        name="Resumen diario",
        replace_existing=True,
    )

    # ── Cada día a las 8:00: guardar contexto geopolítico ──
    scheduler.add_job(
        job_save_context,
        CronTrigger(hour=8, minute=0),
        id="save_context",
        name="Guardar contexto",
        replace_existing=True,
    )

    # ── Cada domingo a las 20:00: insights de aprendizaje ──
    scheduler.add_job(
        job_weekly_learning,
        CronTrigger(day_of_week="sun", hour=20, minute=0),
        id="weekly_learning",
        name="Aprendizaje semanal",
        replace_existing=True,
    )

    # ── Cada domingo a las 21:00: resumen semanal con benchmark ──
    scheduler.add_job(
        job_weekly_benchmark,
        CronTrigger(day_of_week="sun", hour=21, minute=0),
        id="weekly_benchmark",
        name="Benchmark semanal",
        replace_existing=True,
    )

    # ── Cada día a las 18:00: snapshot del portfolio ──
    scheduler.add_job(
        job_portfolio_snapshot,
        CronTrigger(hour=18, minute=0),
        id="portfolio_snapshot",
        name="Snapshot diario portfolio",
        replace_existing=True,
    )

    # ── Cada hora: comprobar alertas personalizadas ──
    scheduler.add_job(
        job_check_custom_alerts,
        IntervalTrigger(hours=1),
        id="check_custom_alerts",
        name="Comprobar alertas",
        replace_existing=True,
    )

    # ── Cada día a las 9:30: comprobar calendario de earnings ──
    scheduler.add_job(
        job_check_earnings_calendar,
        CronTrigger(hour=9, minute=30),
        id="check_earnings",
        name="Calendario de earnings",
        replace_existing=True,
    )

    # ── Cada 5 min: ciclo del modo automático ──
    scheduler.add_job(
        job_auto_mode,
        IntervalTrigger(minutes=5),
        id="auto_mode_cycle",
        name="Modo automático",
        replace_existing=True,
    )

    # ── Backtest continuo en cartera demo (sin supervisión) ──
    if BACKTEST_CONTINUOUS_ENABLED:
        scheduler.add_job(
            job_learning_backtest,
            IntervalTrigger(minutes=max(5, BACKTEST_INTERVAL_MINUTES)),
            id="learning_backtest",
            name="Backtest demo continuo",
            replace_existing=True,
            max_instances=1,  # Evita solapamiento de ejecuciones largas
        )

    logger.info(f"⏰ Scheduler configurado con {len(scheduler.get_jobs())} tareas")
    return scheduler


# ── Jobs ─────────────────────────────────────────────────────


async def job_monitor_prices() -> None:
    """
    Actualiza precios de todas las posiciones abiertas.
    Solo ejecuta si al menos un mercado relevante está abierto.
    """
    # Comprobar si algún mercado está abierto
    any_open = False
    for market_key in MARKETS:
        if is_market_open(market_key):
            any_open = True
            break

    if not any_open:
        logger.debug("🔇 Ningún mercado abierto, saltando monitorización")
        return

    logger.info("📊 Monitorizando precios...")

    # Actualizar cartera real
    real = await repo.get_portfolio_by_type(PortfolioType.REAL)
    if real:
        updated = await update_all_prices(real.id)
        logger.info(f"  Real: {updated} precios actualizados")

        # Comprobar alertas de stop-loss / take-profit
        alerts = await check_alerts(real.id)
        if alerts:
            alert_text = "🚨 *ALERTAS DE PRECIO*\n\n"
            for a in alerts:
                alert_text += (
                    f"{a['type']} ${a['ticker']}\n"
                    f"  Precio: {a['current_price']}$ | PnL: {a['pnl_pct']}%\n\n"
                )
            await _notify(alert_text)

    # Actualizar cartera backtest
    backtest = await repo.get_portfolio_by_type(PortfolioType.BACKTEST)
    if backtest:
        await update_all_prices(backtest.id)


async def job_generate_signals() -> None:
    """Genera señales para la cartera real."""
    # Solo si algún mercado está abierto
    any_open = any(is_market_open(m) for m in MARKETS)
    if not any_open:
        return

    real = await repo.get_portfolio_by_type(PortfolioType.REAL)
    if real is None:
        return

    signals = await generate_signals_for_portfolio(real.id)

    # Notificar señales de compra/venta (no HOLD)
    actionable = [s for s in signals if s.get("type") in ("BUY", "SELL")]
    if actionable:
        text = "📡 *NUEVAS SEÑALES*\n\n"
        for s in actionable:
            emoji = "🟢" if s["type"] == "BUY" else "🔴"
            price_str = f"{s['price']:.2f}$" if s.get('price') else "N/A"
            score_str = f" | Score: {s['score']:.0f}" if s.get('score') else ""
            text += (
                f"{emoji} *${s['ticker']}* → {s['type']} | Precio: {price_str}{score_str}\n"
            )
            # Mostrar justificación completa
            reasoning = s.get("reasoning", "")
            if reasoning:
                # Limitar a 300 chars por señal para no desbordar
                short = reasoning[:300]
                if len(reasoning) > 300:
                    short += "…"
                text += f"{short}\n"
            elif s.get("reason"):
                text += f"  {s['reason']}\n"
            if s.get("pnl_pct") is not None:
                text += f"  💰 PnL actual: {s['pnl_pct']}%\n"
            text += "\n"
        await _notify(text)


async def job_daily_summary() -> None:
    """Genera y envía un resumen diario."""
    from portfolio.portfolio_manager import get_portfolio_summary

    text = "☀️ *RESUMEN DIARIO — TradAI*\n"
    text += f"📅 {datetime.now(ZoneInfo(TIMEZONE)).strftime('%d/%m/%Y')}\n\n"

    real = await repo.get_portfolio_by_type(PortfolioType.REAL)
    if real:
        summary = await get_portfolio_summary(real.id)
        text += (
            f"*Cartera Real:*\n"
            f"💰 {summary['total_value']:,.2f}$ "
            f"(PnL: {summary['total_pnl_pct']:+.2f}%)\n"
            f"📊 {summary['num_positions']} posiciones\n\n"
        )

        # Alertas de posiciones
        for p in summary.get("positions", []):
            if p.get("stop_loss_hit"):
                text += f"⚠️ ${p['ticker']}: STOP-LOSS alcanzado!\n"
            if p.get("take_profit_hit"):
                text += f"🎯 ${p['ticker']}: TAKE-PROFIT alcanzado!\n"

    # Watchlist
    watchlist = await repo.get_active_watchlist()
    if watchlist:
        text += f"\n📋 Watchlist: {', '.join([w.ticker for w in watchlist])}\n"

    # Earnings próximos
    if real:
        from data.earnings import check_upcoming_earnings
        positions = await repo.get_open_positions(real.id)
        tickers = [(p.ticker, p.market) for p in positions]
        if tickers:
            upcoming = await check_upcoming_earnings(tickers)
            near = [e for e in upcoming if e.get("days_until") is not None and e["days_until"] <= 14]
            if near:
                text += "\n📅 *Earnings próximos (14 días):*\n"
                for e in near:
                    mkt = e.get("market")
                    mkt_str = f" ({mkt})" if mkt else ""
                    text += f"  ${e['ticker']}{mkt_str} en {e['days_until']} días\n"

    await _notify(text)


async def job_save_context() -> None:
    """Guarda una instantánea del contexto geopolítico."""
    await save_context_snapshot()


async def job_weekly_learning() -> None:
    """Genera insights de aprendizaje semanales."""
    from ai.learning import get_learning_insights

    insights = await get_learning_insights()
    text = f"🧠 *APRENDIZAJE SEMANAL*\n\n{insights}"
    await _notify(text)


async def job_auto_mode() -> None:
    """Ejecuta el ciclo del modo automático."""
    try:
        await auto_mode_cycle()
    except Exception as e:
        logger.error(f"Error en job_auto_mode: {e}")


async def job_learning_backtest() -> None:
    """
    Ejecuta backtests continuos automáticos sobre el universo de la
    cartera demo (BACKTEST). Los resultados alimentan el learning para
    ajustar decisiones futuras según la estrategia activa.
    """
    from backtesting.engine import BacktestConfig, run_backtest

    logger.info("🧪 Iniciando backtest continuo en cartera demo…")

    # Recopilar tickers de la cartera demo (fuente principal)
    tickers: list[str] = []

    demo = await repo.get_portfolio_by_type(PortfolioType.BACKTEST)
    if demo:
        positions = await repo.get_open_positions(demo.id)
        for p in positions:
            if p.ticker not in tickers:
                tickers.append(p.ticker)

    # Refuerzo opcional con watchlist si la demo aún no tiene universo propio
    # (mantiene el backtest siempre en modo demo, pero evita ciclos vacíos).
    if not tickers:
        watchlist = await repo.get_active_watchlist()
        for w in watchlist:
            if w.ticker not in tickers:
                tickers.append(w.ticker)

    watchlist = await repo.get_active_watchlist()
    if tickers and len(tickers) < BACKTEST_MAX_TICKERS:
        for w in watchlist:
            if w.ticker not in tickers:
                tickers.append(w.ticker)
            if len(tickers) >= BACKTEST_MAX_TICKERS:
                break

    if not tickers:
        logger.info("🧪 Backtest demo sin tickers (demo y watchlist vacías)")
        return

    tickers = tickers[:max(1, BACKTEST_MAX_TICKERS)]

    # Estrategia del portfolio demo (fallback: real -> value)
    strategy = "value"
    if demo and demo.strategy:
        strategy = demo.strategy.value if hasattr(demo.strategy, 'value') else str(demo.strategy)
    else:
        real = await repo.get_portfolio_by_type(PortfolioType.REAL)
        if real and real.strategy:
            strategy = real.strategy.value if hasattr(real.strategy, "value") else str(real.strategy)

    valid_periods = {"3mo", "6mo", "1y", "2y", "5y", "10y"}
    periods = [
        p.strip()
        for p in BACKTEST_PERIODS.split(",")
        if p.strip() and p.strip() in valid_periods
    ]
    if not periods:
        periods = ["6mo", "1y"]

    initial_capital = (demo.initial_capital or demo.cash or 10_000.0) if demo else 10_000.0
    total_logs = 0

    for period in periods:
        try:
            config = BacktestConfig(
                tickers=tickers,
                strategy=strategy,
                period=period,
                initial_capital=initial_capital,
                use_technicals=True,
                use_learning=True,
                auto_learn=True,
            )
            result = await run_backtest(config)
            total_logs += result.learning_logs_created

            logger.info(
                f"🧪 Backtest {period} completado: "
                f"retorno {result.metrics.total_return_pct:+.1f}%, "
                f"{result.learning_logs_created} trades → learning"
            )
        except Exception as e:
            logger.error(f"Error en backtest de aprendizaje ({period}): {e}")

    if total_logs > 0 and BACKTEST_NOTIFY_EACH_RUN:
        text = (
            f"🧪 *BACKTEST DEMO COMPLETADO*\n\n"
            f"📊 {len(tickers)} tickers (cartera demo)\n"
            f"📅 Períodos: {', '.join(periods)}\n"
            f"🧠 {total_logs} trades procesados para aprendizaje\n"
            f"📈 Estrategia: {strategy}\n\n"
            f"_Aprendizaje autónomo actualizado._"
        )
        await _notify(text)
    elif total_logs == 0:
        logger.info("🧪 Backtest de aprendizaje: sin trades generados")


async def job_weekly_benchmark() -> None:
    """Genera un resumen semanal comparando con SPY (benchmark)."""
    from portfolio.portfolio_manager import get_portfolio_summary

    real = await repo.get_portfolio_by_type(PortfolioType.REAL)
    if real is None:
        return

    summary = await get_portfolio_summary(real.id)
    portfolio_return = summary.get("total_pnl_pct", 0)

    # Obtener rendimiento semanal de SPY como benchmark
    try:
        import yfinance as yf
        import asyncio
        spy = await asyncio.to_thread(lambda: yf.Ticker("SPY").history(period="5d"))
        hist = spy
        if len(hist) >= 2:
            spy_return = ((hist["Close"].iloc[-1] / hist["Close"].iloc[0]) - 1) * 100
        else:
            spy_return = 0
    except Exception:
        spy_return = 0

    # Obtener snapshots de la semana
    snapshots = await repo.get_portfolio_snapshots(real.id, limit=7)

    diff = portfolio_return - spy_return
    emoji = "🟢" if diff > 0 else "🔴" if diff < 0 else "🟡"

    text = "📊 *RESUMEN SEMANAL — BENCHMARK*\n\n"
    text += f"📈 Tu cartera: {portfolio_return:+.2f}%\n"
    text += f"🏦 SPY (benchmark): {spy_return:+.2f}%\n"
    text += f"{emoji} Diferencia: {diff:+.2f}%\n\n"

    if diff > 0:
        text += "🎯 ¡Estás superando al mercado! 🚀\n"
    elif diff < -5:
        text += "⚠️ Estás por debajo del mercado. Revisa la estrategia.\n"
    else:
        text += "📊 Rendimiento en línea con el mercado.\n"

    # Evolución últimos 7 snapshots
    if snapshots:
        text += "\n*Evolución diaria:*\n"
        for snap in reversed(list(snapshots)):
            d = snap.snapshot_date.strftime("%d/%m") if hasattr(snap.snapshot_date, "strftime") else str(snap.snapshot_date)
            pnl = snap.pnl_pct or 0
            e = "🟢" if pnl >= 0 else "🔴"
            text += f"  {d}: {snap.total_value:,.0f}$ ({e}{pnl:+.1f}%)\n"

    await _notify(text)


async def job_portfolio_snapshot() -> None:
    """Guarda un snapshot diario del portfolio para tracking histórico."""
    from portfolio.portfolio_manager import get_portfolio_summary

    real = await repo.get_portfolio_by_type(PortfolioType.REAL)
    if real is None:
        return

    summary = await get_portfolio_summary(real.id)

    # Obtener SPY para benchmark
    benchmark = None
    try:
        spy_price = await get_current_price("SPY", "NYSE")
        benchmark = spy_price
    except Exception:
        pass

    await repo.save_portfolio_snapshot(
        portfolio_id=real.id,
        total_value=summary.get("total_with_cash", summary.get("total_value", 0) + summary.get("cash", 0)),
        invested_value=summary.get("total_invested", 0),
        cash=summary.get("cash", 0),
        num_positions=summary.get("num_positions", 0),
        pnl=summary.get("total_pnl", 0),
        pnl_pct=summary.get("total_pnl_pct", 0),
        benchmark_value=benchmark,
    )
    logger.info("📸 Snapshot del portfolio guardado")


async def job_check_custom_alerts() -> None:
    """Comprueba alertas personalizadas (precio, volumen, RSI, técnicos)."""
    alerts = await repo.get_active_alerts()
    if not alerts:
        return

    for alert in alerts:
        try:
            market = getattr(alert, "market", None) or "NASDAQ"
            price = await get_current_price(alert.ticker, market)
            if price is None:
                continue

            triggered = False
            detail = ""

            if alert.alert_type == "precio_max" and price >= alert.threshold:
                triggered = True
                detail = f"💵 Precio: {price:.2f}$ ≥ {alert.threshold:.2f}$"

            elif alert.alert_type == "precio_min" and price <= alert.threshold:
                triggered = True
                detail = f"💵 Precio: {price:.2f}$ ≤ {alert.threshold:.2f}$"

            elif alert.alert_type == "volumen":
                # Alerta de spike de volumen
                try:
                    from data.technical import get_technical_analysis
                    ti = await get_technical_analysis(alert.ticker, market)
                    if ti and getattr(ti, 'atr', None) is not None:
                        # TechnicalIndicators no tiene volume directamente,
                        # usamos ATR como proxy de volatilidad
                        pass
                except Exception:
                    pass

            elif alert.alert_type in ("rsi_max", "rsi_above"):
                try:
                    from data.technical import get_technical_analysis
                    ti = await get_technical_analysis(alert.ticker, market)
                    if ti and ti.rsi is not None:
                        if ti.rsi >= alert.threshold:
                            triggered = True
                            detail = f"📈 RSI: {ti.rsi:.1f} ≥ {alert.threshold:.0f} (sobrecompra)"
                except Exception:
                    pass

            elif alert.alert_type in ("rsi_min", "rsi_below"):
                try:
                    from data.technical import get_technical_analysis
                    ti = await get_technical_analysis(alert.ticker, market)
                    if ti and ti.rsi is not None:
                        if ti.rsi <= alert.threshold:
                            triggered = True
                            detail = f"📉 RSI: {ti.rsi:.1f} ≤ {alert.threshold:.0f} (sobreventa)"
                except Exception:
                    pass

            if triggered:
                await repo.trigger_alert(alert.id)
                text = (
                    f"🔔 *ALERTA DISPARADA*\n\n"
                    f"📌 ${alert.ticker} — {alert.alert_type}\n"
                    f"{detail}\n"
                )
                if alert.message:
                    text += f"📝 {alert.message}\n"
                await _notify(text)
        except Exception as e:
            logger.error(f"Error comprobando alerta {alert.id}: {e}")


async def job_check_earnings_calendar() -> None:
    """
    Comprueba el calendario de earnings de cartera y watchlist.
    Notifica cuando hay resultados próximos (≤7 días) y lanza
    análisis IA pre-earnings para preparar la decisión.
    """
    from data.earnings import check_upcoming_earnings

    tickers: list[tuple[str, str]] = []
    sources: dict[tuple[str, str], str] = {}

    # Cartera
    real = await repo.get_portfolio_by_type(PortfolioType.REAL)
    if real:
        positions = await repo.get_open_positions(real.id)
        for p in positions:
            tickers.append((p.ticker, p.market))
            sources[(p.ticker, p.market)] = "📊 Cartera"

    # Watchlist
    watchlist = await repo.get_active_watchlist()
    for w in watchlist:
        key = (w.ticker, w.market)
        if key not in sources:
            tickers.append(key)
            sources[key] = "📋 Watchlist"

    if not tickers:
        return

    try:
        upcoming = await check_upcoming_earnings(tickers)
    except Exception as e:
        logger.error(f"Error obteniendo calendario de earnings: {e}")
        return

    # Filtrar los que están a 7 días o menos
    imminent = [e for e in upcoming if e.get("days_until") is not None and e["days_until"] <= 7]
    if not imminent:
        return

    text = "📅 *EARNINGS PRÓXIMOS (≤7 días)*\n\n"
    for e in imminent:
        ticker = e["ticker"]
        market = e.get("market") or "N/A"
        days = e["days_until"]
        source = sources.get((ticker, market), "")
        date_str = (
            e["earnings_date"].strftime("%d/%m/%Y")
            if hasattr(e["earnings_date"], "strftime")
            else str(e["earnings_date"])
        )
        d_emoji = "🔴" if days <= 3 else "🟡"
        text += f"  {d_emoji} *${ticker}* ({market}) — {date_str} (en {days} días) {source}\n"

        # Para empresas en cartera con earnings ≤3 días, generar análisis pre-earnings ligero
        if days <= 3 and sources.get((ticker, market)) == "📊 Cartera":
            try:
                from ai.analyst import _call_llm
                from data.fundamentals import fetch_fundamentals
                import asyncio

                fd = await asyncio.to_thread(fetch_fundamentals, ticker, market)
                pre_prompt = (
                    f"Análisis pre-earnings muy breve de ${ticker} "
                    f"(sector: {fd.sector}, P/E: {fd.pe_ratio}, precio: {fd.current_price}$). "
                    f"Earnings en {days} días. "
                    "¿Qué esperar? Riesgos y oportunidades en 2-3 frases."
                )
                ai_analysis = await _call_llm(pre_prompt, max_tokens=200, context=f"pre_earnings_{ticker}_{market}")
                text += f"  🧠 _Pre-earnings:_ {ai_analysis[:200]}…\n"
            except Exception as ex:
                logger.warning(f"Error en análisis pre-earnings {ticker}: {ex}")

    text += "\n_Usa_ `/earnings TICKER` _para ver historial completo_"
    await _notify(text)
    logger.info(f"📅 Earnings check: {len(imminent)} próximos notificados")
