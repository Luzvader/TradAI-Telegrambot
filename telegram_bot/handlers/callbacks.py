"""Handler de callback queries (botones inline: buy/sell confirm, strategy set)."""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config.markets import market_display
from database import repository as repo
from database.models import PortfolioType, StrategyType
from portfolio.portfolio_manager import execute_buy, execute_sell
from telegram_bot.handlers.helpers import _escape_md

logger = logging.getLogger(__name__)


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja las pulsaciones de botones inline."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    data = query.data or ""

    # ── Buy confirm ──
    if data.startswith("buy_confirm:"):
        parts = data.split(":")
        if len(parts) == 5:
            ticker, market = parts[1], parts[2]
            shares, price = float(parts[3]), float(parts[4])
        elif len(parts) == 4:
            ticker, market = parts[1], "NASDAQ"
            shares, price = float(parts[2]), float(parts[3])
        else:
            await query.edit_message_text("❌ Datos inválidos.")
            return

        portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
        if portfolio is None:
            await query.edit_message_text("❌ Cartera no inicializada.")
            return

        mkt_name = market_display(market)
        await query.edit_message_text(
            f"⏳ Comprando {shares} acc de {ticker} ({mkt_name}) a {price}$..."
        )

        result = await execute_buy(
            portfolio_id=portfolio.id,
            ticker=ticker,
            market=market,
            price=price,
            shares=shares,
        )

        if result["success"]:
            text = "✅ *COMPRA ejecutada*\n\n"
            text += f"📌 Ticker: {_escape_md(ticker)} ({_escape_md(mkt_name)})\n"
            text += f"💵 Precio: {price}$\n"
            text += f"📊 Acciones: {result.get('shares', shares):.4f}\n"
            text += f"💰 Total: {result.get('amount', 0):.2f}$\n"
            if result.get("broker_executed"):
                text += "🏦 Broker: Trading212 ✅\n"
                if result.get("broker_order"):
                    text += f"🧾 Orden: `{result['broker_order']}`\n"
            elif result.get("broker_note"):
                text += f"🏦 Broker: ⚠️ {result['broker_note']}\n"
            if "stop_loss" in result:
                text += f"\n🛡️ Stop-Loss: {result['stop_loss']}$\n"
                text += f"🎯 Take-Profit: {result['take_profit']}$\n"
            warnings = result.get("risk_warnings", [])
            if warnings:
                text += "\n⚠️ *Riesgos:*\n"
                for w in warnings:
                    text += f"  • {w}\n"
        else:
            text = f"❌ *Error:* {result['error']}"

        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await query.edit_message_text(text)

    elif data == "buy_cancel":
        await query.edit_message_text("❌ Compra cancelada.")

    # ── Sell confirm ──
    elif data.startswith("sell_confirm:"):
        parts = data.split(":")
        if len(parts) == 5:
            ticker, market = parts[1], parts[2]
            shares, price = float(parts[3]), float(parts[4])
        elif len(parts) == 4:
            ticker, market = parts[1], "NASDAQ"
            shares, price = float(parts[2]), float(parts[3])
        else:
            await query.edit_message_text("❌ Datos inválidos.")
            return

        portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
        if portfolio is None:
            await query.edit_message_text("❌ Cartera no inicializada.")
            return

        mkt_name = market_display(market)
        await query.edit_message_text(
            f"⏳ Vendiendo {shares} acc de {ticker} ({mkt_name}) a {price}$..."
        )

        result = await execute_sell(
            portfolio_id=portfolio.id,
            ticker=ticker,
            market=market,
            price=price,
            shares_to_sell=shares,
        )

        if result["success"]:
            text = "✅ *VENTA ejecutada*\n\n"
            text += f"📌 Ticker: {_escape_md(ticker)} ({_escape_md(mkt_name)})\n"
            text += f"💵 Precio: {price}$\n"
            text += f"📊 Acciones vendidas: {result.get('shares_sold', shares):.4f}\n"
            text += f"💰 Total: {result.get('amount', 0):.2f}$\n"
            if result.get("broker_executed"):
                text += "🏦 Broker: Trading212 ✅\n"
                if result.get("broker_order"):
                    text += f"🧾 Orden: `{result['broker_order']}`\n"
            elif result.get("broker_note"):
                text += f"🏦 Broker: ⚠️ {result['broker_note']}\n"
            if "pnl" in result:
                pnl_emoji = "🟢" if result["pnl"] >= 0 else "🔴"
                text += f"\n{pnl_emoji} PnL: {result['pnl']:+.2f}$ ({result['pnl_pct']:+.2f}%)\n"
        else:
            text = f"❌ *Error:* {result['error']}"

        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await query.edit_message_text(text)

    elif data == "sell_cancel":
        await query.edit_message_text("❌ Venta cancelada.")

    # ── Strategy set ──
    elif data.startswith("strategy_set:"):
        strategy_name = data.split(":")[1]
        valid = {s.value: s for s in StrategyType}
        if strategy_name not in valid:
            await query.edit_message_text(f"❌ Estrategia '{strategy_name}' no válida.")
            return

        portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
        if portfolio is None:
            await query.edit_message_text("❌ Cartera no inicializada.")
            return

        success = await repo.set_portfolio_strategy(portfolio.id, valid[strategy_name])
        if success:
            await query.edit_message_text(
                f"✅ *Estrategia cambiada a {strategy_name.upper()}*\n\n"
                f"Las señales y análisis ahora usarán esta estrategia.",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await query.edit_message_text("❌ Error al cambiar la estrategia.")

    # ── Auto mode SAFE: buy confirm ──
    elif data.startswith("auto_buy:"):
        parts = data.split(":")
        if len(parts) != 5:
            await query.edit_message_text("❌ Datos inválidos.")
            return
        ticker, market = parts[1], parts[2]
        shares, price = float(parts[3]), float(parts[4])

        portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
        if portfolio is None:
            await query.edit_message_text("❌ Cartera no inicializada.")
            return

        mkt_name = market_display(market)
        await query.edit_message_text(
            f"⏳ 🛡️ SAFE — Comprando {shares:.4f} acc de {ticker} ({mkt_name}) a {price}$..."
        )

        result = await execute_buy(
            portfolio_id=portfolio.id,
            ticker=ticker,
            market=market,
            price=price,
            shares=shares,
        )

        if result["success"]:
            text = "🛡️ *SAFE — COMPRA ejecutada* ✅\n\n"
            text += f"📌 Ticker: {_escape_md(ticker)} ({_escape_md(mkt_name)})\n"
            text += f"💵 Precio: {price}$\n"
            text += f"📊 Acciones: {result.get('shares', shares):.4f}\n"
            text += f"💰 Total: {result.get('amount', 0):.2f}$\n"
            if result.get("broker_executed"):
                text += "🏦 Broker: Trading212 ✅\n"
            if "stop_loss" in result:
                text += f"\n🛡️ Stop-Loss: {result['stop_loss']}$\n"
                text += f"🎯 Take-Profit: {result['take_profit']}$\n"
        else:
            text = f"❌ *Error:* {result['error']}"

        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await query.edit_message_text(text)

    # ── Auto mode SAFE: sell confirm ──
    elif data.startswith("auto_sell:"):
        parts = data.split(":")
        if len(parts) != 5:
            await query.edit_message_text("❌ Datos inválidos.")
            return
        ticker, market = parts[1], parts[2]
        shares, price = float(parts[3]), float(parts[4])

        portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
        if portfolio is None:
            await query.edit_message_text("❌ Cartera no inicializada.")
            return

        mkt_name = market_display(market)
        await query.edit_message_text(
            f"⏳ 🛡️ SAFE — Vendiendo {shares:.4f} acc de {ticker} ({mkt_name}) a {price}$..."
        )

        result = await execute_sell(
            portfolio_id=portfolio.id,
            ticker=ticker,
            market=market,
            price=price,
            shares_to_sell=shares,
        )

        if result["success"]:
            text = "🛡️ *SAFE — VENTA ejecutada* ✅\n\n"
            text += f"📌 Ticker: {_escape_md(ticker)} ({_escape_md(mkt_name)})\n"
            text += f"💵 Precio: {price}$\n"
            text += f"📊 Acciones vendidas: {result.get('shares_sold', shares):.4f}\n"
            text += f"💰 Total: {result.get('amount', 0):.2f}$\n"
            if result.get("broker_executed"):
                text += "🏦 Broker: Trading212 ✅\n"
            if "pnl" in result:
                pnl_emoji = "🟢" if result["pnl"] >= 0 else "🔴"
                text += f"\n{pnl_emoji} PnL: {result['pnl']:+.2f}$ ({result['pnl_pct']:+.2f}%)\n"
        else:
            text = f"❌ *Error:* {result['error']}"

        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await query.edit_message_text(text)

    # ── Auto mode SAFE: reject ──
    elif data == "auto_reject":
        await query.edit_message_text("🛡️ Operación rechazada por el usuario.")
