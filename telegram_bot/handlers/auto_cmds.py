"""Handler del modo automático: /auto on|off|safe, intervalos, resumen diario."""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database import repository as repo
from database.models import AutoModeType, PortfolioType
from telegram_bot.handlers.registry import CommandInfo

logger = logging.getLogger(__name__)

_MODE_LABELS = {
    AutoModeType.OFF: "🔴 OFF",
    AutoModeType.ON: "🟢 ON (Full Auto)",
    AutoModeType.SAFE: "🛡️ SAFE (Confirmación)",
}


async def cmd_auto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Comando /auto — gestiona el modo automático.
      /auto           → estado actual
      /auto on        → activar (full auto, ejecuta solo)
      /auto off       → desactivar
      /auto safe      → activar con confirmación para operaciones
      /auto scan 30   → intervalo de scan (min)
      /auto analyze 60 → intervalo de análisis (min)
      /auto macro 120 → intervalo macro (min)
      /auto summary 9 0 → hora:min del resumen diario (España)
      /auto watchlist on|off → gestión auto
      /auto signals on|off → notificaciones
    """
    args = context.args or []

    portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
    if portfolio is None:
        await update.message.reply_text("❌ Cartera no inicializada.")
        return

    config = await repo.get_or_create_auto_mode_config(portfolio.id)

    if not args:
        mode_label = _MODE_LABELS.get(config.mode, "🔴 OFF")
        text = (
            f"🤖 *MODO AUTOMÁTICO — {mode_label}*\n\n"
            f"📋 Estrategia: {(portfolio.strategy.value if portfolio.strategy else 'value').upper()}\n"
            f"🔍 Scan: cada {config.scan_interval_minutes} min\n"
            f"📊 Análisis: cada {config.analyze_interval_minutes} min\n"
            f"🌍 Macro: cada {config.macro_interval_minutes} min\n"
            f"📋 Watchlist auto: {'Sí' if config.watchlist_auto_manage else 'No'}\n"
            f"☀️ Resumen diario: {config.daily_summary_hour:02d}:{config.daily_summary_minute:02d}\n"
            f"📡 Señales: {'Sí' if config.notify_signals else 'No'}\n\n"
            f"*Modos disponibles:*\n"
            f"  🟢 `on`   — Full auto (ejecuta operaciones solo)\n"
            f"  🛡️ `safe` — Auto + confirmación antes de operar\n"
            f"  🔴 `off`  — Desactivado\n\n"
        )
        if config.last_scan_at:
            text += f"Último scan: {config.last_scan_at.strftime('%d/%m %H:%M')}\n"
        if config.last_analyze_at:
            text += f"Último análisis: {config.last_analyze_at.strftime('%d/%m %H:%M')}\n"
        if config.last_daily_summary_at:
            text += f"Último resumen: {config.last_daily_summary_at.strftime('%d/%m %H:%M')}\n"
        text += "\n*Ejemplos:*\n"
        text += "  `/auto on` — Full auto\n"
        text += "  `/auto safe` — Auto con confirmación\n"
        text += "  `/auto off` — Desactivar\n"
        text += "  `/auto scan 30` — Scan cada 30 min\n"
        text += "  `/auto summary 9 0` — Resumen a las 9:00\n"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return

    subcmd = args[0].lower()

    if subcmd == "on":
        config = await repo.set_auto_mode(portfolio.id, AutoModeType.ON)
        await update.message.reply_text(
            "🤖 *Modo automático ACTIVADO — 🟢 FULL AUTO*\n\n"
            "Escaneo, análisis, watchlist y señales automáticas.\n"
            "⚡ Las operaciones se ejecutarán *sin confirmación*.\n"
            f"☀️ Resumen diario: {config.daily_summary_hour:02d}:{config.daily_summary_minute:02d}",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif subcmd == "safe":
        config = await repo.set_auto_mode(portfolio.id, AutoModeType.SAFE)
        await update.message.reply_text(
            "🤖 *Modo automático ACTIVADO — 🛡️ SAFE*\n\n"
            "Escaneo, análisis, watchlist y señales automáticas.\n"
            "🛡️ Las operaciones requieren *tu confirmación* antes de ejecutarse.\n"
            f"☀️ Resumen diario: {config.daily_summary_hour:02d}:{config.daily_summary_minute:02d}",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif subcmd == "off":
        await repo.set_auto_mode(portfolio.id, AutoModeType.OFF)
        await update.message.reply_text(
            "🤖 *Modo automático DESACTIVADO* 🔴",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif subcmd == "scan" and len(args) >= 2:
        try:
            minutes = int(args[1])
            if minutes < 10:
                await update.message.reply_text("⚠️ Mínimo 10 minutos.")
                return
            await repo.update_auto_mode_config(portfolio.id, scan_interval_minutes=minutes)
            await update.message.reply_text(f"✅ Scan cada *{minutes} minutos*", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ Indica un número válido.")

    elif subcmd == "analyze" and len(args) >= 2:
        try:
            minutes = int(args[1])
            if minutes < 15:
                await update.message.reply_text("⚠️ Mínimo 15 minutos.")
                return
            await repo.update_auto_mode_config(portfolio.id, analyze_interval_minutes=minutes)
            await update.message.reply_text(f"✅ Análisis cada *{minutes} minutos*", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ Indica un número válido.")

    elif subcmd == "macro" and len(args) >= 2:
        try:
            minutes = int(args[1])
            if minutes < 30:
                await update.message.reply_text("⚠️ Mínimo 30 minutos.")
                return
            await repo.update_auto_mode_config(portfolio.id, macro_interval_minutes=minutes)
            await update.message.reply_text(f"✅ Macro cada *{minutes} minutos*", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ Indica un número válido.")

    elif subcmd == "summary" and len(args) >= 2:
        try:
            hour = int(args[1])
            minute = int(args[2]) if len(args) >= 3 else 0
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            await repo.update_auto_mode_config(
                portfolio.id, daily_summary_hour=hour, daily_summary_minute=minute
            )
            await update.message.reply_text(
                f"✅ Resumen diario a las *{hour:02d}:{minute:02d}*",
                parse_mode=ParseMode.MARKDOWN,
            )
        except ValueError:
            await update.message.reply_text(
                "❌ *Ejemplo:* `/auto summary 9 0`",
                parse_mode=ParseMode.MARKDOWN,
            )

    elif subcmd == "watchlist" and len(args) >= 2:
        enabled = args[1].lower() in ("on", "si", "sí", "yes", "true", "1")
        await repo.update_auto_mode_config(portfolio.id, watchlist_auto_manage=enabled)
        await update.message.reply_text(
            f"✅ Watchlist auto *{'activada' if enabled else 'desactivada'}*",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif subcmd == "signals" and len(args) >= 2:
        enabled = args[1].lower() in ("on", "si", "sí", "yes", "true", "1")
        await repo.update_auto_mode_config(portfolio.id, notify_signals=enabled)
        await update.message.reply_text(
            f"✅ Señales *{'activadas' if enabled else 'desactivadas'}*",
            parse_mode=ParseMode.MARKDOWN,
        )

    else:
        await update.message.reply_text(
            "❌ Subcomando no reconocido.\n"
            "Usa `/auto` para ver las opciones.",
            parse_mode=ParseMode.MARKDOWN,
        )


# ── Registro de comandos ─────────────────────────────────────

COMMANDS: list[CommandInfo] = [
    CommandInfo("auto", cmd_auto, "Modo automático: /auto on|off|safe"),
]
