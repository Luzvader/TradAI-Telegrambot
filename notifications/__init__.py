"""
Sistema de notificaciones compartido.
Centraliza el envío de mensajes por Telegram y otros canales.
"""

import logging
from typing import Any

from telegram import Bot
from telegram.constants import ParseMode

from config.settings import TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

# ── Referencia global al bot ─────────────────────────────────
_bot: Bot | None = None

# ── Canales de notificación registrados ──────────────────────
_channels: list[Any] = []  # Para futuras extensiones (email, Discord, etc.)


def set_notification_bot(bot: Bot | None) -> None:
    """Establece la referencia global al bot de Telegram."""
    global _bot
    _bot = bot


def get_notification_bot() -> Bot | None:
    """Devuelve la referencia global al bot de Telegram."""
    return _bot


async def notify_telegram(text: str, chat_id: str | None = None) -> None:
    """Envía notificación por Telegram con soporte de mensajes largos."""
    target_chat = chat_id or TELEGRAM_CHAT_ID
    if _bot is None or not target_chat:
        return

    try:
        max_len = 4000
        for i in range(0, len(text), max_len):
            chunk = text[i:i + max_len]
            try:
                await _bot.send_message(
                    chat_id=target_chat,
                    text=chunk,
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception:
                # Fallback sin parse_mode si falla el Markdown
                await _bot.send_message(chat_id=target_chat, text=chunk)
    except Exception as e:
        logger.error(f"Error enviando notificación Telegram: {e}")


async def notify(text: str) -> None:
    """
    Envía notificación por todos los canales configurados.
    Por ahora solo Telegram, extensible a email/Discord/webhooks.
    """
    await notify_telegram(text)

    # Canales adicionales (extensible)
    for channel in _channels:
        try:
            await channel.send(text)
        except Exception as e:
            logger.warning(f"Error en canal de notificación {channel}: {e}")
