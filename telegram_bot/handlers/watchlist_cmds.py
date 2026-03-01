"""Handler de watchlist: /watchlist ver, generar o quitar tickers."""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ai.watchlist import ai_generate_watchlist, get_watchlist_summary
from database import repository as repo
from database.models import PortfolioType
from telegram_bot.handlers.helpers import _send_long
from telegram_bot.handlers.registry import CommandInfo

logger = logging.getLogger(__name__)


async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Comando /watchlist — ver, generar o quitar tickers.
      /watchlist           → ver watchlist
      /watchlist generar   → IA genera nueva watchlist
      /watchlist quitar TICKER → quitar un ticker
      /watchlist limpiar   → vaciar toda la watchlist
    """
    args = context.args or []

    if not args:
        summary = await get_watchlist_summary()
        await _send_long(update, summary)
        return

    subcmd = args[0].lower()

    if subcmd in ("generar", "generate", "gen"):
        await update.message.reply_text("🤖 Generando watchlist con IA...")
        real = await repo.get_portfolio_by_type(PortfolioType.REAL)
        portfolio_tickers = []
        if real:
            positions = await repo.get_open_positions(real.id)
            portfolio_tickers = [p.ticker for p in positions]

        added = await ai_generate_watchlist(portfolio_tickers)

        if added:
            stock_count = sum(1 for a in added if a.get('asset_type') == 'stock')
            etf_count = sum(1 for a in added if a.get('asset_type') == 'etf')
            text = f"✅ *Watchlist generada:* {len(added)} items ({stock_count} acciones, {etf_count} ETFs)\n\n"
            for item in added:
                conv = f" | Convicción: {item['conviction']}/10" if item.get('conviction') else ""
                type_emoji = "📦" if item.get('asset_type') == 'etf' else "📊"
                text += f"{type_emoji} *${item['ticker']}* ({item['market']}){conv}\n"
                if item.get('sector'):
                    text += f"   Sector: {item['sector']}\n"
                if item.get("thesis"):
                    text += f"   📝 {item['thesis']}\n"
                targets = []
                if item.get("target_entry"):
                    from config.markets import format_price, MARKET_CURRENCY
                    ccy = MARKET_CURRENCY.get(item['market'], 'USD')
                    targets.append(f"Entrada: {format_price(item['target_entry'], ccy)}")
                if item.get("target_exit"):
                    from config.markets import format_price, MARKET_CURRENCY
                    ccy = MARKET_CURRENCY.get(item['market'], 'USD')
                    targets.append(f"Salida: {format_price(item['target_exit'], ccy)}")
                if targets:
                    text += f"   🎯 {' | '.join(targets)}\n"
                if item.get("catalysts"):
                    text += f"   🚀 {item['catalysts']}\n"
                if item.get("risks"):
                    text += f"   ⚠️ {item['risks']}\n"
                text += "\n"
        else:
            text = "⚠️ No se pudieron añadir tickers. Puede estar llena (máx 25)."
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    elif subcmd in ("quitar", "remove", "rm"):
        if len(args) < 2:
            await update.message.reply_text(
                "*Uso:* `/watchlist quitar TICKER`\n"
                "*Ejemplo:* `/watchlist quitar AAPL`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        ticker = args[1].upper().replace("$", "")
        removed = await repo.remove_from_watchlist(ticker)
        if removed:
            await update.message.reply_text(f"✅ ${ticker} eliminado de la watchlist.")
        else:
            await update.message.reply_text(f"❌ ${ticker} no está en la watchlist.")

    elif subcmd in ("limpiar", "clear", "reset"):
        count = await repo.clear_watchlist()
        await update.message.reply_text(f"✅ Watchlist limpiada ({count} items eliminados).")

    else:
        await update.message.reply_text(
            "❌ Subcomando no reconocido.\n\n"
            "`/watchlist` — Ver\n"
            "`/watchlist generar` — Crear con IA\n"
            "`/watchlist quitar TICKER` — Quitar un ticker\n"
            "`/watchlist limpiar` — Vaciar toda la watchlist",
            parse_mode=ParseMode.MARKDOWN,
        )


# ── Registro de comandos ─────────────────────────────────────

COMMANDS: list[CommandInfo] = [
    CommandInfo("watchlist", cmd_watchlist, "Ver/gestionar watchlist"),
]
