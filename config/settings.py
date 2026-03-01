"""
Configuración central de TradAI.
Carga variables de entorno y expone constantes globales.
"""

import json
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path
from dotenv import load_dotenv

# ── Cargar .env ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")

# ── Telegram ─────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
_raw_allowed_users = os.getenv("TELEGRAM_ALLOWED_USERS", "")
TELEGRAM_ALLOWED_USERS_INVALID: list[str] = []
TELEGRAM_ALLOWED_USERS: list[int] = []
for uid in _raw_allowed_users.split(","):
    uid = uid.strip()
    if not uid:
        continue
    try:
        TELEGRAM_ALLOWED_USERS.append(int(uid))
    except ValueError:
        TELEGRAM_ALLOWED_USERS_INVALID.append(uid)

# ── Base de datos ────────────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://tradai:tradai_password@localhost:5432/tradai_db",
)

# ── OpenAI ───────────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
AI_AGENTS_JSON: str = os.getenv("AI_AGENTS_JSON", "")

# ── Configuración general ───────────────────────────────────
MONITOR_INTERVAL_MINUTES: int = _get_int("MONITOR_INTERVAL_MINUTES", 10)
TIMEZONE: str = os.getenv("TIMEZONE", "Europe/Madrid")
try:
    ZoneInfo(TIMEZONE)
except ZoneInfoNotFoundError:
    TIMEZONE = "UTC"

# Límite de concurrencia para llamadas a yfinance (threads)
YFINANCE_MAX_CONCURRENCY: int = _get_int("YFINANCE_MAX_CONCURRENCY", 8)

# ── Gestión de Riesgos ──────────────────────────────────────
MAX_TICKER_CONCENTRATION: float = _get_float("MAX_TICKER_CONCENTRATION", 0.05)
MAX_SECTOR_CONCENTRATION: float = _get_float("MAX_SECTOR_CONCENTRATION", 0.20)
DEFAULT_STOP_LOSS_PCT: float = _get_float("DEFAULT_STOP_LOSS_PCT", 0.08)
DEFAULT_TAKE_PROFIT_PCT: float = _get_float("DEFAULT_TAKE_PROFIT_PCT", 0.25)

# ── Umbrales de Estrategia ───────────────────────────────────
SIGNAL_BUY_THRESHOLD: float = _get_float("SIGNAL_BUY_THRESHOLD", 70.0)
SIGNAL_SELL_THRESHOLD: float = _get_float("SIGNAL_SELL_THRESHOLD", 30.0)
SCAN_MIN_SCORE: float = _get_float("SCAN_MIN_SCORE", 65.0)

# ── Divisa de la cuenta ──────────────────────────────────────
# Moneda base de la cuenta del broker (EUR para cuentas europeas T212).
# Los totales de cartera se muestran en esta divisa.
# Se auto-detecta del broker si no se establece manualmente.
ACCOUNT_CURRENCY: str = os.getenv("ACCOUNT_CURRENCY", "EUR")

# ── Web Dashboard ────────────────────────────────────────────
WEB_ENABLED: bool = _get_bool("WEB_ENABLED", True)
WEB_PORT: int = _get_int("WEB_PORT", 8080)
WEB_HOST: str = os.getenv("WEB_HOST", "0.0.0.0")
WEB_DOMAIN: str = os.getenv("WEB_DOMAIN", "")  # ej: "123.45.67.89" o "mi-vps.com"
# ── Trading212 Broker ────────────────────────────────────────
# Credenciales principales (aplican al modo por defecto TRADING212_MODE)
TRADING212_API_KEY: str = os.getenv("TRADING212_API_KEY", "")
TRADING212_API_SECRET: str = os.getenv("TRADING212_API_SECRET", "")
TRADING212_MODE: str = os.getenv("TRADING212_MODE", "demo")  # "demo" o "live"
# Credenciales separadas por modo (demo y live tienen cuentas diferentes en T212)
TRADING212_DEMO_API_KEY: str = os.getenv("TRADING212_DEMO_API_KEY", "")
TRADING212_DEMO_API_SECRET: str = os.getenv("TRADING212_DEMO_API_SECRET", "")
TRADING212_LIVE_API_KEY: str = os.getenv("TRADING212_LIVE_API_KEY", "")
TRADING212_LIVE_API_SECRET: str = os.getenv("TRADING212_LIVE_API_SECRET", "")
TRADING212_AUTO_EXECUTE: bool = _get_bool("TRADING212_AUTO_EXECUTE", True)
TRADING212_REQUIRE_EXECUTION: bool = _get_bool(
    "TRADING212_REQUIRE_EXECUTION", True
)
TRADING212_ANALYSIS_ORIENTED: bool = _get_bool(
    "TRADING212_ANALYSIS_ORIENTED", True
)


def get_trading212_credentials() -> dict[str, tuple[str, str]]:
    """
    Devuelve las credenciales T212 disponibles por modo.
    Retorno: {"demo": (key, secret), "live": (key, secret), ...}

    Lógica de resolución:
      1. TRADING212_DEMO_API_KEY / SECRET  →  modo demo
      2. TRADING212_LIVE_API_KEY / SECRET  →  modo live
      3. TRADING212_API_KEY / SECRET       →  modo TRADING212_MODE (fallback)
    """
    creds: dict[str, tuple[str, str]] = {}

    # Credenciales específicas por modo
    if TRADING212_DEMO_API_KEY and TRADING212_DEMO_API_SECRET:
        creds["demo"] = (TRADING212_DEMO_API_KEY, TRADING212_DEMO_API_SECRET)
    if TRADING212_LIVE_API_KEY and TRADING212_LIVE_API_SECRET:
        creds["live"] = (TRADING212_LIVE_API_KEY, TRADING212_LIVE_API_SECRET)

    # Fallback: credenciales genéricas → modo por defecto
    if TRADING212_API_KEY and TRADING212_API_SECRET:
        mode = TRADING212_MODE.lower()
        if mode not in creds:  # no pisar si ya hay específicas
            creds[mode] = (TRADING212_API_KEY, TRADING212_API_SECRET)

    return creds

# ── Backtesting continuo en demo ──────────────────────────────
BACKTEST_CONTINUOUS_ENABLED: bool = _get_bool("BACKTEST_CONTINUOUS_ENABLED", True)
BACKTEST_INTERVAL_MINUTES: int = _get_int("BACKTEST_INTERVAL_MINUTES", 60)
BACKTEST_PERIODS: str = os.getenv("BACKTEST_PERIODS", "6mo,1y")
BACKTEST_MAX_TICKERS: int = _get_int("BACKTEST_MAX_TICKERS", 20)
BACKTEST_NOTIFY_EACH_RUN: bool = _get_bool("BACKTEST_NOTIFY_EACH_RUN", False)

# ── Logging ──────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR: Path = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


def validate_settings() -> list[str]:
    """Devuelve warnings de configuración (no lanza excepciones)."""
    warnings: list[str] = []

    if not TELEGRAM_BOT_TOKEN:
        warnings.append("TELEGRAM_BOT_TOKEN vacío: el bot no podrá arrancar.")
    if not TELEGRAM_CHAT_ID:
        warnings.append(
            "TELEGRAM_CHAT_ID vacío: no se enviarán notificaciones automáticas."
        )
    if not TELEGRAM_ALLOWED_USERS:
        warnings.append(
            "TELEGRAM_ALLOWED_USERS vacío: cualquiera podrá usar el bot (riesgo)."
        )
    if TELEGRAM_ALLOWED_USERS_INVALID:
        warnings.append(
            "TELEGRAM_ALLOWED_USERS contiene valores no numéricos (ignorados): "
            + ", ".join(TELEGRAM_ALLOWED_USERS_INVALID)
        )
    if not OPENAI_API_KEY:
        warnings.append(
            "OPENAI_API_KEY vacío: análisis IA desactivado (solo análisis cuantitativo)."
        )
    if AI_AGENTS_JSON.strip():
        try:
            parsed_agents = json.loads(AI_AGENTS_JSON)
            if not isinstance(parsed_agents, list):
                warnings.append("AI_AGENTS_JSON debe ser un array JSON de agentes.")
        except json.JSONDecodeError:
            warnings.append("AI_AGENTS_JSON no es JSON válido.")
    if TRADING212_API_KEY and TRADING212_MODE not in ("demo", "live"):
        warnings.append(
            f"TRADING212_MODE='{TRADING212_MODE}' inválido. Usa 'demo' o 'live'."
        )
    t212_creds = get_trading212_credentials()
    if TRADING212_AUTO_EXECUTE and not t212_creds:
        warnings.append(
            "TRADING212_AUTO_EXECUTE activo pero no hay credenciales T212 configuradas."
        )
    if TRADING212_REQUIRE_EXECUTION and not TRADING212_AUTO_EXECUTE:
        warnings.append(
            "TRADING212_REQUIRE_EXECUTION activo pero TRADING212_AUTO_EXECUTE=false."
        )
    if TRADING212_API_KEY and not TRADING212_API_SECRET:
        warnings.append(
            "TRADING212_API_KEY configurada pero falta TRADING212_API_SECRET."
        )
    if TRADING212_AUTO_EXECUTE and "live" in t212_creds:
        warnings.append(
            "⚠️ TRADING212 LIVE configurado con auto-ejecución: operaciones con dinero REAL."
        )
    if len(t212_creds) == 2:
        warnings.append(
            "🏦 Trading212 dual mode: demo + live configurados."
        )
    if BACKTEST_INTERVAL_MINUTES < 5:
        warnings.append(
            "BACKTEST_INTERVAL_MINUTES demasiado bajo (<5). Recomendado >= 5."
        )
    if BACKTEST_MAX_TICKERS < 1:
        warnings.append("BACKTEST_MAX_TICKERS debe ser >= 1.")

    return warnings
