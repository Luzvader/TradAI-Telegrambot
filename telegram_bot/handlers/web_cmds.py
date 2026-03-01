"""Handlers de acceso web: /web — genera código de acceso al dashboard."""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from telegram_bot.handlers.registry import CommandInfo
from web.auth import auth_manager, CODE_TTL_MINUTES, SESSION_TTL_HOURS

logger = logging.getLogger(__name__)


async def cmd_web(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /web — genera un código de un solo uso para acceder al dashboard."""
    code = auth_manager.generate_code()

    from config.settings import WEB_DOMAIN, WEB_PORT
    # Construir URL informativa
    if WEB_DOMAIN:
        url_hint = f"http://{WEB_DOMAIN}:{WEB_PORT}"
    else:
        url_hint = f"http://TU_IP_VPS:{WEB_PORT}"

    text = (
        "🔐 *ACCESO AL DASHBOARD WEB*\n\n"
        f"🔑 Código: `{code}`\n\n"
        f"⏱ Expira en *{CODE_TTL_MINUTES} minutos*\n"
        f"🔄 Un solo uso\n"
        f"📅 La sesión dura *{SESSION_TTL_HOURS}h*\n\n"
        f"🌐 Abre el dashboard e introduce el código:\n"
        f"`{url_hint}`\n\n"
        "⚠️ _No compartas este código con nadie_"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ── Registro de comandos ─────────────────────────────────────

COMMANDS: list[CommandInfo] = [
    CommandInfo("web", cmd_web, "Código de acceso al dashboard"),
]
