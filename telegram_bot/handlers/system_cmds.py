"""Handlers del sistema: /help, /costes y comando desconocido."""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database import repository as repo
from telegram_bot.handlers.registry import CommandInfo

logger = logging.getLogger(__name__)


# ── /help ────────────────────────────────────────────────────


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /help — muestra todos los comandos con ejemplos claros."""
    text = (
        "📖 *COMANDOS DISPONIBLES*\n\n"
        "*── Cartera ──*\n"
        "/cartera — Ver cartera, posiciones, señales y earnings\n"
        "/capital CANTIDAD — Establecer capital inicial\n"
        "  _Ejemplo: /capital 10000_\n\n"
        "*── Operaciones ──*\n"
        "/buy TICKER CANTIDAD PRECIO\n"
        "  _Ejemplo: /buy AAPL 10 185.50_\n"
        "/sell TICKER CANTIDAD PRECIO\n"
        "  _Ejemplo: /sell AAPL 5 200.00_\n\n"
        "*── Análisis ──*\n"
        "/analizar TICKER — Análisis completo con IA\n"
        "  _Ejemplo: /analizar MSFT_\n"
        "/scan — Escanear mejores oportunidades\n"
        "/macro — Análisis macroeconómico con IA\n"
        "/comparar TICKER1 TICKER2 — Comparar dos tickers\n"
        "  _Ejemplo: /comparar AAPL MSFT_\n\n"
        "*── Historial y Alertas ──*\n"
        "/historial — Últimas señales generadas\n"
        "/alertas — Ver alertas activas\n"
        "/alertas crear TICKER precio_max VALOR\n"
        "  _Ejemplo: /alertas crear AAPL precio\\_max 200_\n"
        "/alertas borrar ID — Eliminar una alerta\n\n"
        "*── Watchlist ──*\n"
        "/watchlist — Ver watchlist activa\n"
        "/watchlist generar — IA crea nueva watchlist\n"
        "/watchlist quitar TICKER — Quitar ticker\n"
        "  _Ejemplo: /watchlist quitar AAPL_\n\n"
        "*── Objetivos de Inversión ──*\n"
        "/objetivo — Ver todos los objetivos activos\n"
        "/objetivo TICKER — Ver objetivo de un ticker\n"
        "/objetivo TICKER tesis ... — Definir tesis\n"
        "/objetivo TICKER entrada 150 — Precio entrada\n"
        "/objetivo TICKER salida 200 — Precio salida\n"
        "/objetivo TICKER catalizadores ... — Catalizadores\n"
        "/objetivo TICKER riesgos ... — Riesgos\n"
        "/objetivo TICKER conviccion 8 — Convicción (1-10)\n"
        "/objetivo TICKER borrar — Eliminar objetivo\n\n"
        "*── Earnings ──*\n"
        "/earnings — Calendario cartera + watchlist\n"
        "/earnings TICKER — Historial de resultados\n"
        "  _Ejemplo: /earnings AAPL_\n\n"
        "*── Estrategia ──*\n"
        "/strategy — Ver estrategia activa\n"
        "/strategy TIPO — Cambiar estrategia\n"
        "  _Tipos: value, growth, dividend, balanced, conservative_\n\n"
        "*── Costes ──*\n"
        "/costes — Uso y costes de OpenAI\n\n"
        "*── Modo Auto ──*\n"
        "/auto — Ver estado\n"
        "/auto on — Activar\n"
        "/auto off — Desactivar\n"
        "/auto scan 30 — Intervalo scan (min)\n"
        "/auto analyze 60 — Intervalo análisis (min)\n"
        "/auto summary 9 0 — Hora resumen diario\n\n"
        "*── Trading212 Broker ──*\n"
        "/broker — Estado del broker (cuenta, posiciones)\n"
        "/broker sync — Sincronizar posiciones broker ↔ local\n"
        "/broker import — Importar posiciones del broker\n"
        "/broker buscar TICKER — Buscar instrumento en T212\n"
        "/broker historial — Historial de órdenes\n"
        "/broker ordenes — Órdenes pendientes\n"
        "/broker cancelar ID — Cancelar orden\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ── /costes ──────────────────────────────────────────────────


async def cmd_costes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /costes — muestra uso y costes de OpenAI."""
    args = context.args or []
    days = 30
    if args:
        try:
            days = int(args[0])
        except ValueError:
            pass

    usage = await repo.get_openai_usage_summary(days=days)
    text = (
        f"🤖 *USO DE OPENAI ({days} días)*\n\n"
        f"📊 Llamadas: {usage['total_calls']}\n"
        f"🔤 Tokens: {usage['total_tokens']:,}\n"
        f"💵 Coste estimado: {usage['total_cost_usd']:.4f}$\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ── Comando desconocido ──────────────────────────────────────


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para comandos no reconocidos."""
    await update.message.reply_text(
        "❓ Comando no reconocido. Usa /help para ver los disponibles."
    )


# ── Registro de comandos ─────────────────────────────────────

COMMANDS: list[CommandInfo] = [
    CommandInfo("help", cmd_help, "Ayuda y lista de comandos"),
    CommandInfo("costes", cmd_costes, "Uso y costes de OpenAI"),
]
