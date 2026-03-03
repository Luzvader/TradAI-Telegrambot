"""
Base abstracta para brokers – permite añadir otros brokers en el futuro.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrokerPosition:
    """Posición en el broker."""
    ticker: str
    shares: float
    avg_price: float
    current_price: float
    pnl: float
    pnl_pct: float
    market_value: float
    currency: str = "USD"
    frontend_name: str = ""  # Nombre legible del instrumento


@dataclass
class BrokerOrder:
    """Orden enviada al broker."""
    order_id: str
    ticker: str
    side: str  # "BUY" o "SELL"
    shares: float
    price: float | None  # None = market order
    status: str  # "NEW", "FILLED", "CANCELLED", "REJECTED"
    filled_price: float | None = None
    filled_shares: float | None = None
    timestamp: str = ""


@dataclass
class BrokerAccount:
    """Información de la cuenta del broker."""
    cash: float
    invested: float
    portfolio_value: float
    pnl: float
    pnl_pct: float
    currency: str = "USD"
    mode: str = "demo"  # "demo" o "real"


@dataclass
class BrokerResult:
    """Resultado genérico de una operación con el broker."""
    success: bool
    data: Any = None
    error: str = ""
    warnings: list[str] = field(default_factory=list)


class BaseBroker(ABC):
    """Interfaz abstracta para brokers."""

    @abstractmethod
    async def get_account(self) -> BrokerResult:
        """Obtiene info de la cuenta."""
        ...

    @abstractmethod
    async def get_positions(self) -> BrokerResult:
        """Obtiene posiciones abiertas."""
        ...

    @abstractmethod
    async def place_market_order(
        self, ticker: str, shares: float, side: str
    ) -> BrokerResult:
        """Coloca una orden de mercado."""
        ...

    @abstractmethod
    async def place_limit_order(
        self, ticker: str, shares: float, side: str, limit_price: float,
        time_validity: str = "GOOD_TILL_CANCEL",
    ) -> BrokerResult:
        """Coloca una orden limitada."""
        ...

    @abstractmethod
    async def place_stop_order(
        self, ticker: str, shares: float, side: str, stop_price: float,
        time_validity: str = "GOOD_TILL_CANCEL",
    ) -> BrokerResult:
        """Coloca una orden stop."""
        ...

    @abstractmethod
    async def place_stop_limit_order(
        self, ticker: str, shares: float, side: str,
        stop_price: float, limit_price: float,
        time_validity: str = "GOOD_TILL_CANCEL",
    ) -> BrokerResult:
        """Coloca una orden stop-limit."""
        ...

    async def place_value_order(
        self, ticker: str, amount: float, side: str
    ) -> BrokerResult:
        """
        Orden por valor monetario (comprar por importe).
        eToro soporta esto nativamente (by-amount).
        """
        return BrokerResult(
            success=False,
            error="Órdenes por valor no soportadas por este broker.",
        )

    @abstractmethod
    async def cancel_order(self, order_id: str) -> BrokerResult:
        """Cancela una orden pendiente."""
        ...

    @abstractmethod
    async def get_orders(self) -> BrokerResult:
        """Obtiene órdenes pendientes/recientes."""
        ...

    @abstractmethod
    async def search_instrument(self, query: str) -> BrokerResult:
        """Busca un instrumento por ticker o nombre."""
        ...

    @abstractmethod
    async def get_instrument_by_ticker(self, ticker: str) -> BrokerResult:
        """Obtiene info de un instrumento por ticker."""
        ...

    async def close_position(
        self, position_id: int | str, units_to_deduct: float | None = None
    ) -> BrokerResult:
        """Cierra una posición por su ID (para brokers como eToro)."""
        return BrokerResult(
            success=False,
            error="close_position no implementado para este broker.",
        )
