"""
Análisis de correlación y diversificación del portfolio.

Calcula la matriz de correlación entre posiciones, detecta
concentración sectorial y sugiere mejoras de diversificación.
"""

import asyncio
import logging
from typing import Any

import numpy as np
import pandas as pd

from config.markets import DEFAULT_TICKER_MARKET
from data.market_data import get_historical_data
from database import repository as repo
from database.models import PortfolioType

logger = logging.getLogger(__name__)


async def portfolio_correlation(
    portfolio_id: int | None = None,
    period: str = "6mo",
) -> dict[str, Any]:
    """
    Calcula la matriz de correlación y métricas de diversificación
    para las posiciones abiertas del portfolio.

    Returns:
        {
            "correlation_matrix": dict[str, dict[str, float]],
            "high_correlations": [(ticker1, ticker2, corr)],
            "diversification_score": float (0-100),
            "sector_concentration": dict[str, float],
            "suggestions": [str],
        }
    """
    if portfolio_id is None:
        portfolio = await repo.get_portfolio_by_type(PortfolioType.REAL)
        if portfolio is None:
            return {"error": "No hay cartera inicializada"}
        portfolio_id = portfolio.id

    positions = list(await repo.get_open_positions(portfolio_id))
    if len(positions) < 2:
        return {
            "error": "Se necesitan al menos 2 posiciones para el análisis",
            "positions": len(positions),
        }

    tickers = [p.ticker for p in positions]
    weights = {}
    sectors = {}
    total_value = sum(
        (p.current_price or p.avg_price) * p.shares for p in positions
    )

    for p in positions:
        val = (p.current_price or p.avg_price) * p.shares
        weights[p.ticker] = val / total_value if total_value > 0 else 0
        sectors[p.ticker] = p.sector or "Desconocido"

    # Descargar precios históricos
    price_data = await _fetch_prices(tickers, period)
    if not price_data:
        return {"error": "No se pudieron obtener datos históricos"}

    # Construir DataFrame de retornos
    returns_df = _build_returns_df(price_data)
    if returns_df is None or returns_df.shape[1] < 2:
        return {"error": "Datos insuficientes para calcular correlaciones"}

    # Matriz de correlación
    corr_matrix = returns_df.corr()
    corr_dict = {
        t1: {t2: round(float(corr_matrix.loc[t1, t2]), 3) for t2 in corr_matrix.columns}
        for t1 in corr_matrix.index
    }

    # Pares altamente correlacionados (> 0.7)
    high_corr = []
    seen = set()
    for i, t1 in enumerate(corr_matrix.index):
        for j, t2 in enumerate(corr_matrix.columns):
            if i < j:
                corr_val = float(corr_matrix.iloc[i, j])
                if abs(corr_val) > 0.7:
                    pair = tuple(sorted([t1, t2]))
                    if pair not in seen:
                        seen.add(pair)
                        high_corr.append((t1, t2, round(corr_val, 3)))

    high_corr.sort(key=lambda x: -abs(x[2]))

    # Concentración sectorial
    sector_weights: dict[str, float] = {}
    for ticker, weight in weights.items():
        sector = sectors.get(ticker, "Desconocido")
        sector_weights[sector] = sector_weights.get(sector, 0) + weight
    sector_conc = {k: round(v * 100, 1) for k, v in sorted(sector_weights.items(), key=lambda x: -x[1])}

    # Score de diversificación (0-100)
    div_score = _diversification_score(corr_matrix, weights, sector_weights)

    # Sugerencias
    suggestions = _generate_suggestions(
        high_corr, sector_conc, div_score, len(positions),
    )

    return {
        "correlation_matrix": corr_dict,
        "high_correlations": high_corr,
        "diversification_score": round(div_score, 1),
        "sector_concentration": sector_conc,
        "suggestions": suggestions,
        "tickers": list(corr_matrix.columns),
    }


def format_correlation_report(result: dict[str, Any]) -> str:
    """Formatea el análisis de correlación como texto para Telegram."""
    if "error" in result:
        return f"❌ {result['error']}"

    lines = [
        f"📊 *ANÁLISIS DE DIVERSIFICACIÓN*\n",
        f"🎯 Score diversificación: *{result['diversification_score']}/100*\n",
    ]

    # Concentración sectorial
    if result.get("sector_concentration"):
        lines.append("*Exposición sectorial:*")
        for sector, pct in list(result["sector_concentration"].items())[:6]:
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            lines.append(f"  {bar} {pct:.0f}% {sector}")
        lines.append("")

    # Correlaciones altas
    if result.get("high_correlations"):
        lines.append("⚠️ *Pares altamente correlacionados:*")
        for t1, t2, corr in result["high_correlations"][:5]:
            emoji = "🔴" if abs(corr) > 0.85 else "🟡"
            lines.append(f"  {emoji} {t1} ↔ {t2}: {corr:.2f}")
        lines.append("")

    # Sugerencias
    if result.get("suggestions"):
        lines.append("💡 *Sugerencias:*")
        for s in result["suggestions"]:
            lines.append(f"  • {s}")

    return "\n".join(lines)


# ── Helpers internos ─────────────────────────────────────────


async def _fetch_prices(
    tickers: list[str], period: str
) -> dict[str, pd.DataFrame]:
    """Descarga precios históricos en paralelo."""
    sem = asyncio.Semaphore(5)
    data: dict[str, pd.DataFrame] = {}

    async def _one(ticker: str):
        async with sem:
            market = DEFAULT_TICKER_MARKET.get(ticker)
            df = await get_historical_data(ticker, period=period, market=market)
            if df is not None and not df.empty and len(df) > 5:
                data[ticker] = df

    await asyncio.gather(*[_one(t) for t in tickers])
    return data


def _build_returns_df(price_data: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
    """Construye DataFrame de retornos diarios a partir de precios de cierre."""
    close_series = {}
    for ticker, df in price_data.items():
        close_series[ticker] = df["Close"]

    if not close_series:
        return None

    prices_df = pd.DataFrame(close_series)
    prices_df = prices_df.dropna(axis=0, how="all").ffill()
    returns = prices_df.pct_change().dropna()

    # Eliminar columnas con todos NaN
    returns = returns.dropna(axis=1, how="all")

    if returns.shape[0] < 5 or returns.shape[1] < 2:
        return None

    return returns


def _diversification_score(
    corr_matrix: pd.DataFrame,
    weights: dict[str, float],
    sector_weights: dict[str, float],
) -> float:
    """
    Score de 0-100 donde 100 = perfectamente diversificado.

    Penaliza:
      - Correlaciones altas entre posiciones ponderadas por peso.
      - Concentración sectorial alta.
      - Pocas posiciones.
    """
    tickers = list(corr_matrix.columns)
    n = len(tickers)
    score = 100.0

    # Penalización por correlación (ponderada por peso)
    for i in range(n):
        for j in range(i + 1, n):
            t1, t2 = tickers[i], tickers[j]
            corr = abs(float(corr_matrix.iloc[i, j]))
            w = (weights.get(t1, 0) + weights.get(t2, 0)) / 2
            if corr > 0.5:
                score -= (corr - 0.5) * 40 * w  # Penalización escalada

    # Penalización por concentración sectorial (HHI)
    hhi = sum(w ** 2 for w in sector_weights.values())
    # HHI de 1/n (perfecto) a 1 (todo en un sector)
    ideal_hhi = 1.0 / max(len(sector_weights), 1)
    excess_hhi = max(0, (hhi - ideal_hhi) / (1 - ideal_hhi))
    score -= excess_hhi * 30

    # Bonus por número de posiciones
    if n < 5:
        score -= (5 - n) * 5
    elif n >= 10:
        score += 5

    return max(0, min(100, score))


def _generate_suggestions(
    high_corr: list[tuple],
    sector_conc: dict[str, float],
    div_score: float,
    n_positions: int,
) -> list[str]:
    """Genera sugerencias de mejora de diversificación."""
    suggestions = []

    if n_positions < 5:
        suggestions.append(
            f"Con solo {n_positions} posiciones, considera añadir más activos "
            "para reducir riesgo idiosincrático."
        )

    if high_corr:
        top = high_corr[0]
        suggestions.append(
            f"{top[0]} y {top[1]} tienen correlación de {top[2]:.2f}. "
            "Considera reducir exposición a uno de ellos."
        )

    # Sector dominante
    for sector, pct in sector_conc.items():
        if pct > 40:
            suggestions.append(
                f"Alta concentración en {sector} ({pct:.0f}%). "
                "Busca oportunidades en otros sectores."
            )
            break

    if div_score >= 80:
        suggestions.append("✅ Tu portfolio está bien diversificado.")
    elif div_score < 40:
        suggestions.append(
            "⚠️ Diversificación baja. Considera añadir activos de "
            "sectores y geografías diferentes."
        )

    return suggestions
