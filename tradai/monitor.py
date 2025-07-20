"""Herramientas para monitorear precios de TradingView continuamente."""

from __future__ import annotations

import argparse
import threading
import time
from typing import Dict, Iterable, List

from .tradingview import TradingViewClient, columns_for_timeframe


def monitor_prices(symbols: Iterable[str], interval: int = 300) -> None:
    """Monitoriza precios e indicadores hasta que el usuario escriba ``s``."""

    frames = {
        "5m": 5 * 60,
        "15m": 15 * 60,
        "1h": 60 * 60,
        "4h": 4 * 60 * 60,
        "1d": 24 * 60 * 60,
        "1w": 7 * 24 * 60 * 60,
    }

    timeframe = ""
    while timeframe not in frames:
        timeframe = input(
            "Selecciona la temporalidad (5m, 15m, 1h, 4h, 1d, 1w): "
        ).strip()
    frame_seconds = frames[timeframe]

    try:
        compare_n = int(
            input(
                "Comparar vela actual con cuantas anteriores? (0 para deshabilitar): "
            ).strip()
        )
    except ValueError:
        compare_n = 0

    client = TradingViewClient()
    closes: Dict[str, List[float]] = {sym: [] for sym in symbols}
    frame_index: Dict[str, int] = {}
    stop_event = threading.Event()

    def wait_for_stop() -> None:
        while not stop_event.is_set():
            cmd = input().strip().lower()
            if cmd == "s":
                stop_event.set()

    threading.Thread(target=wait_for_stop, daemon=True).start()
    print(
        "Inicio del monitoreo. Escribe 's' y presiona Enter para detener.",
        f" Temporalidad seleccionada: {timeframe}",
    )

    columns = columns_for_timeframe(timeframe)[3:]
    while not stop_event.is_set():
        print("\n" + "-" * 40)

        try:
            markets = client.fetch_markets(symbols, columns=columns)
        except Exception as exc:  # pragma: no cover - networking
            print(f"Advertencia: no se pudieron obtener datos ({exc})")
            markets = {}
        ts = int(time.time())
        current_frame = ts // frame_seconds
        for ticker, data in markets.items():
            symbol = ticker.split(":")[1].replace(client.base_currency, "")
            price, ema20, ema50, rsi = data
            price = float(price)

            prev_idx = frame_index.get(symbol)
            if prev_idx is None:
                frame_index[symbol] = current_frame
            elif current_frame != prev_idx:
                closes[symbol].append(price)
                frame_index[symbol] = current_frame

            trend = ""
            if compare_n > 0 and len(closes[symbol]) >= compare_n:
                prev_close = closes[symbol][-compare_n]
                trend = "↑" if price > prev_close else "↓"

            ema20_str = f"{float(ema20):.2f}" if ema20 is not None else "N/A"
            ema50_str = f"{float(ema50):.2f}" if ema50 is not None else "N/A"
            rsi_str = f"{float(rsi):.2f}" if rsi is not None else "N/A"
            print(
                f"{symbol}: Precio {price} | EMA20 {ema20_str} | EMA50 {ema50_str} "
                f"| RSI14 {rsi_str} {trend}"
            )

        for remaining in range(interval, 0, -1):
            if stop_event.is_set():
                break
            print(f"Próximo refresco en {remaining}s", end="\r", flush=True)
            time.sleep(1)
        print(" " * 30, end="\r")
        if not stop_event.is_set():
            print()


def main(args: List[str] | None = None) -> None:
    """CLI para ``monitor_prices``."""
    parser = argparse.ArgumentParser(description="Monitorear precios continuamente")
    parser.add_argument(
        "symbols",
        nargs="+",
        help="Lista de criptomonedas (ej. BTC ETH)",
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default=300,
        help="Segundos entre refrescos (por defecto 300)",
    )
    parsed = parser.parse_args(args)
    monitor_prices(parsed.symbols, interval=parsed.interval)


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
