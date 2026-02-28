"""Decoradores de autorización para handlers de Telegram."""

import functools
import logging

from telegram import Update
from telegram.ext import ContextTypes

from config.settings import TELEGRAM_ALLOWED_USERS

logger = logging.getLogger(__name__)


def authorized_only(func):
    """Decorador: solo permite usuarios autorizados."""

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id if update.effective_user else None
        if TELEGRAM_ALLOWED_USERS and user_id not in TELEGRAM_ALLOWED_USERS:
            if update.message:
                await update.message.reply_text(
                    "⛔ No estás autorizado para usar este bot."
                )
            logger.warning(f"Acceso no autorizado: user_id={user_id}")
            return
        if update.message is None:
            return
        return await func(update, context)

    return wrapper


def authorized_only_callback(func):
    """Decorador: solo permite usuarios autorizados en callback queries."""

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id if update.effective_user else None
        if TELEGRAM_ALLOWED_USERS and user_id not in TELEGRAM_ALLOWED_USERS:
            if update.callback_query:
                await update.callback_query.answer("⛔ No autorizado", show_alert=True)
            logger.warning(f"Acceso no autorizado (callback): user_id={user_id}")
            return
        return await func(update, context)

    return wrapper
