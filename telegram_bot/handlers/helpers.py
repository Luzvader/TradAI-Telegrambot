"""Helpers y constantes compartidas por los handlers de Telegram."""

import re
from typing import Any

from telegram import Update
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

from config.markets import (
    DEFAULT_TICKER_MARKET,
    normalize_ticker,
    split_yfinance_suffix,
)

# ── Constantes de validación ─────────────────────────────────
MAX_SHARES = 1_000_000
MIN_SHARES = 0.0001
MAX_PRICE = 1_000_000


def _escape_md(text: str) -> str:
    """Escapa caracteres especiales de Telegram MarkdownV1.

    Usa la implementación oficial de python-telegram-bot.
    """
    return escape_markdown(str(text), version=1)


def resolve_ticker(raw: str) -> tuple[str, str]:
    """Normaliza un ticker crudo y resuelve su mercado.

    Devuelve (ticker_normalizado, mercado).
    """
    base, inferred_market = split_yfinance_suffix(raw)
    ticker = normalize_ticker(base)
    market = inferred_market or DEFAULT_TICKER_MARKET.get(ticker, "NASDAQ")
    return ticker, market


def _parse_buy_sell(text: str) -> dict[str, Any] | None:
    """
    Parsea un comando de compra/venta:
      /buy AAPL 10 150.5
      /sell MSFT 5 320.0
    Acepta ticker con o sin $.  También funciona con @botname.
    """
    pattern = r"/(?:buy|sell|comprar|vender)(?:@\S+)?\s+\$?([A-Za-z.\-]+)\s+([\d.]+)\s+([\d.]+)"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None

    ticker = match.group(1).upper()
    shares = float(match.group(2))
    price = float(match.group(3))

    if price <= 0 or price > MAX_PRICE:
        return None
    if shares < MIN_SHARES or shares > MAX_SHARES:
        return None

    return {"ticker": ticker, "shares": shares, "price": price}


async def _send_long(update: Update, text: str) -> None:
    """Envía mensajes largos dividiéndolos si es necesario."""
    if update.message is None:
        return
    max_len = 4000
    for i in range(0, len(text), max_len):
        chunk = text[i : i + max_len]
        try:
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await update.message.reply_text(chunk)
