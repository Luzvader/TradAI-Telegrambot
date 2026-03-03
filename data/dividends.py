"""
Servicio de detección y registro de dividendos.

Fuente primaria: eToro API (dividendos realmente cobrados, datos exactos).
Fuente secundaria: yfinance (estimaciones, para posiciones no en broker).
"""

import asyncio
import logging
from datetime import datetime, timedelta, UTC
from typing import Any

import yfinance as yf

from config.markets import get_yfinance_ticker, format_price, get_currency_symbol
from config.settings import ACCOUNT_CURRENCY
from database import repository as repo

logger = logging.getLogger(__name__)


async def check_and_record_dividends(portfolio_id: int) -> list[dict[str, Any]]:
    """
    Revisa dividendos usando dos fuentes:
    1. eToro API: dividendos realmente cobrados (datos exactos)
    2. yfinance: fallback para posiciones no en el broker

    Returns:
        Lista de dividendos recién registrados.
    """
    recorded: list[dict[str, Any]] = []

    # ── Fase 1: Dividendos reales desde eToro ──
    try:
        from broker.bridge import get_broker_dividend_history
        etoro_divs = await get_broker_dividend_history(limit=100)
        if etoro_divs:
            existing = await repo.get_dividends_for_portfolio(
                portfolio_id, since_days=365,
            )
            existing_keys = set()
            for d in existing:
                key = (
                    d.ticker.upper() if d.ticker else "",
                    d.ex_date.date() if d.ex_date else None,
                    round(d.total_amount, 2) if d.total_amount else 0,
                )
                existing_keys.add(key)

            for div in etoro_divs:
                ticker = div.get("ticker", "").upper()
                amount = div.get("amount", 0)
                quantity = div.get("quantity", 0)
                paid_on_str = div.get("paid_on", "")

                if not ticker or amount <= 0:
                    continue

                # Parsear fecha
                try:
                    if paid_on_str:
                        pay_date = datetime.fromisoformat(
                            paid_on_str.replace("Z", "+00:00")
                        )
                    else:
                        pay_date = datetime.now(UTC)
                except Exception:
                    pay_date = datetime.now(UTC)

                # Check duplicado
                key = (ticker, pay_date.date(), round(amount, 2))
                if key in existing_keys:
                    continue

                amount_per_share = amount / quantity if quantity > 0 else amount

                dp = await repo.save_dividend_payment(
                    portfolio_id=portfolio_id,
                    ticker=ticker,
                    market="NASDAQ",  # se infiere después si es necesario
                    amount_per_share=amount_per_share,
                    shares_held=quantity,
                    currency=ACCOUNT_CURRENCY,  # eToro paga en USD
                    ex_date=pay_date,
                    pay_date=pay_date,
                )
                existing_keys.add(key)
                recorded.append({
                    "ticker": ticker,
                    "amount_per_share": amount_per_share,
                    "shares": quantity,
                    "total": dp.total_amount,
                    "ex_date": str(pay_date.date()),
                    "source": "eToro",
                })
                logger.info(
                    f"💰 Dividendo eToro: {ticker} "
                    f"{format_price(amount, ACCOUNT_CURRENCY)} ({quantity:.2f} acc)"
                )
    except Exception as e:
        logger.warning(f"Error obteniendo dividendos de eToro: {e}")

    # ── Fase 2: yfinance para posiciones no cubiertas por eToro ──
    positions = list(await repo.get_open_positions(portfolio_id))
    etoro_tickers = {d["ticker"].upper() for d in recorded}

    for pos in positions:
        if pos.ticker.upper() in etoro_tickers:
            continue  # ya registrado desde eToro
        try:
            divs = await _get_recent_dividends(pos.ticker, pos.market)
            if not divs:
                continue

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
                    "source": "yfinance",
                })
                div_ccy = div_info.get("currency", ACCOUNT_CURRENCY)
                logger.info(
                    f"Dividendo registrado (yfinance): {pos.ticker} "
                    f"{format_price(div_info['amount'], div_ccy)}/acc × {pos.shares} = {format_price(dp.total_amount, div_ccy)}"
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
