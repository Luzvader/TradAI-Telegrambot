import argparse
import logging
import time
import json
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from rich.console import Console
from rich.table import Table

from .tradingview import TradingViewClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def validate_symbols(symbols: List[str]) -> List[str]:
    valid_symbols = []
    for symbol in symbols:
        if not symbol.isupper() or not symbol.isalpha():
            logger.warning(f"Símbolo inválido: {symbol}. Debe contener solo letras mayúsculas (ej. BTC, ETH).")
        else:
            valid_symbols.append(symbol)
    return valid_symbols

def validate_market_data(data: Tuple, symbol: str) -> Optional[Tuple[float, float, float, float, Optional[float], Optional[float]]]:
    try:
        if len(data) < 4:
            logger.warning(f"Datos incompletos para {symbol}: {data}")
            return None
        price, ema20, ema50, rsi = data[:4]
        timestamp = data[4] if len(data) > 4 else time.time()
        volume = data[5] if len(data) > 5 else None
        if any(x is None or not isinstance(x, (int, float)) for x in [price, ema20, ema50, rsi]):
            logger.warning(f"Valores no numéricos para {symbol}: {data}")
            return None
        return (float(price), float(ema20), float(ema50), float(rsi), float(timestamp), float(volume) if volume is not None else None)
    except (TypeError, ValueError) as e:
        logger.error(f"Error validando datos para {symbol}: {e}")
        return None

def display_markets(markets: Dict[str, Tuple[float, float, float, float, Optional[float], Optional[float]]], verbose: bool = False) -> None:
    console = Console()
    table = Table(title="📊 Datos de Mercado")

    table.add_column("Símbolo", style="cyan")
    table.add_column("Precio", style="green")
    table.add_column("EMA20", style="magenta")
    table.add_column("EMA50", style="yellow")
    table.add_column("RSI14", style="blue")
    if verbose:
        table.add_column("Timestamp", style="white")
        table.add_column("Volumen", style="purple")

    for symbol, data in markets.items():
        try:
            price, ema20, ema50, rsi, timestamp, volume = data
            rsi_val = float(rsi)
            rsi_str = (
                f"[bold red]{rsi_val:.2f}[/]" if rsi_val > 70 else
                f"[bold green]{rsi_val:.2f}[/]" if rsi_val < 30 else
                f"{rsi_val:.2f}"
            )
            row = [
                symbol,
                f"{price:.2f}" if price is not None else "N/A",
                f"{ema20:.2f}" if ema20 is not None else "N/A",
                f"{ema50:.2f}" if ema50 is not None else "N/A",
                rsi_str,
            ]
            if verbose:
                row.append(time.ctime(timestamp) if timestamp else "N/A")
                row.append(f"{volume:.2f}" if volume is not None else "N/A")
            table.add_row(*row)
        except (TypeError, ValueError, IndexError) as e:
            logger.error(f"Error procesando {symbol}: {e}")
            row = [symbol, "N/A", "N/A", "N/A", "N/A"]
            if verbose:
                row.extend(["N/A", "N/A"])
            table.add_row(*row)

    console.print(table)

def save_markets(markets: Dict[str, Tuple[float, float, float, float, Optional[float], Optional[float]]], output_file: Path) -> None:
    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            ticker: {
                "price": d[0],
                "ema20": d[1],
                "ema50": d[2],
                "rsi14": d[3],
                "timestamp": d[4] if d[4] is not None else time.time(),
                "volume": d[5]
            } for ticker, d in markets.items()
        }
        with output_file.open("w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Datos guardados en {output_file}")
    except (IOError, TypeError, ValueError) as e:
        logger.error(f"Error guardando datos en {output_file}: {e}")

def fetch_and_display(
    client: TradingViewClient,
    symbols: List[str],
    verbose: bool = False,
    output_file: Optional[Path] = None
) -> None:
    markets = {}
    with ThreadPoolExecutor() as executor:
        results = executor.map(lambda s: (s, client.fetch_markets([s])), symbols)
        for symbol, data in results:
            if data is None:
                logger.warning(f"No data received for {symbol}")
                continue
            validated = validate_market_data(data.get(symbol, ()), symbol)
            if validated:
                markets[symbol] = validated
    if not markets:
        logger.warning("No se encontraron datos válidos.")
        return
    display_markets(markets, verbose)
    if output_file:
        save_markets(markets, output_file)

def main(args: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="CLI para consultar datos desde TradingView")
    parser.add_argument("symbols", nargs="+", help="Lista de símbolos (ej. BTC ETH BNB)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Mostrar timestamp y volumen")
    parser.add_argument("-i", "--interval", type=int, default=0, help="Intervalo en segundos entre consultas (0 para una sola vez)")
    parser.add_argument("-o", "--output", type=Path, help="Archivo de salida JSON (se agrega .json si no se especifica)")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO", help="Nivel de logging")

    parsed = parser.parse_args(args)
    logging.getLogger().setLevel(getattr(logging, parsed.log_level))

    if parsed.output and parsed.output.suffix != ".json":
        parsed.output = parsed.output.with_suffix(".json")

    valid_symbols = validate_symbols(parsed.symbols)
    if not valid_symbols:
        logger.error("No se proporcionaron símbolos válidos.")
        return

    client = TradingViewClient()

    try:
        if parsed.interval == 0:
            fetch_and_display(client, valid_symbols, parsed.verbose, parsed.output)
        else:
            while True:
                fetch_and_display(client, valid_symbols, parsed.verbose, parsed.output)
                logger.info(f"Esperando {parsed.interval} segundos para la próxima consulta...")
                time.sleep(parsed.interval)
    except KeyboardInterrupt:
        logger.info("⛔ Interrumpido por el usuario.")
    except Exception as e:
        logger.error(f"❌ Error inesperado: {e}")

if __name__ == "__main__":
    main()
