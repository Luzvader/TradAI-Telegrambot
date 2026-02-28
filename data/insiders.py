"""
Análisis de operaciones de insiders (directivos y consejeros).

Usa yfinance para obtener las transacciones de insiders y detectar
patrones de compra/venta relevantes que podrían ser señales adicionales.
"""

import asyncio
import logging
from datetime import datetime, timedelta, UTC
from typing import Any

import yfinance as yf

from config.markets import get_yfinance_ticker

logger = logging.getLogger(__name__)


async def get_insider_activity(
    ticker: str,
    market: str | None = None,
    lookback_days: int = 90,
) -> dict[str, Any]:
    """
    Obtiene y analiza la actividad de insiders para un ticker.

    Returns:
        {
            "ticker": str,
            "transactions": [...],
            "summary": {
                "total_buys": int,
                "total_sells": int,
                "net_shares": int,
                "insider_sentiment": str,
            },
            "notable": [...],
        }
    """
    def _sync():
        yf_ticker = get_yfinance_ticker(ticker, market)
        stock = yf.Ticker(yf_ticker)

        # yfinance >= 0.2.x usa insider_transactions
        transactions = []
        try:
            insider_df = stock.insider_transactions
            if insider_df is not None and not insider_df.empty:
                for _, row in insider_df.iterrows():
                    transactions.append({
                        "name": str(row.get("Insider Trading", row.get("insiderName", "N/A"))),
                        "relation": str(row.get("Relationship", row.get("relation", "N/A"))),
                        "date": str(row.get("Start Date", row.get("startDate", "N/A"))),
                        "type": str(row.get("Transaction", row.get("transactionText", "N/A"))),
                        "shares": int(row.get("Shares", row.get("shares", 0)) or 0),
                        "value": float(row.get("Value", row.get("value", 0)) or 0),
                    })
        except Exception as e:
            logger.debug(f"insider_transactions no disponible para {ticker}: {e}")

        # Fallback: insider_purchases
        if not transactions:
            try:
                purchases_df = stock.insider_purchases
                if purchases_df is not None and not purchases_df.empty:
                    for _, row in purchases_df.iterrows():
                        transactions.append({
                            "name": "Agregado",
                            "relation": str(row.get("Insider Purchases Last 6m", "N/A")),
                            "date": "N/A",
                            "type": "Purchase",
                            "shares": int(row.get("Shares", 0) or 0),
                            "value": 0,
                        })
            except Exception:
                pass

        return transactions

    transactions = await asyncio.to_thread(_sync)

    # Analizar
    total_buys = 0
    total_sells = 0
    net_shares = 0
    notable = []

    for t in transactions:
        tx_type = t.get("type", "").lower()
        shares = t.get("shares", 0)

        if any(w in tx_type for w in ["purchase", "buy", "acquisition", "award"]):
            total_buys += 1
            net_shares += shares
        elif any(w in tx_type for w in ["sale", "sell", "disposition"]):
            total_sells += 1
            net_shares -= shares

        # Transacciones notables (> $100k)
        if t.get("value", 0) > 100_000:
            notable.append(t)

    # Sentimiento
    if total_buys > total_sells * 2:
        sentiment = "MUY_ALCISTA"
    elif total_buys > total_sells:
        sentiment = "ALCISTA"
    elif total_sells > total_buys * 2:
        sentiment = "MUY_BAJISTA"
    elif total_sells > total_buys:
        sentiment = "BAJISTA"
    else:
        sentiment = "NEUTRAL"

    return {
        "ticker": ticker.upper(),
        "transactions": transactions[:20],  # Limitar
        "summary": {
            "total_buys": total_buys,
            "total_sells": total_sells,
            "net_shares": net_shares,
            "insider_sentiment": sentiment,
        },
        "notable": notable[:5],
    }


def format_insider_report(data: dict[str, Any]) -> str:
    """Formatea el informe de insiders para Telegram."""
    summary = data.get("summary", {})
    lines = [
        f"👔 *ACTIVIDAD DE INSIDERS — {data['ticker']}*\n",
    ]

    sentiment_emoji = {
        "MUY_ALCISTA": "🟢🟢",
        "ALCISTA": "🟢",
        "NEUTRAL": "⚪",
        "BAJISTA": "🔴",
        "MUY_BAJISTA": "🔴🔴",
    }

    lines.append(
        f"Sentimiento: {sentiment_emoji.get(summary.get('insider_sentiment', 'NEUTRAL'), '⚪')} "
        f"*{summary.get('insider_sentiment', 'N/A')}*"
    )
    lines.append(
        f"Compras: {summary.get('total_buys', 0)} | "
        f"Ventas: {summary.get('total_sells', 0)} | "
        f"Neto: {summary.get('net_shares', 0):+,} acciones\n"
    )

    # Transacciones recientes
    transactions = data.get("transactions", [])
    if transactions:
        lines.append("*Últimas transacciones:*")
        for t in transactions[:8]:
            tx_emoji = "🟢" if "purchase" in t.get("type", "").lower() or "buy" in t.get("type", "").lower() else "🔴"
            value_str = f" (${t['value']:,.0f})" if t.get("value", 0) > 0 else ""
            lines.append(
                f"  {tx_emoji} {t['name'][:25]} — {t['type']} "
                f"{t['shares']:,} acc{value_str}"
            )
    else:
        lines.append("_No se encontraron transacciones de insiders._")

    # Notables
    notable = data.get("notable", [])
    if notable:
        lines.append("\n⭐ *Transacciones > $100k:*")
        for n in notable:
            lines.append(
                f"  • {n['name'][:25]}: {n['type']} ${n['value']:,.0f}"
            )

    return "\n".join(lines)
