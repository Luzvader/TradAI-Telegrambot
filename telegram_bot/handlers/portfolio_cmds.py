"""Handlers de cartera, compra, venta, capital y dividendos."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config.markets import DEFAULT_TICKER_MARKET, market_display, normalize_ticker, split_yfinance_suffix
from data.dividends import check_and_record_dividends, get_dividend_summary
from data.earnings import check_upcoming_earnings
from database import repository as repo
from database.models import PortfolioType
from portfolio.portfolio_manager import get_portfolio_summary
from telegram_bot.handlers.helpers import _escape_md, _parse_buy_sell, _send_long
from telegram_bot.handlers.registry import CommandInfo

logger = logging.getLogger(__name__)


async def cmd_cartera(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Comando /cartera — vista completa: posiciones, señales,
    earnings próximos, watchlist y aprendizaje.
    """
    real = await repo.get_portfolio_by_type(PortfolioType.REAL)
    if real is None:
        await update.message.reply_text("❌ No hay cartera inicializada.")
        return

    strategy_str = (real.strategy.value if real.strategy else "value").upper()
    summary = await get_portfolio_summary(real.id)

    # ── Cabecera ──
    text = f"📊 *MI CARTERA — Estrategia {strategy_str}*\n\n"
    text += (
        f"💰 Valor: {summary['total_value']:,.2f}$\n"
        f"💵 Invertido: {summary['total_invested']:,.2f}$\n"
        f"📈 PnL: {summary['total_pnl']:+,.2f}$ ({summary['total_pnl_pct']:+.2f}%)\n\n"
    )

    # ── Posiciones ──
    if summary["positions"]:
        text += "*Posiciones:*\n"
        for p in summary["positions"]:
            emoji = "🟢" if p["pnl"] >= 0 else "🔴"
            alert = ""
            if p.get("stop_loss_hit"):
                alert = " ⚠️ SL!"
            elif p.get("take_profit_hit"):
                alert = " 🎯 TP!"
            mkt = market_display(p['market'])
            text += (
                f"{emoji} *{_escape_md(p['ticker'])}* ({_escape_md(mkt)})\n"
                f"   {p['shares']:.2f} acc × {p['current_price']:.2f}$ "
                f"| PnL: {p['pnl']:+.2f}$ ({p['pnl_pct']:+.1f}%) "
                f"| Peso: {p['weight_pct']:.1f}%{alert}\n"
            )
    else:
        text += "_Sin posiciones abiertas_\n"

    # ── Sectores ──
    if summary.get("sector_weights"):
        text += "\n*Sectores:*\n"
        for sector, weight in sorted(
            summary["sector_weights"].items(), key=lambda x: -x[1]
        ):
            bar = "█" * int(weight / 5) if weight > 0 else ""
            text += f"  {_escape_md(sector)}: {weight:.1f}% {bar}\n"

    # ── Señales recientes ──
    recent_signals = await repo.get_recent_signals(limit=5)
    if recent_signals:
        text += "\n📡 *Últimas señales:*\n"
        for sig in recent_signals:
            emoji = (
                "🟢" if sig.signal_type.value == "BUY"
                else "🔴" if sig.signal_type.value == "SELL"
                else "🟡"
            )
            price_str = f" | {sig.price:.2f}$" if sig.price else ""
            text += (
                f"  {emoji} {_escape_md(sig.ticker)} → {sig.signal_type.value}{price_str}"
                f" | {sig.created_at.strftime('%d/%m %H:%M')}\n"
            )

    # ── Watchlist ──
    watchlist = await repo.get_active_watchlist()
    if watchlist:
        text += f"\n📋 *Watchlist ({len(watchlist)}/5):*\n"
        for w in watchlist:
            text += f"  📌 {_escape_md(w.ticker)} — {_escape_md(w.reason or 'En estudio')}\n"

    # ── Earnings próximos ──
    positions = await repo.get_open_positions(real.id)
    tickers = [(p.ticker, p.market) for p in positions]
    if tickers:
        upcoming = await check_upcoming_earnings(tickers)
        near = [e for e in upcoming if e.get("days_until") is not None and e["days_until"] <= 30]
        if near:
            text += "\n📅 *Earnings próximos (30 días):*\n"
            for e in near:
                days = e["days_until"]
                d_emoji = "🔴" if days <= 7 else "🟡"
                date_str = (
                    e["earnings_date"].strftime("%d/%m/%Y")
                    if hasattr(e["earnings_date"], "strftime")
                    else str(e["earnings_date"])
                )
                mkt = e.get("market")
                mkt_str = f" ({_escape_md(market_display(mkt))})" if mkt else ""
                text += f"  {d_emoji} {_escape_md(e['ticker'])}{mkt_str} — {date_str} (en {days} días)\n"

    # ── Aprendizaje ──
    learning = await repo.get_learning_summary()
    if learning["total_trades_analyzed"] > 0:
        text += (
            f"\n🧠 Aprendizaje: {learning['total_trades_analyzed']} trades "
            f"(Win: {learning['wins']}/{learning['total_trades_analyzed']})\n"
        )

    # ── Auto mode ──
    config = await repo.get_auto_mode_config(real.id)
    if config:
        from database.models import AutoModeType
        mode_labels = {
            AutoModeType.OFF: "🔴 OFF",
            AutoModeType.ON: "🟢 ON",
            AutoModeType.SAFE: "🛡️ SAFE",
        }
        a_status = mode_labels.get(config.mode, "🔴 OFF")
        text += f"\n🤖 Modo auto: {a_status}\n"

    await _send_long(update, text)


async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Comando /buy TICKER CANTIDAD PRECIO
    Ejemplo: /buy AAPL 10 185.50
    Pide confirmación con botón inline antes de ejecutar.
    """
    full_text = update.message.text or ""
    parsed = _parse_buy_sell(full_text)

    if parsed is None:
        await update.message.reply_text(
            "❌ Formato incorrecto.\n\n"
            "*Uso:* `/buy TICKER CANTIDAD PRECIO`\n"
            "*Ejemplo:* `/buy AAPL 10 185.50`\n\n"
            "_TICKER = símbolo (AAPL, MSFT...)_\n"
            "_CANTIDAD = número de acciones_\n"
            "_PRECIO = precio de compra en $_ ",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
    if portfolio is None:
        await update.message.reply_text("❌ Cartera no inicializada.")
        return

    base, inferred_market = split_yfinance_suffix(parsed["ticker"])
    ticker = normalize_ticker(base)
    market = inferred_market or DEFAULT_TICKER_MARKET.get(ticker, "NASDAQ")

    total = parsed["shares"] * parsed["price"]
    mkt_display = _escape_md(market_display(market))
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Confirmar compra",
                callback_data=f"buy_confirm:{ticker}:{market}:{parsed['shares']}:{parsed['price']}",
            ),
            InlineKeyboardButton("❌ Cancelar", callback_data="buy_cancel"),
        ]
    ])

    text = (
        f"🛒 *¿Confirmar compra?*\n\n"
        f"📌 Ticker: {_escape_md(ticker)} ({mkt_display})\n"
        f"📊 Acciones: {parsed['shares']}\n"
        f"💵 Precio: {parsed['price']}$\n"
        f"💰 Total: {total:,.2f}$"
    )
    try:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
    except Exception:
        await update.message.reply_text(
            text,
            reply_markup=keyboard,
        )


async def cmd_sell(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Comando /sell TICKER CANTIDAD PRECIO
    Ejemplo: /sell AAPL 5 200.00
    Pide confirmación con botón inline antes de ejecutar.
    """
    full_text = update.message.text or ""
    parsed = _parse_buy_sell(full_text)

    if parsed is None:
        await update.message.reply_text(
            "❌ Formato incorrecto.\n\n"
            "*Uso:* `/sell TICKER CANTIDAD PRECIO`\n"
            "*Ejemplo:* `/sell AAPL 5 200.00`\n\n"
            "_TICKER = símbolo (AAPL, MSFT...)_\n"
            "_CANTIDAD = acciones a vender_\n"
            "_PRECIO = precio de venta en $_ ",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
    if portfolio is None:
        await update.message.reply_text("❌ Cartera no inicializada.")
        return

    base, inferred_market = split_yfinance_suffix(parsed["ticker"])
    ticker = normalize_ticker(base)
    market = inferred_market or DEFAULT_TICKER_MARKET.get(ticker, "NASDAQ")

    total = parsed["shares"] * parsed["price"]
    mkt_display = _escape_md(market_display(market))
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Confirmar venta",
                callback_data=f"sell_confirm:{ticker}:{market}:{parsed['shares']}:{parsed['price']}",
            ),
            InlineKeyboardButton("❌ Cancelar", callback_data="sell_cancel"),
        ]
    ])

    text = (
        f"💸 *¿Confirmar venta?*\n\n"
        f"📌 Ticker: {_escape_md(ticker)} ({mkt_display})\n"
        f"📊 Acciones: {parsed['shares']}\n"
        f"💵 Precio: {parsed['price']}$\n"
        f"💰 Total: {total:,.2f}$"
    )
    try:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
    except Exception:
        await update.message.reply_text(
            text,
            reply_markup=keyboard,
        )


async def cmd_capital(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Comando /capital CANTIDAD — establece el capital inicial de la cartera.
    Ejemplo: /capital 10000
    """
    args = context.args or []
    if not args:
        portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
        if portfolio:
            text = (
                f"💰 *CAPITAL*\n\n"
                f"Capital inicial: {portfolio.initial_capital or 0:,.2f}$\n"
                f"Cash disponible: {portfolio.cash or 0:,.2f}$\n\n"
                f"_Cambiar:_ `/capital CANTIDAD`\n"
                f"_Ejemplo:_ `/capital 10000`"
            )
        else:
            text = "❌ Cartera no inicializada."
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return

    try:
        amount = float(args[0].replace(",", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Indica una cantidad válida (número positivo).")
        return

    portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
    if portfolio is None:
        await update.message.reply_text("❌ Cartera no inicializada.")
        return

    await repo.set_initial_capital(portfolio.id, amount)
    await update.message.reply_text(
        f"✅ *Capital establecido*\n\n"
        f"💰 Capital inicial: {amount:,.2f}$\n"
        f"💵 Cash disponible: {amount:,.2f}$",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_dividendos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /dividendos [check]
    Sin argumentos: muestra el resumen de dividendos cobrados.
    Con 'check': detecta y registra nuevos dividendos de posiciones abiertas.
    """
    portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
    if portfolio is None:
        await update.message.reply_text("❌ No hay cartera inicializada.")
        return

    # Modo detección
    if context.args and context.args[0].lower() == "check":
        await update.message.reply_text("⏳ Comprobando dividendos recientes…")
        try:
            new_divs = await check_and_record_dividends(portfolio.id)
            if not new_divs:
                await update.message.reply_text("ℹ️ No se detectaron dividendos nuevos.")
                return
            lines = ["✅ *Dividendos registrados:*\n"]
            for d in new_divs:
                lines.append(
                    f"• {d['ticker']}: ${d['amount_per_share']:.4f}/acc "
                    f"× {d['shares']:.0f} = *${d['total']:.2f}* "
                    f"(ex-date: {d['ex_date']})"
                )
            await _send_long(update, "\n".join(lines))
        except Exception as e:
            logger.error(f"Error comprobando dividendos: {e}")
            await update.message.reply_text(f"❌ Error: {e}")
        return

    # Resumen de dividendos
    try:
        summary = await get_dividend_summary(portfolio.id)
    except Exception as e:
        logger.error(f"Error obteniendo resumen de dividendos: {e}")
        await update.message.reply_text(f"❌ Error: {e}")
        return

    if summary["count"] == 0:
        await update.message.reply_text(
            "📊 *Dividendos*\n\n"
            "No hay dividendos registrados.\n"
            "Usa `/dividendos check` para detectar dividendos recientes.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    text = (
        f"📊 *DIVIDENDOS*\n\n"
        f"💰 Total histórico: *${summary['total_all_time']:,.2f}*\n"
        f"📅 Últimos 12 meses: *${summary['total_12m']:,.2f}*\n"
        f"🔢 Pagos registrados: {summary['count']}\n\n"
    )

    if summary["by_ticker"]:
        text += "*Por ticker:*\n"
        for ticker, amount in list(summary["by_ticker"].items())[:10]:
            text += f"  • {ticker}: ${amount:,.2f}\n"

    if summary["recent"]:
        text += "\n*Últimos pagos:*\n"
        for d in summary["recent"][:5]:
            text += f"  • {d['ticker']}: ${d['amount']:.2f} ({d['date']})\n"

    await _send_long(update, text)


# ── Registro de comandos ─────────────────────────────────────

COMMANDS: list[CommandInfo] = [
    CommandInfo("cartera", cmd_cartera, "Ver cartera, posiciones, señales y earnings"),
    CommandInfo("buy", cmd_buy, "Comprar: /buy TICKER CANTIDAD PRECIO"),
    CommandInfo("sell", cmd_sell, "Vender: /sell TICKER CANTIDAD PRECIO"),
    CommandInfo("capital", cmd_capital, "Establecer capital: /capital 10000"),
    CommandInfo("dividendos", cmd_dividendos, "Dividendos: /dividendos [check]"),
]
