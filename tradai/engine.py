from __future__ import annotations
from typing import List, Dict, Any
import logging
import csv
import time
from datetime import datetime
from .strategies import Strategy
from .wallet import Wallet, InsufficientFundsError, InvalidOrderError

# Configuración básica para logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Path para almacenar el historial de transacciones
TRANSACTION_HISTORY_FILE = "transaction_history.csv"


def log_transaction(symbol: str, action: str, amount: float, price: float, total: float) -> None:
    """Registra las transacciones en un archivo CSV."""
    try:
        with open(TRANSACTION_HISTORY_FILE, mode="a", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([datetime.now().isoformat(), symbol, action, amount, price, total])
    except Exception as e:
        logger.error(f"Error al registrar la transacción: {e}")


def simulate_order(action: str, amount: float, wallet: Wallet, price: float) -> str:
    """Simula una operación sin ejecutar realmente la orden."""
    if action == "BUY" and wallet.balance >= amount * price:
        return "Simulación exitosa: Compra"
    elif action == "SELL" and wallet.get_balance(symbol) >= amount:
        return "Simulación exitosa: Venta"
    else:
        return "Simulación fallida: Fondos insuficientes"


def execute_strategy(strategy: Strategy, prices: List[float], wallet: Wallet, amount: float = 1.0, simulate: bool = False) -> Dict[str, Any]:
    """
    Evalúa una estrategia de inversión en criptomonedas y ejecuta la orden correspondiente.
    
    **strategy**: Instancia de Strategy que define la lógica de inversión.
    **prices**: Lista de precios históricos de la criptomoneda.
    **wallet**: Instancia de Wallet para gestionar las órdenes.
    **amount**: Cantidad de la criptomoneda para la orden (default=1.0).
    **simulate**: Si es True, simula la orden sin ejecutarla realmente (default=False).
    
    **Retorna:** Diccionario con estado de la orden ("status", "action", "message", "amount", etc.)
    """
    # Validación de parámetros
    if not isinstance(strategy, Strategy):
        raise TypeError("La estrategia debe ser una instancia de Strategy.")
    if not prices:
        raise ValueError("La lista de precios no puede estar vacía.")
    if not isinstance(wallet, Wallet):
        raise TypeError("La wallet debe ser una instancia de Wallet.")
    if amount <= 0:
        raise ValueError("La cantidad para la orden debe ser mayor a cero.")

    # Evaluación de la estrategia
    try:
        action = strategy.evaluate(prices)
        
        # Acciones válidas: BUY o SELL
        if action not in {"BUY", "SELL"}:
            logger.warning(f"Acción inválida desde la estrategia: {action}")
            return {"status": "failed", "message": f"Acción inválida: {action}"}
        
        # Simulación de la orden si `simulate` es True
        if simulate:
            price = prices[-1]  # Usamos el último precio disponible
            total = price * amount
            message = simulate_order(action, amount, wallet, price)
            return {"status": "simulated", "action": action, "message": message, "price": price, "amount": amount}
        
        # Si no es simulación, ejecutamos la orden real
        price = prices[-1]  # Último precio de la lista de precios
        total = price * amount
        
        if action == "BUY":
            if wallet.balance >= total:
                wallet.place_order(strategy.symbol, action, amount)
                log_transaction(strategy.symbol, action, amount, price, total)
                logger.info(f"Orden ejecutada: {action} {amount} {strategy.symbol} a {price}")
                return {"status": "success", "action": action, "price": price, "amount": amount, "total": total}
            else:
                return {"status": "failed", "message": "Fondos insuficientes para la compra"}
        
        elif action == "SELL":
            if wallet.get_balance(strategy.symbol) >= amount:
                wallet.place_order(strategy.symbol, action, amount)
                log_transaction(strategy.symbol, action, amount, price, total)
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
from .strategies import MyStrategy
from .wallet import MyWallet

# Inicialización
strategy = MyStrategy(symbol="BTC")
wallet = MyWallet(balance=1000.0)  # Balance en USD, por ejemplo

# Lista de precios (ejemplo)
prices = [34000.0, 35000.0, 32000.0, 33000.0, 36000.0]

# Ejecución de la estrategia con una cantidad personalizada
result = execute_strategy(strategy, prices, wallet, amount=0.5, simulate=True)
print(result)  # Resultado de la simulación (no ejecución real)

# Ejecución real (sin simulación)
real_result = execute_strategy(strategy, prices, wallet, amount=0.5, simulate=False)
print(real_result)  # Resultado real (con ejecución)

