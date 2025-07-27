from __future__ import annotations
from typing import List, Dict, Any, Optional
import logging
import csv
import time
from datetime import datetime
from pathlib import Path
import threading
import numpy as np

from .strategies import Strategy
from .wallet import Wallet, InsufficientFundsError, InvalidOrderError

# Configuración básica para logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def log_transaction(
    symbol: str,
    action: str,
    amount: float,
    price: float,
    total: float,
    transaction_file: Path,
    file_lock: threading.Lock,
    simulated: bool = False
) -> None:
    """Registra las transacciones en un archivo CSV."""
    try:
        with file_lock:
            with transaction_file.open(mode="a", newline="") as file:
                writer = csv.writer(file)
                writer.writerow([datetime.now().isoformat(), symbol, action, amount, price, total, simulated])
        logger.info(f"{'Simulación' if simulated else 'Transacción'} registrada: {action} {amount} {symbol} a {price}")
    except Exception as e:
        logger.error(f"Error al registrar transacción: {e}")

def simulate_order(
    action: str,
    amount: float,
    wallet: Wallet,
    price: float,
    symbol: str,
    fee_rate: float = 0.001,
) -> str:
    """Simula una operación sin ejecutar realmente la orden."""
    total = amount * price * (1 + fee_rate) if action == "BUY" else amount * price * (1 - fee_rate)
    try:
        if action == "BUY" and wallet.get_balance("USDT") >= total:
            return f"Simulación exitosa: Compra de {amount} a {price} (total con fee: {total:.2f})"
        elif action == "SELL" and wallet.get_balance(symbol) >= amount:
            return f"Simulación exitosa: Venta de {amount} a {price} (total con fee: {total:.2f})"
        else:
            return "Simulación fallida: Fondos insuficientes"
    except Exception as e:
        logger.error(f"Error en simulación: {e}")
        return f"Simulación fallida: {e}"

def execute_strategy(
    strategy: Strategy,
    prices: List[float],
    wallet: Wallet,
    amount: float = 1.0,
    simulate: bool = False,
    transaction_file: Optional[Path] = None,
    file_lock: Optional[threading.Lock] = None
) -> Dict[str, Any]:
    """
    Evalúa una estrategia de inversión en criptomonedas y ejecuta la orden correspondiente.
    
    Args:
        strategy: Instancia de Strategy que define la lógica de inversión.
        prices: Lista de precios históricos de la criptomoneda.
        wallet: Instancia de Wallet para gestionar las órdenes.
        amount: Cantidad de la criptomoneda para la orden (default=1.0).
        simulate: Si es True, simula la orden sin ejecutarla realmente (default=False).
        transaction_file: Archivo CSV para registrar transacciones (default=transaction_history.csv).
        file_lock: Objeto threading.Lock para escritura segura (default=None).
    
    Returns:
        Diccionario con estado de la orden ("status", "action", "message", "amount", etc.)
    """
    # Validación de parámetros
    if not isinstance(strategy, Strategy):
        raise TypeError("La estrategia debe ser una instancia de Strategy.")
    if not prices or not all(isinstance(p, (int, float)) and not np.isnan(p) and p > 0 for p in prices):
        raise ValueError("La lista de precios debe contener valores numéricos válidos y no vacíos.")
    if not isinstance(wallet, Wallet):
        raise TypeError("La wallet debe ser una instancia de Wallet.")
    if amount <= 0:
        raise ValueError("La cantidad para la orden debe ser mayor a cero.")
    
    # Configuración de archivo de transacciones
    transaction_file = transaction_file or Path("transaction_history.csv")
    transaction_file.parent.mkdir(parents=True, exist_ok=True)
    file_lock = file_lock or threading.Lock()

    # Evaluación de la estrategia
    try:
        action = strategy.evaluate(prices)
        
        # Validar acción
        if action not in {"BUY", "SELL"}:
            logger.warning(f"Acción inválida desde la estrategia: {action}")
            return {"status": "failed", "message": f"Acción inválida: {action}"}
        
        price = prices[-1]  # Último precio disponible
        total = price * amount
        
        # Simulación de la orden
        if simulate:
            message = simulate_order(action, amount, wallet, price, strategy.symbol)
            log_transaction(strategy.symbol, action, amount, price, total, transaction_file, file_lock, simulated=True)
            return {"status": "simulated", "action": action, "message": message, "price": price, "amount": amount, "total": total}
        
        # Ejecución real
        if action == "BUY":
            if wallet.get_balance("USDT") >= total:
                wallet.place_order(strategy.symbol, action, amount)
                log_transaction(strategy.symbol, action, amount, price, total, transaction_file, file_lock)
                logger.info(f"Orden ejecutada: {action} {amount} {strategy.symbol} a {price}")
                return {"status": "success", "action": action, "price": price, "amount": amount, "total": total}
            else:
                return {"status": "failed", "message": "Fondos insuficientes para la compra"}

        elif action == "SELL":
            if wallet.get_balance(strategy.symbol) >= amount:
                wallet.place_order(strategy.symbol, action, amount)
                log_transaction(strategy.symbol, action, amount, price, total, transaction_file, file_lock)
                logger.info(f"Orden ejecutada: {action} {amount} {strategy.symbol} a {price}")
                return {"status": "success", "action": action, "price": price, "amount": amount, "total": total}
            else:
                return {"status": "failed", "message": f"No tienes suficientes {strategy.symbol} para vender."}
    
    except InsufficientFundsError as e:
        logger.error(f"Fondos insuficientes para la orden: {e}")
        return {"status": "failed", "message": "Fondos insuficientes"}
    
    except InvalidOrderError as e:
        logger.error(f"Orden inválida: {e}")
        return {"status": "failed", "message": "Orden inválida"}
    
    except Exception as e:
        logger.critical(f"Error inesperado: {e}")
        return {"status": "failed", "message": "Error inesperado"}

# Ejemplo de uso con simulación y backtesting
if __name__ == "__main__":
    from .strategies import MyStrategy
    from .wallet import MyWallet

    # Inicialización
    strategy = MyStrategy(symbol="BTC")
    wallet = MyWallet(balance=1000.0)  # Balance en USD
    prices = [34000.0, 35000.0, 32000.0, 33000.0, 36000.0]

    # Ejecución de la estrategia con simulación
    result = execute_strategy(strategy, prices, wallet, amount=0.5, simulate=True)
    print(result)

    # Ejecución real
    real_result = execute_strategy(strategy, prices, wallet, amount=0.5, simulate=False)
    print(real_result)