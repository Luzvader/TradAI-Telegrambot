import requests
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
from tabulate import tabulate
import time
import numpy as np
import argparse
import socket

# List of cryptocurrency trading pairs
top_cryptos = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT", "SOLUSDT",
    "USDCUSDT", "DOGEUSDT", "TRXUSDT", "ADAUSDT", "LTCUSDT",
    "PEPEUSDT", "BONKUSDT", "KCSUSDT"
]

# Parameters
interval = "5m"          # Time interval for data (5 minutes)
update_interval = 900    # Update interval in seconds (15 minutes)

# Binance API endpoint for historical data
url = "https://api.binance.com/api/v3/klines"

def fetch_historical_data(symbol, interval, max_retries=3, retry_delay=5):
    """Fetch historical data with retry logic for connection errors."""
    for attempt in range(max_retries):
        try:
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": 1000
            }
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if not data:
                raise ValueError(f"No data returned for {symbol}")
            df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume",
                                            "close_time", "quote_asset_vol", "number_of_trades",
                                            "taker_buy_base_asset_vol", "taker_buy_quote_asset_vol", "ignore"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric)
            return df.sort_values(by="timestamp")
        except socket.gaierror as e:
            if e.errno == -3:
                print(f"Temporary name resolution failure for {symbol} (attempt {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    print(f"Failed to fetch data for {symbol} after {max_retries} attempts")
                    return None
            else:
                raise
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data for {symbol} (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                print(f"Failed to fetch data for {symbol} after {max_retries} attempts")
                return None

def calculate_ema(df, period=14):
    """Calculate Exponential Moving Average with standard trading settings."""
    df['ema'] = df['close'].ewm(span=period, adjust=True).mean()
    return df

def calculate_rsi(df, period=14):
    """Calculate RSI using Wilder's smoothing."""
    df['delta'] = df['close'].diff()
    df['gain'] = df['delta'].where(df['delta'] > 0, 0)
    df['loss'] = -df['delta'].where(df['delta'] < 0, 0)
    if len(df) > period:
        initial_avg_gain = df['gain'].iloc[1:period+1].mean()
        initial_avg_loss = df['loss'].iloc[1:period+1].mean()
        if initial_avg_loss == 0:
            rs = float('inf')
        else:
            rs = initial_avg_gain / initial_avg_loss
        rsi = 100 - 100 / (1 + rs)
        df.loc[df.index[period], 'rsi'] = rsi
        avg_gain = initial_avg_gain
        avg_loss = initial_avg_loss
        for i in range(period+1, len(df)):
            current_gain = df['gain'].iloc[i]
            current_loss = df['loss'].iloc[i]
            avg_gain = (avg_gain * (period - 1) + current_gain) / period
            avg_loss = (avg_loss * (period - 1) + current_loss) / period
            if avg_loss == 0:
                rs = float('inf')
            else:
                rs = avg_gain / avg_loss
            rsi_val = 100 - 100 / (1 + rs)
            df.loc[df.index[i], 'rsi'] = rsi_val
    df['rsi'] = df['rsi'].fillna(method='ffill')
    return df

def calculate_macd(df, short_period=12, long_period=26, signal_period=9):
    """Calculate MACD with standard periods."""
    ema_short = df['close'].ewm(span=short_period, adjust=True).mean()
    ema_long = df['close'].ewm(span=long_period, adjust=True).mean()
    df['macd'] = ema_short - ema_long
    df['macd_signal'] = df['macd'].ewm(span=signal_period, adjust=True).mean()
    df['macd_histogram'] = df['macd'] - df['macd_signal']
    return df

def calculate_atr(df, period=14):
    """Calculate ATR using Wilder's smoothing."""
    range1 = df['high'] - df['low']
    range2 = (df['high'] - df['close'].shift()).abs()
    range3 = (df['low'] - df['close'].shift()).abs()
    df['true_range'] = pd.concat([range1, range2, range3], axis=1).max(axis=1)
    if len(df) > period:
        initial_atr = df['true_range'].iloc[0:period].mean()
        df.loc[df.index[period-1], 'atr'] = initial_atr
        for i in range(period, len(df)):
            prev_atr = df['atr'].iloc[i-1]
            current_tr = df['true_range'].iloc[i]
            atr = (prev_atr * (period - 1) + current_tr) / period
            df.loc[df.index[i], 'atr'] = atr
    df['atr'] = df['atr'].fillna(method='ffill')
    return df

def detect_candle_patterns(df):
    """Detect simple candlestick patterns."""
    df['candle_pattern'] = 'None'
    for i in range(1, len(df)):
        open_price = df['open'].iloc[i]
        close_price = df['close'].iloc[i]
        high_price = df['high'].iloc[i]
        low_price = df['low'].iloc[i]
        prev_open = df['open'].iloc[i-1]
        prev_close = df['close'].iloc[i-1]
        body = abs(close_price - open_price)
        lower_shadow = abs(low_price - min(open_price, close_price))
        upper_shadow = abs(high_price - max(open_price, close_price))
        if body > 0 and lower_shadow > 2 * body and upper_shadow < body and close_price > open_price:
            df['candle_pattern'].iloc[i] = 'Hammer'
        if close_price > open_price and prev_close < prev_open and close_price > prev_open and open_price < prev_close:
            df['candle_pattern'].iloc[i] = 'Bullish Engulfing'
        if close_price < open_price and prev_close > prev_open and close_price < prev_open and open_price > prev_close:
            df['candle_pattern'].iloc[i] = 'Bearish Engulfing'
    return df

def generate_signals(df, symbol):
    """Generate signals using EMA, RSI, MACD, ATR, and candlestick patterns."""
    if symbol in ["USDTUSDT", "USDCUSDT"]:
        return ["Hold"] * (len(df) - 1)
    signals = []
    for i in range(1, len(df)):
        if pd.notna(df['rsi'].iloc[i]) and pd.notna(df['atr'].iloc[i]) and pd.notna(df['candle_pattern'].iloc[i]):
            if (df['close'].iloc[i] > df['ema'].iloc[i] and
                df['close'].iloc[i-1] <= df['ema'].iloc[i-1] and
                df['rsi'].iloc[i] < 30 and
                df['macd'].iloc[i] > df['macd_signal'].iloc[i] and
                df['atr'].iloc[i] < df['atr'].mean() and
                df['candle_pattern'].iloc[i] in ['Hammer', 'Bullish Engulfing']):
                signals.append("Buy")
            elif (df['close'].iloc[i] < df['ema'].iloc[i] and
                  df['close'].iloc[i-1] >= df['ema'].iloc[i-1] and
                  df['rsi'].iloc[i] > 70 and
                  df['macd'].iloc[i] < df['macd_signal'].iloc[i] and
                  df['atr'].iloc[i] > df['atr'].mean() and
                  df['candle_pattern'].iloc[i] == 'Bearish Engulfing'):
                signals.append("Sell")
            else:
                signals.append("Hold")
        else:
            signals.append("Hold")
    return signals

def plot_data(df, symbol):
    """Plot candlestick chart and indicators."""
    mpf.plot(df.set_index('timestamp').tail(100), type='candle', style='charles',
             title=f"{symbol} Candlestick Chart", ylabel='Price (USDT)', volume=True)
    plt.figure(figsize=(12, 8))
    plt.subplot(3, 1, 1)
    plt.plot(df['timestamp'], df['close'], label='Close Price', color='blue')
    plt.plot(df['timestamp'], df['ema'], label='EMA (14)', color='red')
    plt.title(f"Price and EMA for {symbol}")
    plt.xlabel('Date')
    plt.ylabel('Price (USDT)')
    plt.legend()
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.subplot(3, 1, 2)
    plt.plot(df['timestamp'], df['rsi'], label='RSI', color='purple')
    plt.axhline(70, color='red', linestyle='--', label='Overbought (70)')
    plt.axhline(30, color='green', linestyle='--', label='Oversold (30)')
    plt.title(f"RSI for {symbol}")
    plt.xlabel('Date')
    plt.ylabel('RSI')
    plt.legend()
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.subplot(3, 1, 3)
    plt.plot(df['timestamp'], df['atr'], label='ATR (14)', color='orange')
    plt.title(f"ATR for {symbol}")
    plt.xlabel('Date')
    plt.ylabel('ATR')
    plt.legend()
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()

def format_price(price):
    """Convert scientific notation to standard float and format as string."""
    return f"{float(price):.8f}"

def process_crypto(symbols):
    """Process cryptocurrencies and generate signals."""
    results = []
    for symbol in symbols:
        df = fetch_historical_data(symbol, interval)
        if df is None or df.empty:
            results.append([symbol, "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"])
            continue
        df = calculate_ema(df)
        df = calculate_rsi(df)
        df = calculate_macd(df)
        df = calculate_atr(df)
        df = detect_candle_patterns(df)
        signals = generate_signals(df, symbol)
        latest_signal = signals[-1] if signals else "N/A"
        latest_price = format_price(df['close'].iloc[-1]) if not df.empty else "N/A"
        latest_rsi = f"{df['rsi'].iloc[-1]:.2f}" if not df.empty and pd.notna(df['rsi'].iloc[-1]) else "N/A"
        latest_macd = f"{df['macd'].iloc[-1]:.2f}" if not df.empty and pd.notna(df['macd'].iloc[-1]) else "N/A"
        latest_atr = f"{df['atr'].iloc[-1]:.8f}" if not df.empty and pd.notna(df['atr'].iloc[-1]) else "N/A"
        latest_candle = df['candle_pattern'].iloc[-1] if not df.empty else "N/A"
        results.append([symbol, latest_price, latest_signal, latest_rsi, latest_macd, latest_atr, latest_candle])
        plot_data(df, symbol)
    return results

def main():
    """Main function with command-line argument parsing."""
    parser = argparse.ArgumentParser(description="Cryptocurrency Trading Bot")
    parser.add_argument('--symbols', type=str, default='ALL', help="Comma-separated list of symbols or 'ALL' for top cryptos.")
    args = parser.parse_args()
    symbols = args.symbols.upper().split(',') if args.symbols.upper() != 'ALL' else top_cryptos
    symbols = [symbol.strip() for symbol in symbols if symbol.strip() in top_cryptos]
    if not symbols and args.symbols.upper() != 'ALL':
        print(f"Invalid symbols. Please choose from: {', '.join(top_cryptos)}")
        return
    while True:
        try:
            results = process_crypto(symbols)
            print("\nLatest Signals:")
            print(tabulate(results, headers=["Symbol", "Latest Price (USDT)", "Signal", "RSI", "MACD", "ATR", "Candle Pattern"], tablefmt="grid"))
            print(f"\nWaiting {update_interval / 60} minutes for next update...")
            time.sleep(update_interval)
        except KeyboardInterrupt:
            print("\nStopping the bot...")
            break
        except Exception as e:
            print(f"Error occurred: {e}")
            print("Retrying in 60 seconds...")
            time.sleep(60)

if __name__ == "__main__":
    main()