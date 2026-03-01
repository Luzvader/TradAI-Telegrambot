"""
Análisis fundamental para estrategia Value.
Obtiene y procesa datos fundamentales de empresas.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FundamentalData:
    """Datos fundamentales procesados de una empresa."""
    ticker: str
    name: str = "N/A"
    sector: str = "N/A"
    industry: str = "N/A"
    market_cap: float | None = None
    currency: str = "USD"
    current_price: float | None = None

    # Ratios de valoración
    pe_ratio: float | None = None
    forward_pe: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None

    # Rentabilidad
    roe: float | None = None
    roa: float | None = None
    profit_margins: float | None = None
    operating_margins: float | None = None

    # Deuda y flujo de caja
    debt_to_equity: float | None = None
    free_cash_flow: float | None = None

    # Crecimiento
    revenue_growth: float | None = None
    earnings_growth: float | None = None

    # Dividendos
    dividend_yield: float | None = None

    # Técnico
    beta: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    avg_50d: float | None = None
    avg_200d: float | None = None

    # Indicadores técnicos avanzados
    rsi: float | None = None
    macd_histogram: float | None = None
    atr: float | None = None
    atr_pct: float | None = None
    bb_position: float | None = None  # 0-1 posición en Bollinger
    trend_signal: str | None = None   # BULLISH / BEARISH / NEUTRAL

    # Consenso
    target_price: float | None = None
    recommendation: str | None = None

    # Scoring
    value_score: float = 0.0
    quality_score: float = 0.0
    safety_score: float = 0.0
    overall_score: float = 0.0

    raw: dict = field(default_factory=dict)


def fetch_fundamentals(ticker: str, market: str | None = None) -> FundamentalData:
    """Obtiene datos fundamentales y los estructura (sync, para uso en threads)."""
    from data.market_data import _sync_get_ticker_info
    info = _sync_get_ticker_info(ticker, market)

    fd = FundamentalData(
        ticker=ticker.upper(),
        name=info.get("name", "N/A"),
        sector=info.get("sector", "N/A"),
        industry=info.get("industry", "N/A"),
        market_cap=info.get("market_cap"),
        currency=info.get("currency", "USD"),
        current_price=info.get("current_price"),
        pe_ratio=info.get("pe_ratio"),
        forward_pe=info.get("forward_pe"),
        pb_ratio=info.get("pb_ratio"),
        ps_ratio=info.get("ps_ratio"),
        roe=info.get("roe"),
        roa=info.get("roa"),
        profit_margins=info.get("profit_margins"),
        operating_margins=info.get("operating_margins"),
        debt_to_equity=info.get("debt_to_equity"),
        free_cash_flow=info.get("free_cash_flow"),
        revenue_growth=info.get("revenue_growth"),
        earnings_growth=info.get("earnings_growth"),
        dividend_yield=info.get("dividend_yield"),
        beta=info.get("beta"),
        high_52w=info.get("52w_high"),
        low_52w=info.get("52w_low"),
        avg_50d=info.get("50d_avg"),
        avg_200d=info.get("200d_avg"),
        target_price=info.get("target_mean_price"),
        recommendation=info.get("recommendation"),
        raw=info,
    )

    return fd


def calculate_margin_of_safety(fd: FundamentalData) -> float | None:
    """Calcula el margen de seguridad basado en el precio objetivo del consenso."""
    if fd.current_price and fd.target_price and fd.target_price > 0:
        return round((fd.target_price - fd.current_price) / fd.target_price * 100, 2)
    return None


def get_sector(ticker: str, market: str | None = None) -> str:
    """Obtiene el sector de un ticker (sync, para uso en threads)."""
    from data.market_data import _sync_get_ticker_info
    info = _sync_get_ticker_info(ticker, market)
    return info.get("sector", "Unknown")
