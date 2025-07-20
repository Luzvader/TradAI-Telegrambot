"""Script de línea de comandos para consultar datos de TradingView."""

import argparse
from typing import List

from .tradingview import TradingViewClient


def main(args: List[str] | None = None) -> None:
    """Punto de entrada principal del CLI."""
    parser = argparse.ArgumentParser(
        description="Obtener datos de mercados desde TradingView"
    )
    parser.add_argument(
        "symbols",
        nargs="+",
        help="Lista de criptomonedas (ej. BTC, ETH)",
    )
    parsed = parser.parse_args(args)

    client = TradingViewClient()
    # Solicitamos los datos de los mercados para los símbolos indicados
    markets = client.fetch_markets(parsed.symbols)
    for ticker, data in markets.items():
        # Imprimimos en pantalla cada ticker y su información asociada
        print(ticker, data)


if __name__ == "__main__":
    main()
