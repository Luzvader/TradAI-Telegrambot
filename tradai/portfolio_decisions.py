from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Tuple
import logging
import cachetools

# Configuración de logging consistente con otros módulos
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cache para pesos del portafolio (1 hora)
WEIGHTS_CACHE = cachetools.TTLCache(maxsize=100, ttl=3600)

@dataclass
class Position:
    """Posición simple de una criptomoneda.

    Attributes:
        symbol (str): Símbolo de la criptomoneda (ej. "BTC").
        amount (float): Cantidad de la criptomoneda.
        price (float): Precio actual por unidad.
    """
    symbol: str
    amount: float
    price: float

    def __post_init__(self):
        """Valida que el símbolo sea válido (mayúsculas, alfanumérico)."""
        if not (isinstance(self.symbol, str) and self.symbol.isupper() and self.symbol.isalnum()):
            logger.error(f"Símbolo inválido: {self.symbol}")
            raise ValueError("El símbolo debe ser una cadena alfanumérica en mayúsculas")

    def value(self) -> float:
        """Calcula el valor de mercado de la posición.

        Returns:
            float: Valor (amount * price).

        Raises:
            ValueError: Si amount o price son negativos.
        """
        if self.amount < 0 or self.price < 0:
            logger.error(f"Valores inválidos en posición {self.symbol}: amount={self.amount}, price={self.price}")
            raise ValueError("Amount and price must be non-negative")
        return self.amount * self.price


@dataclass
class Portfolio:
    """Colección de posiciones y efectivo disponible.

    Attributes:
        cash (float): Efectivo disponible en el portafolio.
        positions (Dict[str, Position]): Diccionario de posiciones por símbolo.
    """
    cash: float = 0.0
    positions: Dict[str, Position] = field(default_factory=dict)

    def __post_init__(self):
        """Valida que el efectivo sea no negativo."""
        if self.cash < 0:
            logger.error(f"Efectivo negativo: {self.cash}")
            raise ValueError("Cash must be non-negative")

    def total_value(self) -> float:
        """Calcula el valor total del portafolio (efectivo + posiciones).

        Returns:
            float: Suma del efectivo y el valor de todas las posiciones.

        Raises:
            ValueError: Si alguna posición tiene valores inválidos.
        """
        return self.cash + sum(p.value() for p in self.positions.values())

    @cachetools.cachedmethod(lambda self: WEIGHTS_CACHE, key=lambda self: id(self))
    def weights(self) -> Dict[str, float]:
        """Calcula los porcentajes del portafolio por activo.

        Returns:
            Dict[str, float]: Porcentajes de cada símbolo (valor_posición / valor_total).
            Devuelve 0.0 para cada símbolo si el valor total es 0.

        Notes:
            - Usa caching para mejorar rendimiento en cálculos repetitivos.
        """
        total = self.total_value()
        if total == 0:
            logger.warning("Valor total del portafolio es 0")
            return {sym: 0.0 for sym in self.positions}
        return {sym: pos.value() / total for sym, pos in self.positions.items()}


def validate_threshold(threshold: float | Dict[str, float], target_weights: Dict[str, float]):
    """Valida el umbral (threshold) y lo convierte en diccionario si es un valor flotante."""
    if isinstance(threshold, dict):
        invalid_symbols = set(threshold.keys()) - set(target_weights.keys())
        if invalid_symbols:
            logger.error(f"Los siguientes símbolos en threshold no están en target_weights: {invalid_symbols}")
            raise ValueError("Todos los símbolos en 'threshold' deben estar en 'target_weights'")
    elif isinstance(threshold, float):
        if threshold < 0:
            logger.error(f"El umbral debe ser no negativo: {threshold}")
            raise ValueError("El umbral debe ser no negativo")
        threshold = {sym: threshold for sym in target_weights}
    else:
        logger.error(f"El umbral debe ser flotante o diccionario: {threshold}")
        raise ValueError("El umbral debe ser flotante o diccionario")
    return threshold


def calculate_adjustment(portfolio: Portfolio, sym: str, prices: Dict[str, float], target_weight: float, total_value: float) -> Tuple[float, float]:
    """Calcula el ajuste necesario para un símbolo en el portafolio."""
    current_value = portfolio.positions.get(sym, Position(sym, 0, prices.get(sym, 0))).value()
    current_weight = current_value / total_value if total_value > 0 else 0.0
    diff_weight = current_weight - target_weight
    return diff_weight, current_value


def handle_buy_decision(to_adjust_value: float, available_cash: float, to_adjust_amount: float) -> Tuple[str, float]:
    """Maneja la lógica de compra."""
    if to_adjust_value <= available_cash:
        return "BUY", to_adjust_amount
    else:
        logger.warning(f"Efectivo insuficiente para comprar: necesario {to_adjust_value}, disponible {available_cash}")
        return "HOLD", 0.0


def handle_sell_decision(to_adjust_amount: float, portfolio: Portfolio, sym: str) -> Tuple[str, float]:
    """Maneja la lógica de venta."""
    available_amount = portfolio.positions.get(sym, Position(sym, 0, portfolio.positions.get(sym, 0).price)).amount
    if abs(to_adjust_amount) <= available_amount:
        return "SELL", abs(to_adjust_amount)
    else:
        logger.warning(f"Cantidad insuficiente para vender {sym}: se necesita {abs(to_adjust_amount)}, disponible {available_amount}")
        return "SELL", available_amount


def decide_actions(
    portfolio: Portfolio,
    target_weights: Dict[str, float],
    prices: Dict[str, float],
    threshold: float | Dict[str, float] = 0.05,
    max_cash_allocation: float = 1.0,
) -> Dict[str, Tuple[str, float]]:
    """Genera acciones BUY/SELL/HOLD con cantidades para cada activo."""

    # Validaciones previas
    if not target_weights:
        logger.error("El parámetro 'target_weights' no puede estar vacío")
        raise ValueError("El parámetro 'target_weights' no puede estar vacío")
    if not prices:
        logger.error("El parámetro 'prices' no puede estar vacío")
        raise ValueError("El parámetro 'prices' no puede estar vacío")
    if not all(isinstance(s, str) and s.isupper() and s.isalnum() for s in target_weights):
        logger.error("Los símbolos en target_weights deben ser alfanuméricos en mayúsculas")
        raise ValueError("Los símbolos deben ser alfanuméricos en mayúsculas")
    if not all(0 <= w <= 1 for w in target_weights.values()):
        logger.error("Los pesos objetivo deben estar entre 0 y 1")
        raise ValueError("Los pesos objetivo deben estar entre 0 y 1")
    weights_sum = sum(target_weights.values())
    if not 0.95 <= weights_sum <= 1.05:
        logger.error(f"La suma de los pesos objetivo debe ser ~1, encontrada: {weights_sum}")
        raise ValueError("La suma de los pesos objetivo debe ser aproximadamente 1")
    if not all(p > 0 for p in prices.values()):
        logger.error("Los precios deben ser positivos")
        raise ValueError("Los precios deben ser positivos")
    if not 0 <= max_cash_allocation <= 1:
        logger.error(f"max_cash_allocation debe estar entre 0 y 1: {max_cash_allocation}")
        raise ValueError("max_cash_allocation debe estar entre 0 y 1")

    threshold = validate_threshold(threshold, target_weights)

    # Actualizar precios en posiciones
    for sym, price in prices.items():
        if sym in portfolio.positions:
            portfolio.positions[sym].price = max(0, price)

    total_value = portfolio.total_value()
    if total_value == 0:
        logger.warning("El valor total del portafolio es 0; no se pueden tomar decisiones")
        return {sym: ("HOLD", 0.0) for sym in portfolio.positions}

    current_weights = portfolio.weights()
    decisions: Dict[str, Tuple[str, float]] = {}
    available_cash = portfolio.cash * max_cash_allocation

    # Procesar todos los símbolos (en target_weights o en portafolio)
    all_symbols = set(target_weights.keys()) | set(portfolio.positions.keys())
    for sym in all_symbols:
        target_weight = target_weights.get(sym, 0.0)
        sym_threshold = threshold.get(sym, 0.05)
        diff_weight, current_value = calculate_adjustment(portfolio, sym, prices, target_weight, total_value)

        decision, amount = "HOLD", 0.0
        if abs(diff_weight) > sym_threshold:
            target_value = target_weight * total_value
            to_adjust_value = target_value - current_value
            price = prices.get(sym)
            if price and price > 0:
                to_adjust_amount = to_adjust_value / price
                if to_adjust_amount > 0:
                    decision, amount = handle_buy_decision(to_adjust_value, available_cash, to_adjust_amount)
                    if decision == "BUY":
                        available_cash -= amount * price
                elif to_adjust_amount < 0:
                    decision, amount = handle_sell_decision(to_adjust_amount, portfolio, sym)
        decisions[sym] = (decision, amount)

    return decisions
