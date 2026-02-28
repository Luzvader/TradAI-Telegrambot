"""Handler de alertas de precio: /alertas ver, crear y borrar."""

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
from telegram_bot.handlers.registry import CommandInfo

logger = logging.getLogger(__name__)


async def cmd_alertas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Comando /alertas — gestiona alertas de precio personalizadas.
      /alertas                   → ver alertas activas
      /alertas crear TICKER TIPO VALOR → crear alerta
      /alertas borrar ID         → eliminar alerta
    """
    args = context.args or []

    if not args:
        alerts = await repo.get_active_alerts()
        if not alerts:
            await update.message.reply_text(
                "🔔 Sin alertas activas.\n\n"
                "*Crear una:*\n"
                "`/alertas crear AAPL precio_max 200`\n"
                "`/alertas crear MSFT precio_min 350`\n"
                "`/alertas crear AAPL rsi_max 70`\n"
                "`/alertas crear TSLA volumen 2.0`\n\n"
                "_Tipos: precio\\_max, precio\\_min, rsi\\_max, rsi\\_min, volumen_",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        text = f"🔔 *ALERTAS ACTIVAS ({len(alerts)})*\n\n"
        for a in alerts:
            text += (
                f"  🔹 ID:{a.id} — ${a.ticker} ({getattr(a, 'market', 'N/A')}) | {a.alert_type} {a.threshold:.2f}$\n"
            )
            if a.message:
                text += f"     _{a.message}_\n"
        text += "\n_Borrar:_ `/alertas borrar ID`"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return

    subcmd = args[0].lower()

    if subcmd in ("crear", "create", "add") and len(args) >= 4:
        ticker_raw = args[1].replace("$", "")

        market_arg = None
        if len(args) >= 5 and args[2].upper() in MARKETS:
            market_arg = args[2].upper()
            alert_type = args[3].lower()
            threshold_str = args[4]
            msg = " ".join(args[5:]) if len(args) > 5 else None
        else:
            alert_type = args[2].lower()
            threshold_str = args[3]
            msg = " ".join(args[4:]) if len(args) > 4 else None

        try:
            threshold = float(threshold_str)
        except ValueError:
            await update.message.reply_text("❌ Valor inválido.")
            return

        base, inferred_market = split_yfinance_suffix(ticker_raw)
        ticker = normalize_ticker(base)
        market = market_arg or inferred_market or DEFAULT_TICKER_MARKET.get(ticker, "NASDAQ")

        alert = await repo.create_custom_alert(
            ticker=ticker,
            market=market,
            alert_type=alert_type,
            threshold=threshold,
            message=msg,
        )
        await update.message.reply_text(
            f"✅ *Alerta creada* (ID: {alert.id})\n\n"
            f"📌 ${ticker} ({market}) | {alert_type} {threshold:.2f}$",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif subcmd in ("borrar", "delete", "rm") and len(args) >= 2:
        try:
            alert_id = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ ID inválido.")
            return
        deleted = await repo.delete_alert(alert_id)
        if deleted:
            await update.message.reply_text(f"✅ Alerta {alert_id} eliminada.")
        else:
            await update.message.reply_text(f"❌ Alerta {alert_id} no encontrada.")

    else:
        await update.message.reply_text(
            "❌ Subcomando no reconocido.\n\n"
            "`/alertas` — Ver\n"
            "`/alertas crear TICKER TIPO VALOR` — Crear\n"
            "`/alertas borrar ID` — Eliminar",
            parse_mode=ParseMode.MARKDOWN,
        )


# ── Registro de comandos ─────────────────────────────────────

COMMANDS: list[CommandInfo] = [
    CommandInfo("alertas", cmd_alertas, "Gestionar alertas de precio"),
]
