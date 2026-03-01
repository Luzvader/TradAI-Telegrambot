"""
Bot de Telegram – punto de entrada y configuración.

Usa el registro centralizado de comandos (``handlers.ALL_COMMANDS``)
para registrar handlers y el menú de Telegram en un solo lugar.
"""

import logging

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config.settings import TELEGRAM_BOT_TOKEN
from telegram_bot.decorators import authorized_only, authorized_only_callback
from telegram_bot.handlers import ALL_COMMANDS, callback_handler, unknown_command

logger = logging.getLogger(__name__)


def create_bot() -> Application:
    """Crea y configura la aplicación del bot."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN no configurado en .env")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Registrar comandos desde el registro centralizado
    for cmd in ALL_COMMANDS:
        app.add_handler(CommandHandler(cmd.name, authorized_only(cmd.handler)))

    # Handler para botones inline (confirmaciones buy/sell/strategy)
    app.add_handler(CallbackQueryHandler(authorized_only_callback(callback_handler)))

    # Handler para comandos desconocidos
    app.add_handler(
        MessageHandler(filters.COMMAND, authorized_only(unknown_command))
    )

    # Handler global de errores
    app.add_error_handler(_error_handler)

    logger.info(f"🤖 Bot de Telegram configurado ({len(ALL_COMMANDS)} comandos)")
    return app


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manejador global de errores: notifica al usuario y registra el error."""
    logger.error("Excepción en handler:", exc_info=context.error)
    if isinstance(update, Update):
        msg = update.effective_message
        if msg:
            try:
                await msg.reply_text(
                    f"⚠️ Error interno: {type(context.error).__name__}"
                )
            except Exception as e:
                logger.debug(f"No se pudo enviar mensaje de error al usuario: {e}")


async def set_bot_commands(app: Application) -> None:
    """Registra los comandos en el menú de Telegram desde el registro centralizado."""
    commands = [BotCommand(cmd.name, cmd.description) for cmd in ALL_COMMANDS]
    await app.bot.set_my_commands(commands)
