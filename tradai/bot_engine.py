from __future__ import annotations

import importlib
import time
import json
import logging
import pickle  # ✅ Import necesario para el modelo
import pkgutil
import threading
from pathlib import Path
from typing import Iterable, List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from sklearn.ensemble import RandomForestClassifier

from .tradingview import TradingViewClient
from .wallet import load_wallet

# Default path for logged orders used by services and tests
ORDERS_FILE = Path.home() / ".tradai_orders"
from .services.market_service import get_crypto_signals

# Ruta por defecto para el registro de órdenes
ORDERS_FILE = Path.home() / ".tradai_orders"

# ----------------------------
# Utilidades
# ----------------------------

def is_valid_features(entry: Dict[str, Any]) -> bool:
    """Valida si un diccionario tiene valores numéricos válidos para ML."""
    return all(
        isinstance(entry.get(k), (int, float)) and
        not (np.isnan(entry.get(k, np.nan)) or np.isinf(entry.get(k, np.nan)))
        for k in ("rsi", "macd", "atr")
    )

def log_order(entry: Dict[str, Any], orders_file: Path, file_lock: threading.Lock) -> None:
    """Agrega una operación al archivo de log."""
    try:
        with file_lock:
            try:
                data = json.loads(orders_file.read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                data = []
            data.append(entry)
            orders_file.write_text(json.dumps(data, indent=2))
            logging.info(f"Orden registrada: {entry}")
    except Exception as e:
        logging.error(f"Error al registrar orden: {e}")

def load_strategies(package: str = "strategies") -> List[Any]:
    """Importa y devuelve instancias de estrategias dentro del paquete especificado."""
    try:
        pkg = importlib.import_module(package)
    except ModuleNotFoundError:
        logging.warning("Paquete de estrategias '%s' no encontrado", package)
        return []

    strategies = []
    for mod_info in pkgutil.iter_modules(pkg.__path__):
        try:
            mod = importlib.import_module(f"{package}.{mod_info.name}")
            strat = getattr(mod, "strategy", None)
            if strat and callable(getattr(strat, "evaluate", None)):
                strategies.append(strat)
            else:
                logging.warning(f"Módulo {mod_info.name} no contiene una estrategia válida")
        except Exception as e:
            logging.error(f"Error al cargar estrategia de {mod_info.name}: {e}")
    return strategies

# ----------------------------
# Motor principal mejorado
# ----------------------------

class BotEngine:
    """Ejecuta periódicamente estrategias de trading y toma decisiones con ML."""

    def __init__(
        self,
        symbols: Iterable[str],
        interval_minutes: int = 5,
        strategies_pkg: str = "strategies",
        data_dir: Optional[Path] = None,
        quantity: int = 1,
        min_backlog_size: int = 20,
        log_level: int = logging.INFO,  # ✅ Permitir nivel de log configurable
    ) -> None:
        logging.basicConfig(level=log_level)

        self.symbols = list(symbols)
        self.interval = interval_minutes
        self.strategies_pkg = strategies_pkg
        self.quantity = quantity
        self.min_backlog_size = min_backlog_size

        self.client = TradingViewClient()
        self.wallet = load_wallet()
        self.strategies = load_strategies(strategies_pkg)
        self.file_lock = threading.Lock()

        # Directorios y archivos
        self.data_dir = data_dir or Path.home()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backlog_file = self.data_dir / ".tradai_signals_backlog"
        self.model_file = self.data_dir / ".tradai_ml_model.pkl"
        # Usa el nombre de ORDERS_FILE dentro del directorio de datos
        self.orders_file = self.data_dir / ORDERS_FILE.name

        self.ml_model = RandomForestClassifier()
        self.ml_trained = False
        self.last_trained_size = 0  # ✅ Prevención de reentrenamiento redundante
        self.backlog = self._load_backlog()
        self._load_model()

        # ✅ Métricas internas
        self.metrics = {
            "signals_fetched": 0,
            "orders_placed": 0,
            "orders_failed": 0,
        }

    def _load_backlog(self) -> List[Dict[str, Any]]:
        if self.backlog_file.exists():
            try:
                with self.file_lock:
                    return json.loads(self.backlog_file.read_text())
            except Exception as e:
                logging.error(f"Error al cargar backlog: {e}")
        return []

    def _save_backlog(self) -> None:
        try:
            with self.file_lock:
                self.backlog_file.write_text(json.dumps(self.backlog, indent=2))
        except Exception as e:
            logging.error(f"Error al guardar backlog: {e}")

    def _save_model(self) -> None:
        try:
            with self.file_lock:
                with open(self.model_file, "wb") as f:
                    pickle.dump(self.ml_model, f)
        except Exception as e:
            logging.error(f"Error al guardar modelo ML: {e}")

    def _load_model(self) -> None:
        if self.model_file.exists():
            try:
                with self.file_lock:
                    with open(self.model_file, "rb") as f:
                        self.ml_model = pickle.load(f)
                        self.ml_trained = True
            except Exception as e:
                logging.warning(f"No se pudo cargar el modelo ML: {e}")
                self.ml_model = RandomForestClassifier()
                self.ml_trained = False

    def _fetch_signal(self, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            result = get_crypto_signals(f"{symbol}USDT")
            required_keys = ["latest_price", "latest_signal", "latest_rsi", "latest_macd", "latest_atr", "latest_candle"]
            if "error" in result or not all(k in result for k in required_keys):
                logging.warning(f"Datos incompletos o error para {symbol}: {result.get('error', 'Datos faltantes')}")
                return None
            self.metrics["signals_fetched"] += 1
            return {
                "symbol": symbol,
                "timestamp": time.time(),
                "price": result["latest_price"],
                "signal": result["latest_signal"],
                "rsi": result["latest_rsi"],
                "macd": result["latest_macd"],
                "atr": result["latest_atr"],
                "candle": result["latest_candle"],
            }
        except Exception as e:
            logging.error(f"Error obteniendo datos para {symbol}: {e}")
            return None

    def run_once(self) -> None:
        if not self.wallet:
            logging.warning("No hay wallet configurada.")
            return

        # Señales en paralelo
        with ThreadPoolExecutor() as executor:
            signals = list(executor.map(self._fetch_signal, self.symbols))
        signals = [s for s in signals if s is not None]
        self.backlog.extend(signals)
        self._save_backlog()

        # Estrategias
        for strategy in self.strategies:
            for signal in signals:
                try:
                    decision = strategy.evaluate(signal)
                    if decision in ["BUY", "SELL"]:
                        res = self.wallet.place_order(f"{signal['symbol']}USDT", decision, self.quantity)
                        if not res.get("error"):
                            log_order({
                                "symbol": signal["symbol"],
                                "side": decision,
                                "quantity": self.quantity,
                                "result": res,
                                "source": "strategy",
                            }, self.orders_file, self.file_lock)
                            self.metrics["orders_placed"] += 1
                        else:
                            self.metrics["orders_failed"] += 1
                            logging.warning(f"Orden fallida para {signal['symbol']}: {res['error']}")
                except Exception as e:
                    logging.error(f"Error evaluando estrategia para {signal['symbol']}: {e}")

        # ML Training
        if not self.ml_trained and len(self.backlog) >= self.min_backlog_size and len(self.backlog) > self.last_trained_size:
            X, y = [], []
            for entry in self.backlog:
                if is_valid_features(entry):
                    X.append([entry["rsi"], entry["macd"], entry["atr"]])
                    y.append(1 if entry["signal"] == "BUY" else 0 if entry["signal"] == "SELL" else -1)
            X, y = np.array(X), np.array(y)
            mask = y != -1
            if np.any(mask):
                try:
                    self.ml_model.fit(X[mask], y[mask])
                    self.ml_trained = True
                    self.last_trained_size = len(self.backlog)
                    self._save_model()
                    logging.info("Modelo ML entrenado correctamente.")
                except Exception as e:
                    logging.error(f"Error entrenando modelo ML: {e}")

        # Predicción ML
        for signal in signals:
            if self.ml_trained and is_valid_features(signal):
                try:
                    features = np.array([[signal["rsi"], signal["macd"], signal["atr"]]])
                    pred = self.ml_model.predict(features)[0]
                    if pred in [0, 1]:
                        side = "BUY" if pred == 1 else "SELL"
                        res = self.wallet.place_order(f"{signal['symbol']}USDT", side, self.quantity)
                        if not res.get("error"):
                            log_order({
                                "symbol": signal["symbol"],
                                "side": side,
                                "quantity": self.quantity,
                                "result": res,
                                "source": "ml_model",
                            }, self.orders_file, self.file_lock)
                            self.metrics["orders_placed"] += 1
                        else:
                            self.metrics["orders_failed"] += 1
                            logging.warning(f"Orden fallida para {signal['symbol']}: {res['error']}")
                except Exception as e:
                    logging.error(f"Error en predicción ML para {signal['symbol']}: {e}")

    def run_forever(self, stop_event: Optional[threading.Event] = None) -> None:
        while True:
            self.run_once()
            if stop_event and stop_event.wait(self.interval * 60):
                break
