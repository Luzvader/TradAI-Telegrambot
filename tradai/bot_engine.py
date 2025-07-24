"""Motor de ejecuci\u00f3n simple para estrategias de trading."""
from __future__ import annotations

import importlib
import time
import json
import logging
import pkgutil
import time
import threading
from pathlib import Path
from typing import Iterable, List, Dict, Any

from .tradingview import TradingViewClient
from .wallet import load_wallet
# Integración de señales y scikit-learn
from .services.market_service import get_crypto_signals
from sklearn.ensemble import RandomForestClassifier
import numpy as np
import pickle
# Integración de señales y scikit-learn
from .services.market_service import get_crypto_signals
from sklearn.ensemble import RandomForestClassifier
import numpy as np

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

        self.backlog_file = Path.home() / ".tradai_signals_backlog"
        self.model_file = Path.home() / ".tradai_ml_model.pkl"
        self.ml_model = RandomForestClassifier()
        self.ml_trained = False
        self.backlog = self._load_backlog()
        self._load_model()

    def _load_backlog(self):
        if self.backlog_file.exists():
            try:
                return json.loads(self.backlog_file.read_text())
            except Exception:
                return []
        return []

    def _save_backlog(self):
        self.backlog_file.write_text(json.dumps(self.backlog, indent=2))

    def _save_model(self):
        with open(self.model_file, "wb") as f:
            pickle.dump(self.ml_model, f)

    def _load_model(self):
        if self.model_file.exists():
            try:
                with open(self.model_file, "rb") as f:
                    self.ml_model = pickle.load(f)
                    self.ml_trained = True
            except Exception:
                self.ml_trained = False

        # Ejemplo: modelo ML para señales (puedes entrenarlo con tus datos históricos)
        self.ml_model = RandomForestClassifier()
        self.ml_trained = False

    def run_once(self) -> None:
        """Ejecuta una sola iteraci\u00f3n de evaluaci\u00f3n."""
        if not self.wallet:
            logging.warning("No wallet configured")
            return
        # --- Usar señales e indicadores, guardar backlog y entrenar modelo ML ---
        for symbol in self.symbols:
            result = get_crypto_signals(f"{symbol}USDT")
            if "error" in result:
                logging.warning(f"No data for {symbol}")
                continue
            # Guardar en backlog
            self.backlog.append({
                "symbol": symbol,
                "timestamp": time.time(),
                "price": result["latest_price"],
                "signal": result["latest_signal"],
                "rsi": result["latest_rsi"],
                "macd": result["latest_macd"],
                "atr": result["latest_atr"],
                "candle": result["latest_candle"],
            })
        self._save_backlog()

        # Entrenar modelo ML si hay suficiente backlog
        if not self.ml_trained and len(self.backlog) > 20:
            X = np.array([
                [entry["rsi"] or 0, entry["macd"] or 0, entry["atr"] or 0]
                for entry in self.backlog
            ])
            y = np.array([
                1 if entry["signal"] == "BUY" else 0 if entry["signal"] == "SELL" else -1
                for entry in self.backlog
            ])
            # Filtrar señales válidas
            mask = y != -1
            if np.any(mask):
                self.ml_model.fit(X[mask], y[mask])
                self.ml_trained = True
                self._save_model()

        # Tomar decisiones usando el modelo ML si está entrenado
        for entry in self.backlog[-len(self.symbols):]:
            if self.ml_trained:
                features = np.array([[entry["rsi"] or 0, entry["macd"] or 0, entry["atr"] or 0]])
                pred = self.ml_model.predict(features)[0]
                if pred in [0, 1]:
                    side = "BUY" if pred == 1 else "SELL"
                    quantity = 1
                    res = self.wallet.place_order(f"{entry['symbol']}USDT", side, quantity)
                    log_order({
                        "symbol": entry["symbol"],
                        "side": side,
                        "quantity": quantity,
                        "result": res,
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

