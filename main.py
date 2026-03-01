"""
TradAI – Punto de entrada principal.

Arranca:
  1. Base de datos (PostgreSQL)
  2. Portfolios (real + backtest)
  3. Scheduler (tareas periódicas)
  4. Bot de Telegram (polling)
"""

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler

from config.settings import LOG_DIR, LOG_LEVEL, validate_settings
from config.settings import WEB_ENABLED, WEB_HOST, WEB_PORT
from database.connection import close_db, init_db
from portfolio.portfolio_manager import init_portfolios
from scheduler.jobs import init_scheduler
from telegram_bot.bot import create_bot, set_bot_commands


def setup_logging() -> None:
    """Configura logging a consola y archivo."""
    log_format = "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    handlers = [
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(
            LOG_DIR / "tradai.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        ),
    ]

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
    )

    # Silenciar logs ruidosos de librerías externas
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)


async def main() -> None:
    """Función principal asíncrona."""
    logger = logging.getLogger("tradai")
    logger.info("=" * 60)
    logger.info("🚀 TradAI — Arrancando...")
    logger.info("=" * 60)

    for warning in validate_settings():
        logger.warning(f"⚙️ Config: {warning}")

    # 1. Inicializar base de datos
    logger.info("📦 Inicializando base de datos...")
    await init_db()

    # 2. Inicializar portfolios
    logger.info("📁 Inicializando portfolios...")
    portfolios = await init_portfolios()
    logger.info(
        f"   Real: ID={portfolios['real'].id} | "
        f"Backtest: ID={portfolios['backtest'].id}"
    )

    # 2b. Inicializar broker Trading212
    from config.settings import TRADING212_API_KEY, TRADING212_API_SECRET, TRADING212_MODE
    if TRADING212_API_KEY and TRADING212_API_SECRET:
        from broker.trading212 import init_trading212_dual
        try:
            clients = init_trading212_dual(
                TRADING212_API_KEY, TRADING212_API_SECRET, TRADING212_MODE,
            )
            modes = ", ".join(m.upper() for m in clients)
            logger.info(f"🏦 Trading212 broker inicializado ({modes})")

            # Sincronizar capital desde T212 (REAL←live, BACKTEST←demo)
            from broker.bridge import sync_all_capitals
            try:
                cap_results = await sync_all_capitals()
                for mode, r in cap_results.items():
                    if r.get("success"):
                        logger.info(
                            f"   💰 {mode.upper()}: cash={r['new_cash']:.2f}, "
                            f"total={r.get('broker_total', 0):.2f} {r.get('currency', '')}"
                        )
                    elif r.get("skipped"):
                        logger.debug(f"   ⏭️ {mode.upper()}: {r.get('reason')}")
                    else:
                        logger.warning(f"   ⚠️ {mode.upper()}: {r.get('error')}")
            except Exception as e:
                logger.warning(f"⚠️ Error sincronizando capital desde T212: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Error inicializando Trading212: {e}")
    else:
        logger.info("🏦 Trading212 no configurado (sin API key/secret)")

    # 3. Crear bot de Telegram
    logger.info("🤖 Iniciando bot de Telegram...")
    app = create_bot()

    # 4. Iniciar scheduler
    logger.info("⏰ Configurando scheduler...")
    async with app:
        await app.start()
        await set_bot_commands(app)

        # Pasar el bot al scheduler para notificaciones
        sched = init_scheduler(telegram_bot=app.bot)
        sched.start()

        # 5. Iniciar dashboard web
        web_server = None
        if WEB_ENABLED:
            try:
                import uvicorn
                from web.app import app as web_app

                config = uvicorn.Config(
                    web_app,
                    host=WEB_HOST,
                    port=WEB_PORT,
                    log_level="warning",
                    access_log=False,
                )
                web_server = uvicorn.Server(config)
                asyncio.create_task(web_server.serve())
                logger.info(f"   🌐 Dashboard web: http://{WEB_HOST}:{WEB_PORT}")
            except ImportError:
                logger.warning("⚠️ uvicorn/fastapi no instalados — dashboard web desactivado")
            except Exception as e:
                logger.warning(f"⚠️ Error iniciando dashboard web: {e}")

        logger.info("=" * 60)
        logger.info("✅ TradAI operativo — esperando comandos e instrucciones")
        logger.info("   📱 Telegram: bot activo")
        logger.info(f"   ⏰ Scheduler: {len(sched.get_jobs())} tareas programadas")
        logger.info(f"   📊 Monitorización: cada 10 min en horario de mercado")
        if WEB_ENABLED and web_server:
            logger.info(f"   🌐 Dashboard: http://localhost:{WEB_PORT}")
        logger.info("=" * 60)

        # Notificar por Telegram que el bot ha arrancado
        from config.settings import TELEGRAM_CHAT_ID
        if TELEGRAM_CHAT_ID:
            try:
                await app.bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=(
                        "🚀 *TradAI iniciado correctamente*\n\n"
                        "📊 Cartera real y backtest listas\n"
                        "⏰ Monitorización activa cada 10 min\n"
                        "📱 Usa /help para ver los comandos"
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass

        # Iniciar polling del bot
        await app.updater.start_polling(drop_pending_updates=True)

        # Mantener vivo hasta Ctrl+C
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            logger.info("🛑 Señal de parada recibida...")
        finally:
            sched.shutdown(wait=False)
            await app.updater.stop()
            await app.stop()
            # Cerrar broker
            from broker.trading212 import shutdown_trading212
            await shutdown_trading212()
            await close_db()
            logger.info("👋 TradAI detenido correctamente")


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
