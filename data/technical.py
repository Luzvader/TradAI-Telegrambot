"""
Indicadores técnicos — RSI, MACD, Bandas de Bollinger, ATR.
Todos los cálculos usan pandas y datos de yfinance.
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class TechnicalIndicators:
    """Resultado de los indicadores técnicos de un ticker."""
    ticker: str

    # RSI (14 períodos)
    rsi: float | None = None

    # MACD
    macd_line: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None

    # Bandas de Bollinger (20 períodos, 2 desviaciones)
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    bb_position: float | None = None  # 0-1, posición dentro de las bandas

    # ATR (14 períodos)
    atr: float | None = None
    atr_pct: float | None = None  # ATR como % del precio

    # Medias móviles
    sma_50: float | None = None
    sma_200: float | None = None
    ema_12: float | None = None
    ema_26: float | None = None

    # Señales derivadas
    golden_cross: bool = False   # SMA50 cruza sobre SMA200
    death_cross: bool = False    # SMA50 cruza bajo SMA200
    macd_bullish: bool = False   # MACD cruza sobre signal
    rsi_overbought: bool = False  # RSI > 70
    rsi_oversold: bool = False    # RSI < 30

    @property
    def trend_signal(self) -> str:
        """Señal combinada de tendencia: BULLISH / BEARISH / NEUTRAL."""
        bullish = 0
        bearish = 0

        if self.rsi is not None:
            if self.rsi > 70:
                bearish += 1  # Sobrecompra
            elif self.rsi < 30:
                bullish += 1  # Sobreventa (oportunidad)
            elif self.rsi > 50:
                bullish += 0.5
            else:
                bearish += 0.5

        if self.macd_bullish:
            bullish += 1
        elif self.macd_histogram is not None and self.macd_histogram < 0:
            bearish += 1

        if self.golden_cross:
            bullish += 1
        elif self.death_cross:
            bearish += 1

        if bullish > bearish + 0.5:
            return "BULLISH"
        elif bearish > bullish + 0.5:
            return "BEARISH"
        return "NEUTRAL"


def calculate_rsi(close: pd.Series, period: int = 14) -> float | None:
    """Calcula el RSI (Relative Strength Index)."""
    if len(close) < period + 1:
        return None

    delta = close.diff()
    gains = delta.where(delta > 0, 0.0)
    losses = (-delta).where(delta < 0, 0.0)

    avg_gain = gains.rolling(window=period, min_periods=period).mean()
    avg_loss = losses.rolling(window=period, min_periods=period).mean()

    # Usar EMA suavizado después del primer cálculo
    for i in range(period, len(close)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gains.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + losses.iloc[i]) / period

    last_gain = avg_gain.iloc[-1]
    last_loss = avg_loss.iloc[-1]

    if last_loss == 0:
        return 100.0
    rs = last_gain / last_loss
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi), 2)


def calculate_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[float | None, float | None, float | None]:
    """Calcula MACD line, signal line, histogram."""
    if len(close) < slow + signal:
        return None, None, None

    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    return (
        round(float(macd_line.iloc[-1]), 4),
        round(float(signal_line.iloc[-1]), 4),
        round(float(histogram.iloc[-1]), 4),
    )


def calculate_bollinger_bands(
    close: pd.Series, period: int = 20, std_dev: float = 2.0
) -> tuple[float | None, float | None, float | None, float | None]:
    """Calcula Bandas de Bollinger. Devuelve (upper, middle, lower, position 0-1)."""
    if len(close) < period:
        return None, None, None, None

    middle = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()

    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)

    last_upper = float(upper.iloc[-1])
    last_middle = float(middle.iloc[-1])
    last_lower = float(lower.iloc[-1])
    last_price = float(close.iloc[-1])

    band_range = last_upper - last_lower
    position = (last_price - last_lower) / band_range if band_range > 0 else 0.5

    return (
        round(last_upper, 4),
        round(last_middle, 4),
        round(last_lower, 4),
        round(position, 4),
    )


def calculate_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> float | None:
    """Calcula el ATR (Average True Range)."""
    if len(close) < period + 1:
        return None

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean()

    return round(float(atr.iloc[-1]), 4)


def analyze_technical(ticker: str, df: pd.DataFrame) -> TechnicalIndicators:
    """
    Calcula todos los indicadores técnicos para un ticker
    a partir de un DataFrame OHLCV de yfinance.
    """
    result = TechnicalIndicators(ticker=ticker)

    if df is None or df.empty or len(df) < 30:
        return result

    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    # RSI
    result.rsi = calculate_rsi(close)
    if result.rsi is not None:
        result.rsi_overbought = result.rsi > 70
        result.rsi_oversold = result.rsi < 30

    # MACD
    macd_l, macd_s, macd_h = calculate_macd(close)
    result.macd_line = macd_l
    result.macd_signal = macd_s
    result.macd_histogram = macd_h
    if macd_l is not None and macd_s is not None:
        result.macd_bullish = macd_l > macd_s

    # Bollinger Bands
    bb_u, bb_m, bb_l, bb_p = calculate_bollinger_bands(close)
    result.bb_upper = bb_u
    result.bb_middle = bb_m
    result.bb_lower = bb_l
    result.bb_position = bb_p

    # ATR
    result.atr = calculate_atr(high, low, close)
    if result.atr is not None and close.iloc[-1] > 0:
        result.atr_pct = round(result.atr / close.iloc[-1] * 100, 2)

    # Medias móviles
    if len(close) >= 12:
        result.ema_12 = round(float(close.ewm(span=12, adjust=False).mean().iloc[-1]), 4)
    if len(close) >= 26:
        result.ema_26 = round(float(close.ewm(span=26, adjust=False).mean().iloc[-1]), 4)
    if len(close) >= 50:
        result.sma_50 = round(float(close.rolling(50).mean().iloc[-1]), 4)
    if len(close) >= 200:
        result.sma_200 = round(float(close.rolling(200).mean().iloc[-1]), 4)

    # Golden / Death cross
    if result.sma_50 is not None and result.sma_200 is not None:
        result.golden_cross = result.sma_50 > result.sma_200
        result.death_cross = result.sma_50 < result.sma_200

    return result


async def get_technical_analysis(ticker: str, market: str | None = None) -> TechnicalIndicators:
    """Obtiene el análisis técnico completo de un ticker (async)."""
    from data.market_data import get_historical_data

    df = await get_historical_data(ticker, period="1y", interval="1d", market=market)
    return analyze_technical(ticker, df)
