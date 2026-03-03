"""
Handlers de comandos de Telegram para eToro broker.

Comandos:
  /broker              — Estado del broker (cuenta, posiciones, órdenes)
  /broker sync         — Sincronizar posiciones broker ↔ BD local
  /broker import       — Importar posiciones del broker a la BD local
  /broker buscar TICK  — Buscar instrumento en eToro
  /broker ordenes      — Órdenes pendientes
  /broker cancelar ID  — Cancelar orden pendiente
  /broker dividendos   — Historial dividendos
  /broker cash         — Detalle de cash
"""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config.settings import (
    ETORO_API_KEY,
    ETORO_USER_KEY,
    ETORO_AUTO_EXECUTE,
    ETORO_REQUIRE_EXECUTION,
    ETORO_MODE,
)
from telegram_bot.handlers.helpers import _send_long
from telegram_bot.handlers.registry import CommandInfo

logger = logging.getLogger(__name__)


async def cmd_broker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /broker — Comando principal del broker eToro.
    Sin argumentos muestra el estado general.
    """
    if not ETORO_API_KEY or not ETORO_USER_KEY:
        await update.message.reply_text(
            "⚠️ *eToro no configurado*\n\n"
            "Añade en `.env`:\n"
            "```\n"
            "ETORO_API_KEY=tu_api_key\n"
            "ETORO_USER_KEY=tu_user_key\n"
            "ETORO_MODE=demo\n"
            "ETORO_AUTO_EXECUTE=true\n"
            "ETORO_REQUIRE_EXECUTION=true\n"
            "```",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    args = context.args or []
    if not args:
        await _broker_status(update)
    elif args[0].lower() == "sync":
        await _broker_sync(update)
    elif args[0].lower() == "import":
        await _broker_import(update)
    elif args[0].lower() in ("buscar", "search"):
        query = " ".join(args[1:]) if len(args) > 1 else ""
        await _broker_search(update, query)
    elif args[0].lower() in ("ordenes", "orders"):
        await _broker_orders(update)
    elif args[0].lower() in ("cancelar", "cancel"):
        order_id = args[1] if len(args) > 1 else ""
        await _broker_cancel(update, order_id)
    elif args[0].lower() in ("dividendos", "dividends"):
        await _broker_dividends(update)
    elif args[0].lower() == "cash":
        await _broker_cash(update)
    else:
        await update.message.reply_text(
            "❓ Subcomando no reconocido. Opciones:\n"
            "/broker — Estado general\n"
            "/broker sync — Sincronizar posiciones\n"
            "/broker import — Importar posiciones\n"
            "/broker buscar TICKER — Buscar instrumento\n"
            "/broker ordenes — Órdenes pendientes\n"
            "/broker cancelar ID — Cancelar orden\n"
            "/broker dividendos — Historial dividendos\n"
            "/broker cash — Detalle de cash",
        )


async def _broker_status(update: Update) -> None:
    """Muestra el estado completo del broker."""
    await update.message.reply_text("⏳ Consultando eToro...")

    from broker.bridge import get_broker_status
    status = await get_broker_status()

    if not status.get("connected"):
        await update.message.reply_text(
            f"❌ *Broker desconectado*\n{status.get('error', '')}",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    mode_emoji = "🟢" if status["mode"] == "real" else "🔵"
    auto_emoji = "✅" if status["auto_execute"] else "❌"
    req_emoji = "✅" if status.get("require_execution", ETORO_REQUIRE_EXECUTION) else "❌"

    lines = [
        f"🏦 *eToro — {status['mode'].upper()}*",
        f"{mode_emoji} Modo: {status['mode'].upper()}",
        f"{auto_emoji} Auto-ejecutar: {'Sí' if status['auto_execute'] else 'No'}",
        f"{req_emoji} Ejecución obligatoria: {'Sí' if status.get('require_execution', ETORO_REQUIRE_EXECUTION) else 'No'}",
        "",
    ]

    # Cuenta
    if "account" in status:
        acc = status["account"]
        lines.extend([
            "💰 *Cuenta*",
            f"  Cash disponible: {acc['cash']:,.2f} {acc.get('currency', 'USD')}",
            f"  Invertido: {acc['invested']:,.2f} {acc.get('currency', 'USD')}",
            f"  Valor total: {acc['portfolio_value']:,.2f} {acc.get('currency', 'USD')}",
            f"  PnL: {acc['pnl']:+,.2f}",
            "",
        ])
    elif "account_error" in status:
        lines.append(f"⚠️ Error cuenta: {status['account_error']}\n")

    # Posiciones
    if "positions" in status:
        n = status.get("num_positions", 0)
        lines.append(f"📊 *Posiciones abiertas ({n})*")
        for p in status["positions"][:15]:
            pnl_emoji = "🟢" if p["pnl"] >= 0 else "🔴"
            name = p.get("name", p["ticker"])
            lines.append(
                f"  {pnl_emoji} *{p['ticker']}* ({name})\n"
                f"    {p['shares']:.2f} acc | "
                f"Avg: {p['avg_price']:.2f} | "
                f"Actual: {p['current_price']:.2f} | "
                f"PnL: {p['pnl']:+.2f} ({p['pnl_pct']:+.1f}%)"
            )
        if n > 15:
            lines.append(f"  _... y {n - 15} más_")
        lines.append("")
    elif "positions_error" in status:
        lines.append(f"⚠️ Error posiciones: {status['positions_error']}\n")

    # Órdenes pendientes
    if "pending_orders" in status and status["pending_orders"]:
        lines.append(f"📋 *Órdenes pendientes ({len(status['pending_orders'])})*")
        for o in status["pending_orders"]:
            price_str = f"@ {o['price']}" if o['price'] else "market"
            lines.append(
                f"  {o['side']} {o['ticker']}: {o['shares']} acc {price_str} "
                f"[{o['status']}] ID: `{o['id']}`"
            )
        lines.append("")

    text = "\n".join(lines)
    await _send_long(update, text)


async def _broker_sync(update: Update) -> None:
    """Sincroniza posiciones broker ↔ BD local."""
    await update.message.reply_text("🔄 Sincronizando posiciones...")

    from broker.bridge import sync_broker_positions
    from database import repository as repo
    from database.models import PortfolioType

    portfolio = await repo.get_or_create_portfolio("Principal", PortfolioType.REAL)
    result = await sync_broker_positions(portfolio.id)

    if not result.get("success"):
        await update.message.reply_text(
            f"❌ Error: {result.get('error', 'desconocido')}",
        )
        return

    lines = [
        f"🔄 *Sincronización eToro ({result['mode'].upper()})*\n",
        result["summary"],
        "",
    ]

    if result["only_broker"]:
        lines.append("*🔵 Solo en broker (no en TradAI):*")
        for p in result["only_broker"]:
            lines.append(
                f"  • {p['ticker']}: "
                f"{p['shares']:.2f} acc @ {p['avg_price']:.2f}"
            )
        lines.append("  _Usa /broker import para importarlas_\n")

    if result["only_local"]:
        lines.append("*🟡 Solo en TradAI (no en broker):*")
        for p in result["only_local"]:
            lines.append(
                f"  • {p['ticker']}: {p['shares']:.2f} acc @ {p['avg_price']:.2f}"
            )
        lines.append("")

    if result["mismatched"]:
        lines.append("*⚠️ Discrepancias:*")
        for p in result["mismatched"]:
            lines.append(
                f"  • {p['ticker']}: "
                f"broker={p['broker_shares']:.2f} / local={p['local_shares']:.2f}"
            )

    await _send_long(update, "\n".join(lines))


async def _broker_import(update: Update) -> None:
    """Importa posiciones del broker a TradAI."""
    await update.message.reply_text("📥 Importando posiciones del broker...")

    from broker.bridge import import_broker_positions
    from database import repository as repo
    from database.models import PortfolioType

    portfolio = await repo.get_or_create_portfolio("Principal", PortfolioType.REAL)
    result = await import_broker_positions(portfolio.id)

    if not result.get("success"):
        await update.message.reply_text(
            f"❌ Error: {result.get('error', 'desconocido')}",
        )
        return

    lines = [
        "📥 *Importación completada*\n",
        f"Total en broker: {result['total']}",
        f"✅ Importadas nuevas: {result['imported']}",
        f"🔄 Actualizadas: {result['updated']}",
    ]

    if result.get("errors"):
        lines.append(f"\n⚠️ Errores ({len(result['errors'])}):")
        for err in result["errors"][:5]:
            lines.append(f"  • {err}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def _broker_search(update: Update, query: str) -> None:
    """Busca un instrumento en eToro."""
    if not query:
        await update.message.reply_text(
            "Uso: /broker buscar TICKER\nEjemplo: /broker buscar AAPL",
        )
        return

    from broker.etoro import get_etoro_client

    client = get_etoro_client()
    if client is None:
        await update.message.reply_text("❌ Broker no inicializado")
        return

    await update.message.reply_text(f"🔍 Buscando '{query}'...")

    result = await client.search_instrument(query)
    if not result.success:
        await update.message.reply_text(f"❌ Error: {result.error}")
        return

    if not result.data:
        await update.message.reply_text(f"No se encontró '{query}' en eToro")
        return

    lines = [f"🔍 *Resultados para '{query}'* ({len(result.data)})\n"]
    for inst in result.data[:10]:
        tradable = "✅" if inst.get("tradable") else "❌"
        lines.append(
            f"  • *{inst.get('symbol', '?')}* (ID: {inst.get('instrument_id', '?')})\n"
            f"    {inst.get('name', 'N/A')} | {inst.get('type', 'N/A')}\n"
            f"    Operable: {tradable}"
        )

    await _send_long(update, "\n".join(lines))


async def _broker_orders(update: Update) -> None:
    """Muestra órdenes pendientes."""
    from broker.etoro import get_etoro_client

    client = get_etoro_client()
    if client is None:
        await update.message.reply_text("❌ Broker no inicializado")
        return

    result = await client.get_orders()
    if not result.success:
        await update.message.reply_text(f"❌ Error: {result.error}")
        return

    if not result.data:
        await update.message.reply_text("No hay órdenes pendientes 📋")
        return

    lines = [f"📋 *Órdenes pendientes ({len(result.data)})*\n"]
    for o in result.data:
        price_str = f"@ {o.price}" if o.price else "market"
        lines.append(
            f"  {'🟢' if o.side == 'BUY' else '🔴'} *{o.ticker}* "
            f"{o.side}: {o.shares:.2f} acc {price_str}\n"
            f"    Estado: {o.status} | ID: `{o.order_id}`"
        )

    await _send_long(update, "\n".join(lines))


async def _broker_cancel(update: Update, order_id: str) -> None:
    """Cancela una orden pendiente."""
    if not order_id:
        await update.message.reply_text(
            "Uso: /broker cancelar ORDER\\_ID\n"
            "Obtén IDs con /broker ordenes",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    from broker.bridge import broker_cancel_order

    result = await broker_cancel_order(order_id)
    if result.success:
        await update.message.reply_text(f"✅ Orden `{order_id}` cancelada")
    else:
        await update.message.reply_text(f"❌ Error: {result.error}")


async def _broker_dividends(update: Update) -> None:
    """Muestra historial de dividendos."""
    from broker.bridge import get_broker_dividend_history

    await update.message.reply_text("💰 Obteniendo historial de dividendos...")

    divs = await get_broker_dividend_history(limit=30)
    if not divs:
        await update.message.reply_text(
            "eToro no expone dividendos vía API.\n"
            "Los dividendos se detectan mediante yfinance."
        )
        return

    total = sum(d.get("amount", 0) for d in divs)
    lines = [f"💰 *Dividendos* ({len(divs)} últimos)\n"]

    for d in divs[:20]:
        ticker = d.get("ticker", "?")
        amount = d.get("amount", 0)
        quantity = d.get("quantity", 0)
        date = d.get("paid_on", "")[:10]
        lines.append(
            f"  📌 *{ticker}* — ${amount:.2f} ({quantity:.2f} acc) | {date}"
        )

    if len(divs) > 20:
        lines.append(f"  _... y {len(divs) - 20} más_")

    lines.append(f"\n💵 *Total: ${total:,.2f}*")
    await _send_long(update, "\n".join(lines))


async def _broker_cash(update: Update) -> None:
    """Muestra detalle de cash del broker eToro."""
    from broker.etoro import get_etoro_client

    client = get_etoro_client()
    if client is None:
        await update.message.reply_text("❌ Broker no inicializado")
        return

    result = await client.get_account()
    if not result.success:
        await update.message.reply_text(f"❌ Error: {result.error}")
        return

    acc = result.data
    text = (
        f"💰 *eToro Cash — {acc.mode.upper()}*\n\n"
        f"💵 Cash total: {acc.cash:,.2f} {acc.currency}\n"
        f"📊 Invertido: {acc.invested:,.2f} {acc.currency}\n"
        f"💎 Valor total: {acc.portfolio_value:,.2f} {acc.currency}\n"
        f"{'🟢' if acc.pnl >= 0 else '🔴'} PnL: {acc.pnl:+,.2f}\n"
    )
    await _send_long(update, text)


# ── Registro de comandos ─────────────────────────────────────

COMMANDS: list[CommandInfo] = [
    CommandInfo("broker", cmd_broker, "eToro: /broker [sync|import|buscar|ordenes]"),
]
