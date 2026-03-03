"""Handlers de análisis, scan, comparación, macro, estrategia, historial y backtest."""

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ai.analyst import analyze_with_context, get_macro_analysis
from backtesting.engine import BacktestConfig, run_backtest
from config.markets import format_price, MARKET_CURRENCY
from config.settings import SCAN_MIN_SCORE
from data.insiders import get_insider_activity, format_insider_report
from data.ticker_discovery import get_etf_tickers, get_etf_categories
from database import repository as repo
from database.models import AnalysisLog, PortfolioType, StrategyType
from signals.signal_engine import analyze_ticker, scan_opportunities
from strategy.correlation import portfolio_correlation, format_correlation_report
from strategy.screener import quick_scan
from telegram_bot.handlers.helpers import _send_long
from telegram_bot.handlers.registry import CommandInfo

logger = logging.getLogger(__name__)


async def cmd_analizar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Comando /analizar TICKER — análisis completo según estrategia activa.
    Muestra un resumen compacto al usuario y almacena el análisis completo
    en la BD para que el motor de aprendizaje pueda utilizarlo.
    Ejemplo: /analizar AAPL
    """
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "❌ Indica un ticker.\n\n"
            "*Uso:* `/analizar TICKER`\n"
            "*Ejemplo:* `/analizar AAPL`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ticker = args[0].upper().replace("$", "")
    await update.message.reply_text(f"🔍 Analizando ${ticker}...")

    analysis = await analyze_ticker(ticker)
    resolved_ticker = analysis.get("ticker", ticker)
    resolved_market = analysis.get("market")

    # ── IA analysis (obtenerlo antes de construir mensaje) ───
    ai_analysis_text = ""
    try:
        det_ctx = analysis.get("deterministic_context", "")
        ai_analysis_text = await analyze_with_context(
            resolved_ticker, resolved_market, analysis,
            deterministic_context=det_ctx,
        ) or ""
    except Exception as e:
        logger.warning(f"Error en análisis IA: {e}")

    # ── Persistir análisis completo para el motor de aprendizaje ──
    try:
        reasoning_list = analysis.get("reasoning", [])
        reasoning_text = "\n".join(reasoning_list) if isinstance(reasoning_list, list) else str(reasoning_list)

        tradability = analysis.get("broker_tradability") or {}
        broker_tradable = tradability.get("tradable")

        log = AnalysisLog(
            ticker=resolved_ticker,
            market=resolved_market or "NASDAQ",
            strategy_used=str(analysis.get("strategy", "")),
            signal=analysis.get("signal", "HOLD"),
            overall_score=analysis.get("overall_score"),
            value_score=analysis.get("value_score"),
            quality_score=analysis.get("quality_score"),
            safety_score=analysis.get("safety_score"),
            price_at_analysis=analysis.get("price"),
            margin_of_safety=analysis.get("margin_of_safety"),
            pe_ratio=analysis.get("pe_ratio"),
            roe=analysis.get("roe"),
            debt_to_equity=analysis.get("debt_to_equity"),
            dividend_yield=analysis.get("dividend_yield"),
            reasoning=reasoning_text,
            tech_summary=analysis.get("tech_summary", ""),
            price_summary=analysis.get("price_summary", ""),
            ai_analysis=ai_analysis_text if ai_analysis_text and not ai_analysis_text.startswith("⚠️") else None,
            broker_tradable=broker_tradable,
            deterministic_context=analysis.get("deterministic_context", ""),
            source="manual",
        )
        await repo.save_analysis_log(log)
        logger.info(f"💾 Análisis de {resolved_ticker} guardado (id={log.id})")
    except Exception as e:
        logger.warning(f"Error guardando análisis de {resolved_ticker}: {e}")

    # ── Construir resumen compacto para Telegram ──────────────
    signal = analysis.get("signal", "HOLD")
    emoji = "🟢" if signal == "BUY" else "🔴" if signal == "SELL" else "🟡"
    strategy = str(analysis.get("strategy", "value")).upper()
    market_str = f" ({resolved_market})" if resolved_market else ""
    price = analysis.get("price")
    currency = analysis.get("currency", "USD")
    price_str = format_price(price, currency) if price else "N/A"

    text = f"{emoji} *${resolved_ticker}*{market_str} — {price_str}\n"
    text += f"Señal: *{signal}* | Score: *{analysis.get('overall_score', 0):.0f}*/100\n"

    # Scores desglosados en una línea
    text += (
        f"V:{analysis.get('value_score', 0):.0f} "
        f"Q:{analysis.get('quality_score', 0):.0f} "
        f"S:{analysis.get('safety_score', 0):.0f} "
        f"| {strategy}\n"
    )

    # Métricas clave (solo si existen), formato compacto
    metrics_parts = []
    if analysis.get("margin_of_safety") is not None:
        metrics_parts.append(f"MoS {analysis['margin_of_safety']:.1f}%")
    if analysis.get("pe_ratio"):
        metrics_parts.append(f"P/E {analysis['pe_ratio']:.1f}")
    if analysis.get("roe"):
        metrics_parts.append(f"ROE {analysis['roe'] * 100:.1f}%")
    if analysis.get("debt_to_equity"):
        metrics_parts.append(f"D/E {analysis['debt_to_equity']:.0f}%")
    if metrics_parts:
        text += " | ".join(metrics_parts) + "\n"

    # eToro tradabilidad (una línea)
    tradability = analysis.get("broker_tradability") or {}
    if tradability.get("tradable") is True:
        text += "🏦 eToro: ✅ Operable\n"
    elif tradability.get("tradable") is False:
        text += f"🏦 eToro: ❌ {tradability.get('reason', 'No disponible')}\n"

    # Resumen técnico + valoración (compactos)
    if analysis.get("tech_summary"):
        text += f"📉 {analysis['tech_summary']}\n"
    if analysis.get("price_summary"):
        text += f"💲 {analysis['price_summary']}\n"

    # Razonamiento: máximo 3 puntos clave
    reasoning = analysis.get("reasoning", [])
    if reasoning:
        text += "\n"
        for r in reasoning[:3]:
            text += f"• {r}\n"
        if len(reasoning) > 3:
            text += f"_+{len(reasoning) - 3} más_\n"

    # IA (recortada si es muy larga)
    if ai_analysis_text and not ai_analysis_text.startswith("⚠️"):
        short_ai = ai_analysis_text[:500]
        if len(ai_analysis_text) > 500:
            short_ai += "…"
        text += f"\n🧠 *IA:*\n{short_ai}"
    elif ai_analysis_text:
        text += f"\n🧠 {ai_analysis_text}"
    else:
        text += "\n🧠 _IA no disponible_"

    await _send_long(update, text)


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /scan — escanea las mejores oportunidades según estrategia."""
    await update.message.reply_text("🔍 Escaneando mercados... (puede tardar)")

    opportunities = await scan_opportunities(max_results=5)

    if not opportunities:
        await update.message.reply_text(f"Sin oportunidades con score > {SCAN_MIN_SCORE:.0f}.")
        return

    strat = str(opportunities[0].get("strategy", "value")).upper()
    text = f"🎯 *TOP OPORTUNIDADES {strat}*\n\n"
    for i, opp in enumerate(opportunities, 1):
        emoji = "🟢" if opp["signal"] == "BUY" else "🟡"
        currency = opp.get("currency", "USD")
        price_str = format_price(opp.get("price"), currency) if opp.get("price") else "N/A"
        text += (
            f"{i}. {emoji} *${opp['ticker']}* — {price_str}\n"
            f"   Score: {opp['overall_score']:.0f}/100 "
            f"(V:{opp['value_score']:.0f} Q:{opp['quality_score']:.0f} S:{opp['safety_score']:.0f})\n"
        )
        tradability = opp.get("broker_tradability") or {}
        if tradability.get("tradable") is True:
            text += "   eToro: ✅ Operable\n"
        elif tradability.get("tradable") is False:
            text += "   eToro: ❌ No operable\n"
        elif "tradable" in tradability:
            text += "   eToro: ⚪ Sin verificar\n"
        if opp.get("margin_of_safety") is not None:
            text += f"   MoS: {opp['margin_of_safety']:.1f}%\n"

        # Justificación detallada
        justification = opp.get("justification", "")
        if justification:
            short = justification[:250]
            if len(justification) > 250:
                short += "…"
            text += f"{short}\n"
        text += "\n"

    await _send_long(update, text)

    # Persistir las oportunidades como AnalysisLog para el motor de aprendizaje
    for opp in opportunities:
        try:
            await repo.save_analysis_log(AnalysisLog(
                ticker=opp["ticker"],
                source="scan",
                signal_type=opp.get("signal", "BUY"),
                score=opp.get("overall_score"),
                summary=opp.get("justification", "")[:500],
                raw_json={
                    "value_score": opp.get("value_score"),
                    "quality_score": opp.get("quality_score"),
                    "safety_score": opp.get("safety_score"),
                    "margin_of_safety": opp.get("margin_of_safety"),
                    "price": opp.get("price"),
                    "strategy": opp.get("strategy"),
                },
            ))
        except Exception:
            pass  # no bloquear respuesta por fallo de logging


async def cmd_macro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /macro — análisis macroeconómico con IA."""
    await update.message.reply_text("🌍 Analizando contexto macro...")
    analysis = await get_macro_analysis()
    text = f"🌍 *ANÁLISIS MACROECONÓMICO*\n\n{analysis}"
    await _send_long(update, text)


async def cmd_strategy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Comando /strategy [TIPO]
    Sin argumentos: muestra estrategia actual.
    Con argumento: cambia la estrategia.
    """
    args = context.args or []

    portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
    if portfolio is None:
        await update.message.reply_text("❌ Cartera no inicializada.")
        return

    if not args:
        current = (portfolio.strategy.value if portfolio.strategy else "value").upper()
        text = f"📋 *ESTRATEGIA ACTIVA: {current}*\n\n"
        text += "Selecciona una estrategia:"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 Value", callback_data="strategy_set:value"),
             InlineKeyboardButton("🚀 Growth", callback_data="strategy_set:growth")],
            [InlineKeyboardButton("💰 Dividend", callback_data="strategy_set:dividend"),
             InlineKeyboardButton("⚖️ Balanced", callback_data="strategy_set:balanced")],
            [InlineKeyboardButton("🛡️ Conservative", callback_data="strategy_set:conservative")],
        ])

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        return

    strategy_name = args[0].lower().strip()
    valid = {s.value: s for s in StrategyType}

    if strategy_name not in valid:
        await update.message.reply_text(
            f"❌ Estrategia '{strategy_name}' no válida.\n"
            f"Opciones: {', '.join(valid.keys())}",
        )
        return

    success = await repo.set_portfolio_strategy(portfolio.id, valid[strategy_name])
    if success:
        await update.message.reply_text(
            f"✅ *Estrategia cambiada a {strategy_name.upper()}*\n\n"
            f"Las señales y análisis ahora usarán esta estrategia.",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text("❌ Error al cambiar la estrategia.")


async def cmd_historial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /historial — muestra las últimas señales generadas."""
    args = context.args or []
    limit = 10
    if args:
        try:
            limit = min(int(args[0]), 30)
        except ValueError:
            pass

    signals = await repo.get_recent_signals(limit=limit)
    if not signals:
        await update.message.reply_text("📡 Sin señales registradas.")
        return

    text = f"📡 *ÚLTIMAS {len(signals)} SEÑALES*\n\n"
    for sig in signals:
        emoji = (
            "🟢" if sig.signal_type.value == "BUY"
            else "🔴" if sig.signal_type.value == "SELL"
            else "🟡"
        )
        price_str = f" | {format_price(sig.price, MARKET_CURRENCY.get(sig.market, 'USD'))}" if sig.price else ""
        score_str = f" | Score: {sig.value_score:.0f}" if sig.value_score else ""
        text += (
            f"{emoji} *${sig.ticker}* → {sig.signal_type.value}{price_str}{score_str}\n"
            f"   {sig.created_at.strftime('%d/%m/%Y %H:%M')}\n"
        )
        if sig.reasoning:
            short = sig.reasoning[:80] + "..." if len(sig.reasoning) > 80 else sig.reasoning
            text += f"   _{short}_\n"
        text += "\n"

    await _send_long(update, text)


async def cmd_comparar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Comando /comparar TICKER1 TICKER2 — compara dos tickers lado a lado.
    Ejemplo: /comparar AAPL MSFT
    """
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Indica dos tickers.\n\n"
            "*Uso:* `/comparar TICKER1 TICKER2`\n"
            "*Ejemplo:* `/comparar AAPL MSFT`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ticker1 = args[0].upper().replace("$", "")
    ticker2 = args[1].upper().replace("$", "")

    await update.message.reply_text(
        f"🔍 Comparando ${ticker1} vs ${ticker2}... (puede tardar)"
    )

    a1, a2 = await asyncio.gather(
        analyze_ticker(ticker1),
        analyze_ticker(ticker2),
    )

    def _fmt(a: dict) -> str:
        emoji = "🟢" if a["signal"] == "BUY" else "🔴" if a["signal"] == "SELL" else "🟡"
        cur = a.get("currency", "USD")
        lines = [
            f"*${a['ticker']}* — {a.get('name', 'N/A')}",
            f"  Sector: {a.get('sector', 'N/A')}",
            f"  Precio: {format_price(a.get('price'), cur)}",
            f"  {emoji} Señal: {a['signal']}",
            f"  Score: {a['overall_score']:.0f}/100 (V:{a['value_score']:.0f} Q:{a['quality_score']:.0f} S:{a['safety_score']:.0f})",
        ]
        if a.get("margin_of_safety") is not None:
            lines.append(f"  MoS: {a['margin_of_safety']:.1f}%")
        if a.get("pe_ratio"):
            lines.append(f"  P/E: {a['pe_ratio']:.1f}")
        if a.get("roe"):
            lines.append(f"  ROE: {a['roe'] * 100:.1f}%")
        if a.get("debt_to_equity"):
            lines.append(f"  Deuda/Equity: {a['debt_to_equity']:.0f}%")
        return "\n".join(lines)

    winner = ticker1 if a1["overall_score"] > a2["overall_score"] else ticker2
    diff = abs(a1["overall_score"] - a2["overall_score"])

    text = f"⚔️ *COMPARATIVA*\n\n{_fmt(a1)}\n\n{'─' * 20}\n\n{_fmt(a2)}\n\n"
    text += f"🏆 *Ganador: ${winner}* (diferencia de {diff:.0f} puntos)\n"

    await _send_long(update, text)


async def cmd_backtest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /backtest TICKER1 TICKER2 ... [period=1y] [strategy=value]
    Ejecuta un backtest sobre cartera demo (eToro-oriented).
    Ejemplo: /backtest AAPL MSFT GOOG period=2y strategy=growth
    """
    # Parsear argumentos
    tickers = []
    period = "1y"
    strategy = None

    for arg in (context.args or []):
        arg_lower = arg.lower()
        if arg_lower.startswith("period="):
            period = arg_lower.split("=", 1)[1]
        elif arg_lower.startswith("strategy="):
            strat_name = arg_lower.split("=", 1)[1]
            for st in StrategyType:
                if st.value == strat_name:
                    strategy = st
                    break
        else:
            tickers.append(arg.upper().replace("$", ""))

    demo = await repo.get_portfolio_by_type(PortfolioType.BACKTEST)
    if demo is None:
        await update.message.reply_text("❌ Cartera demo no inicializada.")
        return

    if strategy is None:
        strategy = demo.strategy or StrategyType.VALUE

    # Si no se indican tickers, usar cartera demo y luego watchlist
    if not tickers:
        demo_positions = await repo.get_open_positions(demo.id)
        tickers = [p.ticker.upper() for p in demo_positions]
        if not tickers:
            watchlist = await repo.get_active_watchlist()
            tickers = [w.ticker.upper() for w in watchlist]

    if not tickers:
        await update.message.reply_text(
            "❌ No hay tickers en cartera demo ni watchlist.\n"
            "Añade tickers o usa `/backtest AAPL MSFT ...`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    valid_periods = {"3mo", "6mo", "1y", "2y", "5y", "10y"}
    if period not in valid_periods:
        await update.message.reply_text(
            f"❌ Período inválido. Opciones: {', '.join(sorted(valid_periods))}"
        )
        return

    await update.message.reply_text(
        f"⏳ Ejecutando backtest DEMO de {len(tickers)} tickers "
        f"({strategy.value}, {period})…\n"
        f"Esto puede tardar unos segundos."
    )

    try:
        config = BacktestConfig(
            tickers=tickers,
            strategy=strategy,
            period=period,
            initial_capital=(demo.initial_capital or demo.cash or 10_000.0),
        )
        result = await run_backtest(config)
        summary = result.format_summary()
        if result.learning_logs_created > 0:
            summary += f"\n\n🧠 _Se han registrado {result.learning_logs_created} trades para aprendizaje del bot._"
        await _send_long(update, summary)
    except Exception as e:
        logger.error(f"Error en backtest: {e}")
        await update.message.reply_text(f"❌ Error en backtest: {e}")


async def cmd_diversificacion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /diversificacion — Análisis de correlación y diversificación del portfolio.
    """
    await update.message.reply_text("⏳ Analizando diversificación del portfolio…")

    try:
        result = await portfolio_correlation()
        text = format_correlation_report(result)
        await _send_long(update, text)
    except Exception as e:
        logger.error(f"Error en análisis de diversificación: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_etf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /etf [categoría] — Escanea ETFs populares y muestra los mejores.
    Categorías: indices_us, indices_eu, indices_global, sectorial,
    renta_fija, commodities, tematicos
    """
    category = None
    if context.args:
        cat = context.args[0].lower()
        available = get_etf_categories()
        if cat in available:
            category = cat
        else:
            await update.message.reply_text(
                f"❌ Categoría desconocida.\n"
                f"Opciones: {', '.join(available)}"
            )
            return

    categories = [category] if category else None
    tickers = get_etf_tickers(categories)
    label = category or "todos"

    await update.message.reply_text(
        f"⏳ Escaneando {len(tickers)} ETFs ({label})…"
    )

    try:
        results = await quick_scan(tickers)
        if not results:
            await update.message.reply_text("ℹ️ No se obtuvieron datos.")
            return

        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        top = results[:10]

        lines = [f"📊 *ETFs — {label.upper()}*\n"]
        for r in top:
            emoji = "🟢" if r["signal"] == "BUY" else "🔴" if r["signal"] == "SELL" else "🟡"
            price_str = format_price(r["price"], r.get("currency", "USD")) if r["price"] else "N/A"
            lines.append(
                f"{emoji} *{r['ticker']}* — Score: {r['score']:.0f} | "
                f"{price_str} | {r['signal']}"
            )

        lines.append(f"\n_Mostrando top {len(top)} de {len(results)} ETFs analizados_")
        await _send_long(update, "\n".join(lines))
    except Exception as e:
        logger.error(f"Error en scan ETF: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_insider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /insider TICKER — Muestra actividad reciente de insiders (compras/ventas).
    """
    if not context.args:
        await update.message.reply_text(
            "👔 Uso: `/insider TICKER`\n"
            "Ejemplo: `/insider AAPL`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ticker = context.args[0].upper().replace("$", "")
    await update.message.reply_text(f"⏳ Consultando actividad de insiders de {ticker}…")

    try:
        data = await get_insider_activity(ticker)
        text = format_insider_report(data)
        await _send_long(update, text)
    except Exception as e:
        logger.error(f"Error obteniendo insiders de {ticker}: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


# ── Registro de comandos ─────────────────────────────────────

COMMANDS: list[CommandInfo] = [
    CommandInfo("analizar", cmd_analizar, "Análisis completo: /analizar TICKER"),
    CommandInfo("scan", cmd_scan, "Escanear mejores oportunidades"),
    CommandInfo("macro", cmd_macro, "Análisis macroeconómico con IA"),
    CommandInfo("strategy", cmd_strategy, "Estrategia: /strategy value|growth|..."),
    CommandInfo("historial", cmd_historial, "Últimas señales generadas"),
    CommandInfo("comparar", cmd_comparar, "Comparar: /comparar TICKER1 TICKER2"),
    CommandInfo("backtest", cmd_backtest, "Backtest: /backtest AAPL MSFT period=1y"),
    CommandInfo("diversificacion", cmd_diversificacion, "Análisis de correlación y diversificación"),
    CommandInfo("etf", cmd_etf, "Escanear ETFs: /etf [categoría]"),
    CommandInfo("insider", cmd_insider, "Insiders: /insider TICKER"),
]
