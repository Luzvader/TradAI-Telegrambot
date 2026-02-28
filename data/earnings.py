"""
Monitorización de resultados trimestrales (earnings).
Consulta las fechas de earnings y compara resultados con expectativas.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

import yfinance as yf

from config.markets import (
    DEFAULT_TICKER_MARKET,
    get_yfinance_ticker,
    normalize_ticker,
    split_yfinance_suffix,
)
from config.settings import YFINANCE_MAX_CONCURRENCY
from database import repository as repo

logger = logging.getLogger(__name__)


def _to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime()
        except Exception:
            return None
    return None


def _normalize_ticker_and_market(
    ticker: str, market: str | None = None
) -> tuple[str, str | None]:
    raw = (ticker or "").strip().upper().replace("$", "")
    base, inferred_market = split_yfinance_suffix(raw)
    norm = normalize_ticker(base)
    mk = (market or inferred_market or DEFAULT_TICKER_MARKET.get(norm))
    return norm, (mk.upper() if mk else None)


def _sync_get_next_earnings(
    ticker: str, market: str | None = None
) -> dict[str, Any] | None:
    """Obtiene la próxima fecha de earnings de un ticker (sync)."""
    norm_ticker, mk = _normalize_ticker_and_market(ticker, market)
    yf_ticker = get_yfinance_ticker(norm_ticker, mk)
    stock = yf.Ticker(yf_ticker)
    cal = stock.calendar

    # Verificar que calendar tiene datos válidos
    has_data = False
    if cal is not None:
        if hasattr(cal, "empty"):
            has_data = not cal.empty
        elif isinstance(cal, dict):
            has_data = bool(cal)
        else:
            has_data = bool(cal)

    if not has_data:
        return None

    earnings_date = None
    if isinstance(cal, dict):
        earnings_date = cal.get("Earnings Date")
        if isinstance(earnings_date, list) and len(earnings_date) > 0:
            earnings_date = earnings_date[0]
    elif hasattr(cal, "loc"):
        try:
            row = cal.loc["Earnings Date"]
            if hasattr(row, "iloc"):
                earnings_date = row.iloc[0]
            else:
                earnings_date = row
        except (KeyError, IndexError):
            earnings_date = None

    earnings_dt = _to_datetime(earnings_date)
    if earnings_dt is None:
        return None

    days_until = (earnings_dt.date() - datetime.now().date()).days
    if days_until < 0:
        return None

    return {
        "ticker": norm_ticker.upper(),
        "market": mk,
        "earnings_date": earnings_dt,
        "days_until": days_until,
    }


async def check_upcoming_earnings(
    tickers: list[str] | list[tuple[str, str | None]]
) -> list[dict[str, Any]]:
    """Comprueba las próximas fechas de earnings para los tickers dados.

    Acepta:
      - ["AAPL", "SAN.MC"]
      - [("AAPL", "NASDAQ"), ("SAN", "IBEX")]
    """
    sem = asyncio.Semaphore(max(1, int(YFINANCE_MAX_CONCURRENCY)))

    normalized: list[tuple[str, str | None]] = []
    for item in tickers:
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            t, m = str(item[0]), (str(item[1]) if item[1] is not None else None)
        else:
            t, m = str(item), None
        nt, nm = _normalize_ticker_and_market(t, m)
        normalized.append((nt, nm))

    # Deduplicar entradas
    seen: set[tuple[str, str | None]] = set()
    normalized_unique = []
    for t, m in normalized:
        key = (t.upper(), m.upper() if m else None)
        if key in seen:
            continue
        seen.add(key)
        normalized_unique.append((t, m))

    async def _one(ticker: str, market: str | None) -> dict[str, Any] | None:
        async with sem:
            return await asyncio.to_thread(_sync_get_next_earnings, ticker, market)

    tasks = [_one(t, m) for t, m in normalized_unique]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    upcoming: list[dict[str, Any]] = []
    for (ticker, _market), result in zip(normalized_unique, results):
        if isinstance(result, Exception):
            logger.warning(f"No se pudieron obtener earnings de {ticker}: {result}")
            continue
        if result is not None:
            upcoming.append(result)

    return sorted(upcoming, key=lambda x: x.get("days_until", 999))


async def fetch_earnings_history(
    ticker: str, market: str | None = None
) -> list[dict[str, Any]]:
    """Obtiene el historial de earnings de un ticker."""
    def _sync_fetch() -> list[dict[str, Any]]:
        norm_ticker, mk = _normalize_ticker_and_market(ticker, market)
        yf_ticker = get_yfinance_ticker(norm_ticker, mk)
        stock = yf.Ticker(yf_ticker)
        earnings = stock.earnings_history
        if earnings is None or (hasattr(earnings, "empty") and earnings.empty):
            return []

        results: list[dict[str, Any]] = []
        for _, row in earnings.iterrows():
            results.append({
                "ticker": norm_ticker.upper(),
                "market": mk,
                "date": row.get("Earnings Date"),
                "eps_estimate": row.get("EPS Estimate"),
                "eps_actual": row.get("Reported EPS"),
                "surprise_pct": row.get("Surprise(%)"),
            })
        return results

    try:
        return await asyncio.to_thread(_sync_fetch)
    except Exception as e:
        logger.warning(f"Error obteniendo historial de earnings de {ticker}: {e}")
        return []


async def analyze_earnings_impact(
    ticker: str, actual_eps: float, expected_eps: float
) -> dict[str, Any]:
    """Analiza el impacto de un reporte de earnings."""
    surprise_pct = 0.0
    if expected_eps != 0:
        surprise_pct = round((actual_eps - expected_eps) / abs(expected_eps) * 100, 2)

    impact = "neutral"
    if surprise_pct > 10:
        impact = "very_positive"
    elif surprise_pct > 3:
        impact = "positive"
    elif surprise_pct < -10:
        impact = "very_negative"
    elif surprise_pct < -3:
        impact = "negative"

    # Guardar en DB
    await repo.save_earnings_event(
        ticker=ticker,
        expected_eps=expected_eps,
        actual_eps=actual_eps,
        surprise_pct=surprise_pct,
    )

    return {
        "ticker": ticker.upper(),
        "expected_eps": expected_eps,
        "actual_eps": actual_eps,
        "surprise_pct": surprise_pct,
        "impact": impact,
    }
