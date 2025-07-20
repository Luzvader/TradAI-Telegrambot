"""Motor de ejecuci\u00f3n simple para estrategias de trading."""
from __future__ import annotations

import importlib
import json
import logging
import pkgutil
import time
import threading
from pathlib import Path
from typing import Iterable, List, Dict, Any

from .tradingview import TradingViewClient
from .wallet import load_wallet

ORDERS_FILE = Path.home() / ".tradai_orders"


def load_strategies(package: str = "strategies") -> List[Any]:
    """Importa y devuelve instancias de estrategias dentro del *package*.

    Cada m\u00f3dulo del paquete debe exponer un atributo ``strategy`` que a su vez
    implemente un m\u00e9todo ``evaluate``.
    """
    try:
        pkg = importlib.import_module(package)
    except ModuleNotFoundError:
        logging.warning("Strategies package '%s' not found", package)
        return []

    strategies = []
    for mod_info in pkgutil.iter_modules(pkg.__path__):
        mod = importlib.import_module(f"{package}.{mod_info.name}")
        strat = getattr(mod, "strategy", None)
        if strat is not None:
            strategies.append(strat)
    return strategies


def log_order(entry: Dict[str, Any]) -> None:
    """Agrega una operaci\u00f3n al archivo de log ``ORDERS_FILE``."""
    try:
        data = json.loads(ORDERS_FILE.read_text())
    except Exception:
        data = []
    data.append(entry)
    ORDERS_FILE.write_text(json.dumps(data, indent=2))


class BotEngine:
    """Ejecuta peri\u00f3dicamente estrategias de trading."""

    def __init__(
        self,
        symbols: Iterable[str],
        interval_minutes: int = 5,
        strategies_pkg: str = "strategies",
    ) -> None:
        self.symbols = list(symbols)
        self.interval = interval_minutes
        self.strategies_pkg = strategies_pkg
        self.client = TradingViewClient()
        self.wallet = load_wallet()
        self.strategies = load_strategies(strategies_pkg)

    def run_once(self) -> None:
        """Ejecuta una sola iteraci\u00f3n de evaluaci\u00f3n."""
        if not self.wallet:
            logging.warning("No wallet configured")
            return
        markets = self.client.fetch_markets(self.symbols)
        for strategy in self.strategies:
            try:
                orders = strategy.evaluate(markets)
            except Exception as exc:  # pragma: no cover - unexpected strategy error
                logging.warning("Strategy %s failed: %s", strategy, exc)
                continue
            for order in orders:
                side = order.get("side")
                symbol = order.get("symbol")
                quantity = order.get("quantity", 0)
                if side in {"BUY", "SELL"} and symbol and quantity:
                    result = self.wallet.place_order(f"{symbol}USDT", side, quantity)
                    log_order({
                        "symbol": symbol,
                        "side": side,
                        "quantity": quantity,
                        "result": result,
                    })

    def run_forever(self, stop_event: threading.Event | None = None) -> None:  # pragma: no cover - infinite loop
        """Ejecuta el motor continuamente cada ``interval`` minutos.

        Si ``stop_event`` se proporciona se verificará antes de cada ciclo de
        espera para finalizar el bucle cuando se establezca.
        """
        while True:
            self.run_once()
            if stop_event and stop_event.wait(self.interval * 60):
                break
            time.sleep(self.interval * 60)

