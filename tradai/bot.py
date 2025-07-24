import argparse
import logging
from typing import List

from rich.console import Console
from rich.table import Table
from .tradingview import TradingViewClient

# Configuración del logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def display_markets(markets: dict) -> None:
    """Muestra los mercados de forma más amigable."""
    console = Console()
    table = Table(title="Datos de Mercado")

    # Definir las columnas de la tabla
    table.add_column("Símbolo", style="cyan")
    table.add_column("Precio", style="green")
    table.add_column("EMA20", style="magenta")
    table.add_column("EMA50", style="yellow")
    table.add_column("RSI14", style="blue")

    # Agregar cada fila de datos
    for ticker, data in markets.items():
        try:
            price, ema20, ema50, rsi = data
            price_str = f"{float(price):.2f}" if price is not None else "N/A"
            ema20_str = f"{float(ema20):.2f}" if ema20 is not None else "N/A"
            ema50_str = f"{float(ema50):.2f}" if ema50 is not None else "N/A"
            rsi_str = f"{float(rsi):.2f}" if rsi is not None else "N/A"
            table.add_row(ticker, price_str, ema20_str, ema50_str, rsi_str)
        except Exception as e:
            logger.error(f"Error procesando los datos de {ticker}: {e}")

    # Mostrar la tabla en consola
    console.print(table)

def main(args: List[str] | None = None) -> None:
    """Punto de entrada principal del CLI para obtener datos de TradingView."""
    parser = argparse.ArgumentParser(
        description="Obtener datos de mercados desde TradingView"
    )
    parser.add_argument(
        "symbols",
        nargs="+",
        help="Lista de criptomonedas (ej. BTC, ETH)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Mostrar más detalles sobre los datos de los mercados"
    )
    parser.add_argument(
        "-i", "--interval",
        type=int,
        default=300,
        help="Intervalo en segundos entre cada consulta (por defecto 300 segundos)"
    )
    parsed = parser.parse_args(args)

    client = TradingViewClient()

    try:
        logger.info(f"Obteniendo datos para los símbolos: {', '.join(parsed.symbols)}...")
        # Solicitamos los datos de los mercados para los símbolos indicados
        markets = client.fetch_markets(parsed.symbols)
        
        if not markets:
            logger.warning("No se encontraron datos para los símbolos solicitados.")
            return
        
        if parsed.verbose:
            logger.info("Mostrando detalles completos de los mercados...")

        # Mostrar los datos de los mercados en formato tabla
        display_markets(markets)
        
        # Mostrar un mensaje indicando que la consulta se completó
        logger.info("Consulta completada.")
        
    except Exception as e:
        logger.error(f"Hubo un error al obtener los datos: {e}")

if __name__ == "__main__":
    main()
