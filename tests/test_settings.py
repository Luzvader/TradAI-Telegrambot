"""
Tests para config/settings.py — verificar carga de configuración.
"""

import os


def test_settings_import():
    """Asegurar que settings se importa sin errores."""
    from config import settings
    assert hasattr(settings, "TELEGRAM_BOT_TOKEN")
    assert hasattr(settings, "DATABASE_URL")
    assert hasattr(settings, "OPENAI_MODEL")


def test_signal_thresholds():
    from config.settings import SIGNAL_BUY_THRESHOLD, SIGNAL_SELL_THRESHOLD
    assert 0 <= SIGNAL_SELL_THRESHOLD < SIGNAL_BUY_THRESHOLD <= 100


def test_scan_min_score():
    from config.settings import SCAN_MIN_SCORE
    assert 0 <= SCAN_MIN_SCORE <= 100


def test_web_config():
    from config.settings import WEB_ENABLED, WEB_PORT
    assert isinstance(WEB_ENABLED, bool)
    assert isinstance(WEB_PORT, int)
    assert WEB_PORT > 0


def test_get_int_helper():
    from config.settings import _get_int
    assert _get_int("NONEXISTENT_VAR_12345", 42) == 42


def test_get_float_helper():
    from config.settings import _get_float
    assert _get_float("NONEXISTENT_VAR_12345", 3.14) == 3.14


def test_get_bool_helper():
    from config.settings import _get_bool
    assert _get_bool("NONEXISTENT_VAR_12345", True) is True
    assert _get_bool("NONEXISTENT_VAR_12345", False) is False


def test_broker_and_backtest_flags_types():
    from config.settings import (
        BACKTEST_CONTINUOUS_ENABLED,
        BACKTEST_INTERVAL_MINUTES,
        BACKTEST_MAX_TICKERS,
        TRADING212_ANALYSIS_ORIENTED,
        TRADING212_AUTO_EXECUTE,
        TRADING212_REQUIRE_EXECUTION,
    )

    assert isinstance(TRADING212_AUTO_EXECUTE, bool)
    assert isinstance(TRADING212_REQUIRE_EXECUTION, bool)
    assert isinstance(TRADING212_ANALYSIS_ORIENTED, bool)
    assert isinstance(BACKTEST_CONTINUOUS_ENABLED, bool)
    assert isinstance(BACKTEST_INTERVAL_MINUTES, int)
    assert isinstance(BACKTEST_MAX_TICKERS, int)


def test_validate_settings_returns_list():
    from config.settings import validate_settings
    warnings = validate_settings()
    assert isinstance(warnings, list)
