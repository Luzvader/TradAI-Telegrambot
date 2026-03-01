"""Handler de objetivos de inversión: /objetivo ver, crear, editar y borrar."""

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
from database import repository as repo
from telegram_bot.handlers.helpers import _send_long
from telegram_bot.handlers.registry import CommandInfo

logger = logging.getLogger(__name__)


async def cmd_objetivo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Comando /objetivo — gestiona objetivos de inversión por empresa.
    """
    args = context.args or []

    if not args:
        objectives = await repo.get_all_active_objectives()
        if not objectives:
            await update.message.reply_text(
                "🎯 Sin objetivos de inversión definidos.\n\n"
                "*Crear uno:*\n"
                "`/objetivo AAPL tesis Value play con margen de seguridad`\n"
                "`/objetivo AAPL entrada 150`\n"
                "`/objetivo AAPL salida 200`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        text = f"🎯 *OBJETIVOS DE INVERSIÓN ({len(objectives)})*\n\n"
        for obj in objectives:
            source_emoji = "🤖" if obj.source == "ai" else "👤"
            text += f"{source_emoji} *${obj.ticker}* ({obj.market})\n"
            if obj.thesis:
                text += f"   📝 {obj.thesis}\n"
            targets = []
            if obj.target_entry_price:
                targets.append(f"Entrada: {obj.target_entry_price:.2f}$")
            if obj.target_exit_price:
                targets.append(f"Salida: {obj.target_exit_price:.2f}$")
            if targets:
                text += f"   🎯 {' | '.join(targets)}\n"
            if obj.conviction:
                text += f"   💪 Convicción: {obj.conviction}/10 | Horizonte: {obj.time_horizon or 'N/A'}\n"
            if obj.catalysts:
                text += f"   🚀 {obj.catalysts}\n"
            if obj.risks:
                text += f"   ⚠️ {obj.risks}\n"
            text += "\n"
        await _send_long(update, text)
        return

    ticker_raw = args[0].replace("$", "")
    remaining = args[1:]

    explicit_market = None
    if remaining and remaining[0].upper() in MARKETS:
        explicit_market = remaining[0].upper()
        remaining = remaining[1:]

    base, inferred_market = split_yfinance_suffix(ticker_raw)
    ticker = normalize_ticker(base)
    market = explicit_market or inferred_market or DEFAULT_TICKER_MARKET.get(ticker, "NASDAQ")

    if not remaining:
        obj = await repo.get_investment_objective(ticker, market=market)
        if not obj:
            await update.message.reply_text(
                f"🎯 Sin objetivo definido para ${ticker} ({market}).\n\n"
                f"`/objetivo {ticker} {market} tesis Tu tesis aquí`\n"
                f"`/objetivo {ticker} {market} entrada 150`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        source_emoji = "🤖" if obj.source == "ai" else "👤"
        text = f"🎯 *OBJETIVO — ${ticker}* ({market}) {source_emoji}\n\n"
        if obj.thesis:
            text += f"📝 *Tesis:* {obj.thesis}\n"
        if obj.target_entry_price:
            text += f"🎯 Entrada: {obj.target_entry_price:.2f}$\n"
        if obj.target_exit_price:
            text += f"🎯 Salida: {obj.target_exit_price:.2f}$\n"
        if obj.catalysts:
            text += f"🚀 Catalizadores: {obj.catalysts}\n"
        if obj.risks:
            text += f"⚠️ Riesgos: {obj.risks}\n"
        if obj.conviction:
            text += f"💪 Convicción: {obj.conviction}/10\n"
        if obj.time_horizon:
            text += f"⏰ Horizonte: {obj.time_horizon}\n"
        text += f"\n_Actualizado: {obj.updated_at.strftime('%d/%m/%Y %H:%M') if obj.updated_at else 'N/A'}_"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return

    subcmd = remaining[0].lower()
    subargs = remaining[1:]

    if subcmd == "borrar":
        deleted = await repo.deactivate_objective(ticker, market=market)
        if deleted:
            await update.message.reply_text(f"✅ Objetivo de ${ticker} ({market}) eliminado.")
        else:
            await update.message.reply_text(f"❌ No hay objetivo activo para ${ticker} ({market}).")

    elif subcmd == "entrada" and len(subargs) >= 1:
        try:
            price = float(subargs[0])
            await repo.save_investment_objective(
                ticker=ticker, market=market, target_entry_price=price, source="manual"
            )
            await update.message.reply_text(
                f"✅ Precio de entrada para ${ticker}: *{price:.2f}$*",
                parse_mode=ParseMode.MARKDOWN,
            )
        except ValueError:
            await update.message.reply_text("❌ Precio inválido.")

    elif subcmd == "salida" and len(subargs) >= 1:
        try:
            price = float(subargs[0])
            await repo.save_investment_objective(
                ticker=ticker, market=market, target_exit_price=price, source="manual"
            )
            await update.message.reply_text(
                f"✅ Precio de salida para ${ticker}: *{price:.2f}$*",
                parse_mode=ParseMode.MARKDOWN,
            )
        except ValueError:
            await update.message.reply_text("❌ Precio inválido.")

    elif subcmd == "tesis" and len(subargs) >= 1:
        thesis_text = " ".join(subargs)
        await repo.save_investment_objective(
            ticker=ticker, market=market, thesis=thesis_text, source="manual"
        )
        await update.message.reply_text(
            f"✅ Tesis para ${ticker} guardada.",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif subcmd in ("catalizadores", "catalysts") and len(subargs) >= 1:
        cat_text = " ".join(subargs)
        await repo.save_investment_objective(
            ticker=ticker, market=market, catalysts=cat_text, source="manual"
        )
        await update.message.reply_text(f"✅ Catalizadores para ${ticker} guardados.")

    elif subcmd in ("riesgos", "risks") and len(subargs) >= 1:
        risk_text = " ".join(subargs)
        await repo.save_investment_objective(
            ticker=ticker, market=market, risks=risk_text, source="manual"
        )
        await update.message.reply_text(f"✅ Riesgos para ${ticker} guardados.")

    elif subcmd in ("conviccion", "conviction") and len(subargs) >= 1:
        try:
            conv = int(subargs[0])
            if not 1 <= conv <= 10:
                raise ValueError
            await repo.save_investment_objective(
                ticker=ticker, market=market, conviction=conv, source="manual"
            )
            await update.message.reply_text(f"✅ Convicción para ${ticker}: *{conv}/10*", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ Convicción debe ser 1-10.")

    else:
        await update.message.reply_text(
            "❌ Subcomando no reconocido.\n\n"
            "`/objetivo` — Ver todos\n"
            "`/objetivo TICKER` — Ver uno\n"
            "`/objetivo TICKER tesis ...` — Definir tesis\n"
            "`/objetivo TICKER entrada 150` — Precio entrada\n"
            "`/objetivo TICKER salida 200` — Precio salida\n"
            "`/objetivo TICKER catalizadores ...` — Catalizadores\n"
            "`/objetivo TICKER riesgos ...` — Riesgos\n"
            "`/objetivo TICKER conviccion 8` — Convicción 1-10\n"
            "`/objetivo TICKER borrar` — Eliminar",
            parse_mode=ParseMode.MARKDOWN,
        )


# ── Registro de comandos ─────────────────────────────────────

COMMANDS: list[CommandInfo] = [
    CommandInfo("objetivo", cmd_objetivo, "Objetivos: /objetivo TICKER"),
]
