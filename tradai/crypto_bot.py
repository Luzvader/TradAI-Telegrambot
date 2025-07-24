"""Simple trading bot using technical indicators and scikit-learn."""

from __future__ import annotations

import argparse
import socket
import time
from typing import List, Optional

import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import LogisticRegression


# Top trading pairs supported
TOP_CRYPTOS = [
    "BTCUSDT",
    "ETHUSDT",
    "XRPUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "USDCUSDT",
    "DOGEUSDT",
    "TRXUSDT",
    "ADAUSDT",
    "LTCUSDT",
    "PEPEUSDT",
    "BONKUSDT",
    "KCSUSDT",
]

# Binance API endpoint
BINANCE_URL = "https://api.binance.com/api/v3/klines"

# Bot parameters
INTERVAL = "5m"
UPDATE_INTERVAL = 900  # seconds


def fetch_historical_data(symbol: str, interval: str, max_retries: int = 3, retry_delay: int = 5) -> Optional[pd.DataFrame]:
    """Return historical OHLCV data for *symbol* using Binance."""

    for attempt in range(max_retries):
        try:
            params = {"symbol": symbol, "interval": interval, "limit": 1000}
            response = requests.get(BINANCE_URL, params=params)
            response.raise_for_status()
            data = response.json()
            if not data:
                raise ValueError(f"No data returned for {symbol}")
            df = pd.DataFrame(
                data,
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "close_time",
                    "quote_asset_vol",
                    "num_trades",
                    "taker_buy_base_vol",
                    "taker_buy_quote_vol",
                    "ignore",
                ],
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df[["open", "high", "low", "close", "volume"]] = df[
                ["open", "high", "low", "close", "volume"]
            ].apply(pd.to_numeric)
            return df.sort_values(by="timestamp")
        except socket.gaierror as exc:
            if exc.errno == -3 and attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return None
        except requests.RequestException:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return None


def calculate_ema(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df["ema"] = df["close"].ewm(span=period, adjust=True).mean()
    return df


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df["delta"] = df["close"].diff()
    df["gain"] = df["delta"].where(df["delta"] > 0, 0)
    df["loss"] = -df["delta"].where(df["delta"] < 0, 0)
    if len(df) > period:
        initial_avg_gain = df["gain"].iloc[1 : period + 1].mean()
        initial_avg_loss = df["loss"].iloc[1 : period + 1].mean()
        rs = np.inf if initial_avg_loss == 0 else initial_avg_gain / initial_avg_loss
        rsi = 100 - 100 / (1 + rs)
        df.loc[df.index[period], "rsi"] = rsi
        avg_gain = initial_avg_gain
        avg_loss = initial_avg_loss
        for i in range(period + 1, len(df)):
            current_gain = df["gain"].iloc[i]
            current_loss = df["loss"].iloc[i]
            avg_gain = (avg_gain * (period - 1) + current_gain) / period
            avg_loss = (avg_loss * (period - 1) + current_loss) / period
            rs = np.inf if avg_loss == 0 else avg_gain / avg_loss
            df.loc[df.index[i], "rsi"] = 100 - 100 / (1 + rs)
    df["rsi"] = df["rsi"].fillna(method="ffill")
    return df


def calculate_macd(df: pd.DataFrame, short_period: int = 12, long_period: int = 26, signal_period: int = 9) -> pd.DataFrame:
    ema_short = df["close"].ewm(span=short_period, adjust=True).mean()
    ema_long = df["close"].ewm(span=long_period, adjust=True).mean()
    df["macd"] = ema_short - ema_long
    df["macd_signal"] = df["macd"].ewm(span=signal_period, adjust=True).mean()
    df["macd_histogram"] = df["macd"] - df["macd_signal"]
    return df


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    range1 = df["high"] - df["low"]
    range2 = (df["high"] - df["close"].shift()).abs()
    range3 = (df["low"] - df["close"].shift()).abs()
    df["true_range"] = pd.concat([range1, range2, range3], axis=1).max(axis=1)
    if len(df) > period:
        initial_atr = df["true_range"].iloc[0:period].mean()
        df.loc[df.index[period - 1], "atr"] = initial_atr
        for i in range(period, len(df)):
            prev_atr = df["atr"].iloc[i - 1]
            current_tr = df["true_range"].iloc[i]
            df.loc[df.index[i], "atr"] = (prev_atr * (period - 1) + current_tr) / period
    df["atr"] = df["atr"].fillna(method="ffill")
    return df


def train_model(df: pd.DataFrame) -> LogisticRegression:
    """Train a very small logistic regression model to predict upward movement."""

    df = df.dropna(subset=["ema", "rsi", "macd", "atr"]).copy()
    df["target"] = np.where(df["close"].shift(-1) > df["close"], 1, 0)
    features = df[["ema", "rsi", "macd", "atr"]].values[:-1]
    target = df["target"].values[:-1]
    model = LogisticRegression(max_iter=200)
    if len(features) > 10:
        model.fit(features, target)
    else:  # fall back to dummy model
        model.fit(np.zeros((1, 4)), np.array([0]))
    return model


def predict_signal(df: pd.DataFrame, model: LogisticRegression) -> str:
    """Return "Buy" or "Sell" using the trained model on the last row."""

    row = df[["ema", "rsi", "macd", "atr"]].iloc[-1].values.reshape(1, -1)
    pred = model.predict(row)[0]
    return "Buy" if pred == 1 else "Sell"


def process_crypto(symbols: List[str]):
    """Process all symbols and return latest signals."""

    results = []
    for symbol in symbols:
        df = fetch_historical_data(symbol, INTERVAL)
        if df is None or df.empty:
            results.append([symbol, "N/A", "N/A", "N/A"])
            continue
        df = calculate_ema(df)
        df = calculate_rsi(df)
        df = calculate_macd(df)
        df = calculate_atr(df)
        model = train_model(df)
        ml_signal = predict_signal(df, model)
        latest_price = f"{df['close'].iloc[-1]:.8f}"
        results.append([symbol, latest_price, ml_signal, f"{df['rsi'].iloc[-1]:.2f}"])
    return results


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Simple crypto bot")
    parser.add_argument(
        "--symbols",
        type=str,
        default="ALL",
        help="Comma separated list of symbols or ALL",
    )
    args = parser.parse_args(argv)

    symbols = (
        args.symbols.upper().split(",") if args.symbols.upper() != "ALL" else TOP_CRYPTOS
    )
    symbols = [s.strip() for s in symbols if s.strip() in TOP_CRYPTOS]
    if not symbols and args.symbols.upper() != "ALL":
        print(f"Invalid symbols. Choose from: {', '.join(TOP_CRYPTOS)}")
        return

    while True:
        results = process_crypto(symbols)
        print("\nLatest signals (ML based):")
        for r in results:
            print(f"{r[0]} -> {r[2]} @ {r[1]} (RSI {r[3]})")
        print(f"\nWaiting {UPDATE_INTERVAL/60} minutes for next update...")
        try:
            time.sleep(UPDATE_INTERVAL)
        except KeyboardInterrupt:
            print("Stopping bot...")
            break


if __name__ == "__main__":  # pragma: no cover - manual run helper
    main()

