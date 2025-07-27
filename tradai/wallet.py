from __future__ import annotations

import json
from base64 import b64encode, b64decode
from pathlib import Path
from typing import Dict, Optional

from binance.client import Client

from .options import OPTIONS_FILE, load_options, save_options

# Backwards compatibility alias
WALLET_FILE = OPTIONS_FILE

class Wallet:
    """Interfaz base para una cartera."""

    def get_balances(self) -> Dict[str, float]:
        raise NotImplementedError

    def get_balance(self, symbol: str) -> float:
        """Devuelve el balance disponible para *symbol*."""
        return self.get_balances().get(symbol.upper(), 0.0)

    def place_order(self, symbol: str, side: str, quantity: float) -> Dict:
        raise NotImplementedError

    def balance_usdt(self) -> float:
        """Acceso rápido al balance en USDT."""
        return self.get_balance("USDT")


class DemoWallet(Wallet):
    """Cartera simple con almacenamiento local."""

    def __init__(self, balances: Optional[Dict[str, float]] = None) -> None:
        # initialize with 10k USDT so demo trades have more margin
        self.balances = balances or {"USDT": 10000.0}

    def get_balances(self) -> Dict[str, float]:
        return dict(self.balances)

    def get_balance(self, symbol: str) -> float:
        return self.balances.get(symbol.upper(), 0.0)

    def place_order(self, symbol: str, side: str, quantity: float) -> Dict:
        if side == "BUY":
            self.balances[symbol] = self.balances.get(symbol, 0.0) + quantity
            self.balances["USDT"] = self.balances.get("USDT", 0.0) - quantity
        else:
            self.balances[symbol] = self.balances.get(symbol, 0.0) - quantity
            self.balances["USDT"] = self.balances.get("USDT", 0.0) + quantity
        return {"status": "filled"}


class BinanceWallet(Wallet):
    """Implementación basada en la librería python-binance."""

    def __init__(self, api_key: str, api_secret: str) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.client = Client(api_key, api_secret)

    def get_balances(self) -> Dict[str, float]:
        account = self.client.get_account()
        balances = {
            b["asset"]: float(b["free"])
            for b in account.get("balances", [])
            if float(b.get("free", 0)) > 0
        }
        return balances

    def get_balance(self, symbol: str) -> float:
        return self.get_balances().get(symbol.upper(), 0.0)

    def place_order(self, symbol: str, side: str, quantity: float) -> Dict:
        order = self.client.create_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=quantity,
        )
        return order


def save_wallet_config(cfg: Dict) -> None:
    opts = load_options()
    opts["wallet"] = b64encode(json.dumps(cfg).encode()).decode()
    save_options(opts)


def load_wallet_config() -> Optional[Dict]:
    opts = load_options()
    data = opts.get("wallet")
    if not data:
        return None
    try:
        return json.loads(b64decode(data).decode())
    except Exception:
        return None


def wallet_from_config(cfg: Dict) -> Wallet:
    wtype = cfg.get("type")
    if wtype == "demo":
        return DemoWallet()
    if wtype == "binance":
        key = cfg.get("api_key")
        secret = cfg.get("api_secret")
        if not key or not secret:
            raise ValueError("Credenciales requeridas para Binance")
        return BinanceWallet(key, secret)
    raise ValueError("Tipo de wallet no soportado")


_wallet_cache: Wallet | None = None


def load_wallet() -> Wallet:
    """Devuelve la instancia de :class:`Wallet` configurada o una demo por defecto."""
    global _wallet_cache
    cfg = load_wallet_config() or {"type": "demo"}
    if _wallet_cache and getattr(_wallet_cache, "_cfg", None) == cfg:
        return _wallet_cache
    wallet = wallet_from_config(cfg)
    setattr(wallet, "_cfg", cfg)
    _wallet_cache = wallet
    return wallet
