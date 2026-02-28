"""Handler de earnings: /earnings calendario y historial de resultados."""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config.markets import (
    DEFAULT_TICKER_MARKET,
    MARKETS,
    normalize_ticker,
    split_yfinance_suffix,
)
from data.earnings import check_upcoming_earnings, fetch_earnings_history
from database import repository as repo
from database.models import PortfolioType
from telegram_bot.handlers.helpers import _send_long
from telegram_bot.handlers.registry import CommandInfo

logger = logging.getLogger(__name__)


async def cmd_earnings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Comando /earnings — calendario de resultados trimestrales.
      /earnings           → próximos earnings de cartera + watchlist
      /earnings TICKER    → historial de earnings de un ticker
    """
    args = context.args or []

    if args:
        raw_ticker = args[0].replace("$", "")
        market = args[1].upper() if len(args) >= 2 and args[1].upper() in MARKETS else None

        base, inferred_market = split_yfinance_suffix(raw_ticker)
        ticker = normalize_ticker(base)
        market = market or inferred_market or DEFAULT_TICKER_MARKET.get(ticker)

        await update.message.reply_text(
            f"📅 Obteniendo historial de earnings de ${ticker}{f' ({market})' if market else ''}..."
        )

        history = await fetch_earnings_history(ticker, market=market)
        if not history:
            await update.message.reply_text(f"❌ Sin historial de earnings para ${ticker}.")
            return

        text = f"📅 *HISTORIAL DE EARNINGS — ${ticker}{f' ({market})' if market else ''}*\n\n"
        for e in history[:8]:
            date_str = str(e.get("date", "N/A"))[:10]
            eps_est = e.get("eps_estimate")
            eps_act = e.get("eps_actual")
            surprise = e.get("surprise_pct")

            eps_est_str = f"{eps_est:.2f}" if eps_est is not None else "N/A"
            eps_act_str = f"{eps_act:.2f}" if eps_act is not None else "N/A"

            if surprise is not None:
                s_emoji = "🟢" if surprise > 0 else "🔴" if surprise < 0 else "🟡"
                s_str = f"{surprise:+.1f}%"
            else:
                s_emoji = "⚪"
                s_str = "N/A"

            text += (
                f"  {s_emoji} {date_str} | EPS: {eps_act_str} vs {eps_est_str} | Sorpresa: {s_str}\n"
            )

        upcoming = await check_upcoming_earnings([(ticker, market)])
        if upcoming:
            e = upcoming[0]
            date_str = (
                e["earnings_date"].strftime("%d/%m/%Y")
                if hasattr(e["earnings_date"], "strftime")
                else str(e["earnings_date"])
            )
            text += f"\n📆 *Próximo earnings:* {date_str} (en {e['days_until']} días)"

        await _send_long(update, text)
        return

    await update.message.reply_text("📅 Obteniendo calendario de earnings...")

    tickers_to_check: list[tuple[str, str]] = []
    sources: dict[tuple[str, str], str] = {}

    real = await repo.get_portfolio_by_type(PortfolioType.REAL)
    if real:
        positions = await repo.get_open_positions(real.id)
        for p in positions:
            tickers_to_check.append((p.ticker, p.market))
            sources[(p.ticker, p.market)] = "📊 Cartera"

    watchlist = await repo.get_active_watchlist()
    for w in watchlist:
        key = (w.ticker, w.market)
        if key not in sources:
            tickers_to_check.append(key)
            sources[key] = "📋 Watchlist"

    if not tickers_to_check:
        await update.message.reply_text(
            "📅 Sin tickers en cartera ni watchlist para consultar earnings.\n\n"
            "Usa `/earnings TICKER` para consultar un ticker específico.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    upcoming = await check_upcoming_earnings(tickers_to_check)

    if not upcoming:
        await update.message.reply_text("📅 Sin fechas de earnings próximas.")
        return

    text = "📅 *CALENDARIO DE EARNINGS*\n\n"
    for e in upcoming:
        ticker = e["ticker"]
        market = e.get("market") or "N/A"
        days = e["days_until"]
        source = sources.get((ticker, market), "")
        date_str = (
            e["earnings_date"].strftime("%d/%m/%Y")
            if hasattr(e["earnings_date"], "strftime")
            else str(e["earnings_date"])
        )
        if days <= 3:
            d_emoji = "🔴"
        elif days <= 7:
            d_emoji = "🟡"
        else:
            d_emoji = "🟢"
        text += f"  {d_emoji} *${ticker}* ({market}) — {date_str} (en {days} días) {source}\n"

    text += (
        "\n_🔴 = 0-3 días | 🟡 = 4-7 días | 🟢 = 8+ días_\n"
        "_Usa_ `/earnings TICKER` _para ver historial_"
    )
    await _send_long(update, text)


# ── Registro de comandos ─────────────────────────────────────

COMMANDS: list[CommandInfo] = [
    CommandInfo("earnings", cmd_earnings, "Calendario de resultados"),
]
