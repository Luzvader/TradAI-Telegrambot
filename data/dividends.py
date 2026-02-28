"""
Servicio de detección y registro de dividendos.

Consulta yfinance para obtener el calendario de dividendos de las
posiciones abiertas y registra pagos cuando se detecta una fecha ex-dividend
en el pasado reciente.
"""

import asyncio
import logging
from datetime import datetime, timedelta, UTC
from typing import Any

import yfinance as yf

from config.markets import get_yfinance_ticker
from database import repository as repo

logger = logging.getLogger(__name__)


async def check_and_record_dividends(portfolio_id: int) -> list[dict[str, Any]]:
    """
    Revisa todas las posiciones abiertas de un portfolio:
    1. Consulta el historial de dividendos recientes de yfinance.
    2. Si hay un dividendo cuya ex-date fue en los últimos 30 días,
       lo registra si no está ya guardado.

    Returns:
        Lista de dividendos recién registrados.
    """
    positions = list(await repo.get_open_positions(portfolio_id))
    recorded: list[dict[str, Any]] = []

    for pos in positions:
        try:
            divs = await _get_recent_dividends(pos.ticker, pos.market)
            if not divs:
                continue

            # Comprobar cuáles ya están registrados
            existing = await repo.get_dividends_for_portfolio(
                portfolio_id, since_days=90,
            )
            existing_keys = {
                (d.ticker, d.ex_date.date() if d.ex_date else None)
                for d in existing
            }

            for div_info in divs:
                ex_date = div_info["ex_date"]
                key = (pos.ticker.upper(), ex_date.date() if ex_date else None)
                if key in existing_keys:
                    continue

                dp = await repo.save_dividend_payment(
                    portfolio_id=portfolio_id,
                    ticker=pos.ticker,
                    market=pos.market or "NASDAQ",
                    amount_per_share=div_info["amount"],
                    shares_held=pos.shares,
                    currency=div_info.get("currency", "USD"),
                    ex_date=ex_date,
                    pay_date=div_info.get("pay_date"),
                )
                recorded.append({
                    "ticker": pos.ticker,
                    "amount_per_share": div_info["amount"],
                    "shares": pos.shares,
                    "total": dp.total_amount,
                    "ex_date": str(ex_date.date()) if ex_date else "N/A",
                })
                logger.info(
                    f"Dividendo registrado: {pos.ticker} "
                    f"${div_info['amount']:.4f}/acc × {pos.shares} = ${dp.total_amount:.2f}"
                )
        except Exception as e:
            logger.warning(f"Error comprobando dividendos de {pos.ticker}: {e}")

    return recorded


async def get_dividend_summary(portfolio_id: int) -> dict[str, Any]:
    """
    Resumen de dividendos cobrados por el portfolio.
    """
    all_divs = await repo.get_dividends_for_portfolio(portfolio_id)
    total = await repo.get_total_dividends(portfolio_id)

    # Agrupar por ticker
    by_ticker: dict[str, float] = {}
    for d in all_divs:
        by_ticker[d.ticker] = by_ticker.get(d.ticker, 0.0) + d.total_amount

    # Últimos 12 meses
    recent = await repo.get_dividends_for_portfolio(portfolio_id, since_days=365)
    total_12m = sum(d.total_amount for d in recent)

    return {
        "total_all_time": round(total, 2),
        "total_12m": round(total_12m, 2),
        "count": len(all_divs),
        "by_ticker": {k: round(v, 2) for k, v in sorted(by_ticker.items(), key=lambda x: -x[1])},
        "recent": [
            {
                "ticker": d.ticker,
                "amount": d.total_amount,
                "date": str(d.ex_date.date()) if d.ex_date else "N/A",
            }
            for d in list(recent)[:10]
        ],
    }


async def _get_recent_dividends(
    ticker: str,
    market: str | None = None,
    lookback_days: int = 30,
) -> list[dict[str, Any]]:
    """
    Obtiene dividendos pagados en los últimos N días vía yfinance.
    """
    def _sync():
        yf_ticker = get_yfinance_ticker(ticker, market)
        stock = yf.Ticker(yf_ticker)

        # yfinance expone dividends como un pandas Series indexado por fecha
        divs = stock.dividends
        if divs is None or divs.empty:
            return []

        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        recent = []
        for date, amount in divs.items():
            div_date = date.to_pydatetime()
            if div_date.tzinfo is None:
                div_date = div_date.replace(tzinfo=UTC)
            if div_date >= cutoff and amount > 0:
                recent.append({
                    "ex_date": div_date,
                    "amount": float(amount),
                    "currency": stock.info.get("currency", "USD") if hasattr(stock, "info") else "USD",
                })
        return recent

    return await asyncio.to_thread(_sync)


async def get_upcoming_dividend_info(ticker: str, market: str | None = None) -> dict[str, Any] | None:
    """
    Obtiene información sobre el próximo dividendo de un ticker.
    """
    def _sync():
        yf_ticker = get_yfinance_ticker(ticker, market)
        stock = yf.Ticker(yf_ticker)
        info = stock.info
        if not info:
            return None

        div_yield = info.get("dividendYield")
        div_rate = info.get("dividendRate")
        ex_date = info.get("exDividendDate")

        if div_rate is None and div_yield is None:
            return None

        result = {
            "ticker": ticker.upper(),
            "dividend_yield": div_yield,
            "dividend_rate": div_rate,
            "payout_ratio": info.get("payoutRatio"),
        }

        if ex_date:
            from datetime import datetime
            result["ex_dividend_date"] = datetime.fromtimestamp(ex_date, tz=UTC).isoformat()

        return result

    return await asyncio.to_thread(_sync)
