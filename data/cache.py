"""
Sistema de caché en memoria con TTL para reducir llamadas redundantes
a yfinance y OpenAI.

Thread-safe: protegido con threading.Lock para accesos concurrentes
desde asyncio.to_thread().
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Una entrada de caché con timestamp de expiración."""
    value: Any
    expires_at: float  # time.monotonic()


class TTLCache:
    """Caché en memoria con TTL (Time-To-Live) por clave, thread-safe."""

    def __init__(self, default_ttl: int = 300):
        """
        Args:
            default_ttl: TTL por defecto en segundos.
        """
        self._store: dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        """Obtiene un valor del caché si no ha expirado."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if time.monotonic() > entry.expires_at:
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Almacena un valor con TTL opcional."""
        ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            self._store[key] = CacheEntry(
                value=value,
                expires_at=time.monotonic() + ttl,
            )

    def invalidate(self, key: str) -> bool:
        """Elimina una clave del caché."""
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def invalidate_prefix(self, prefix: str) -> int:
        """Elimina todas las claves que empiezan por un prefijo."""
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]
            return len(keys)

    def clear(self) -> None:
        """Limpia todo el caché."""
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def cleanup(self) -> int:
        """Elimina entradas expiradas. Devuelve cuántas se eliminaron."""
        with self._lock:
            now = time.monotonic()
            expired = [k for k, v in self._store.items() if now > v.expires_at]
            for k in expired:
                del self._store[k]
            return len(expired)

    @property
    def stats(self) -> dict[str, int | float]:
        """Estadísticas del caché."""
        with self._lock:
            return {
                "entries": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(
                    self._hits / max(self._hits + self._misses, 1) * 100, 1
                ),
            }


# ── Instancias globales ─────────────────────────────────────

# Precios: TTL corto (2 min) para datos de mercado
price_cache = TTLCache(default_ttl=120)

# Fundamentales: TTL medio (2 horas) para info de empresa
fundamentals_cache = TTLCache(default_ttl=7200)

# Ticker info: TTL medio (1 hora)
ticker_info_cache = TTLCache(default_ttl=3600)

# IA: TTL largo (24h) para respuestas de OpenAI por ticker+estrategia
ai_cache = TTLCache(default_ttl=86400)

# Noticias RSS: TTL de 30 min
news_cache = TTLCache(default_ttl=1800)


def get_all_cache_stats() -> dict[str, dict[str, int]]:
    """Devuelve estadísticas de todos los cachés."""
    return {
        "prices": price_cache.stats,
        "fundamentals": fundamentals_cache.stats,
        "ticker_info": ticker_info_cache.stats,
        "ai": ai_cache.stats,
        "news": news_cache.stats,
    }


def clear_all_caches() -> None:
    """Limpia todos los cachés."""
    price_cache.clear()
    fundamentals_cache.clear()
    ticker_info_cache.clear()
    ai_cache.clear()
    news_cache.clear()
    logger.info("🗑️ Todos los cachés limpiados")


def cleanup_all_caches() -> int:
    """Elimina entradas expiradas de todos los cachés."""
    total = 0
    total += price_cache.cleanup()
    total += fundamentals_cache.cleanup()
    total += ticker_info_cache.cleanup()
    total += ai_cache.cleanup()
    total += news_cache.cleanup()
    return total
