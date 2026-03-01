"""
Descubrimiento dinámico de tickers por mercado.

En vez de listas estáticas, obtiene los componentes de los principales
índices usando yfinance / Wikipedia / pandas. Cachea resultados para
no repetir llamadas costosas.

Índices cubiertos:
  - S&P 500       → NASDAQ + NYSE
  - IBEX 35       → IBEX
  - DAX 40        → XETRA
  - CAC 40        → EURONEXT_PARIS
  - FTSE MIB      → BORSA_ITALIANA
  - FTSE 100      → LSE
"""

import asyncio
import logging
import time
from typing import Any

from config.markets import normalize_ticker, register_ticker_market, split_yfinance_suffix

logger = logging.getLogger(__name__)

# ── Caché en memoria ────────────────────────────────────────

_cache: dict[str, tuple[list[str], float]] = {}
_CACHE_TTL = 86_400  # 24 horas


def _cache_get(key: str) -> list[str] | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    tickers, ts = entry
    if time.time() - ts > _CACHE_TTL:
        del _cache[key]
        return None
    return tickers


def _cache_set(key: str, tickers: list[str]) -> None:
    _cache[key] = (tickers, time.time())


# ── Obtención de componentes ────────────────────────────────


def _get_sp500_tickers() -> list[str]:
    """Obtiene los ~500 tickers del S&P 500 desde Wikipedia."""
    try:
        import pandas as pd
        table = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            attrs={"id": "constituents"},
        )
        if table:
            tickers = table[0]["Symbol"].tolist()
            # Normalizar: BRK.B → BRK-B
            return [t.replace(".", "-").upper() for t in tickers if isinstance(t, str)]
    except Exception as e:
        logger.warning(f"Error obteniendo S&P 500 desde Wikipedia: {e}")
    return []


def _get_ibex35_tickers() -> list[str]:
    """Obtiene los ~35 tickers del IBEX 35 desde Wikipedia."""
    try:
        import pandas as pd
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/IBEX_35",
            match="Ticker",
        )
        if tables:
            df = tables[0]
            # Buscar la columna que tenga 'Ticker' en el nombre
            for col in df.columns:
                if "ticker" in str(col).lower():
                    tickers = df[col].tolist()
                    return [str(t).upper() for t in tickers if isinstance(t, str) and len(t) <= 6]
    except Exception as e:
        logger.warning(f"Error obteniendo IBEX 35: {e}")
    return []


def _get_dax40_tickers() -> list[str]:
    """Obtiene los ~40 tickers del DAX 40 desde Wikipedia."""
    try:
        import pandas as pd
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/DAX",
            match="Ticker",
        )
        if tables:
            df = tables[0]
            for col in df.columns:
                if "ticker" in str(col).lower():
                    tickers = df[col].tolist()
                    return [str(t).upper() for t in tickers if isinstance(t, str)]
    except Exception as e:
        logger.warning(f"Error obteniendo DAX 40: {e}")
    return []


def _get_cac40_tickers() -> list[str]:
    """Obtiene los ~40 tickers del CAC 40 desde Wikipedia."""
    try:
        import pandas as pd
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/CAC_40",
            match="Ticker",
        )
        if tables:
            df = tables[0]
            for col in df.columns:
                if "ticker" in str(col).lower():
                    tickers = df[col].tolist()
                    return [str(t).upper() for t in tickers if isinstance(t, str)]
    except Exception as e:
        logger.warning(f"Error obteniendo CAC 40: {e}")
    return []


def _get_ftse_mib_tickers() -> list[str]:
    """Obtiene los ~40 tickers del FTSE MIB desde Wikipedia."""
    try:
        import pandas as pd
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/FTSE_MIB",
            match="Ticker",
        )
        if tables:
            df = tables[0]
            for col in df.columns:
                if "ticker" in str(col).lower():
                    tickers = df[col].tolist()
                    return [str(t).upper() for t in tickers if isinstance(t, str)]
    except Exception as e:
        logger.warning(f"Error obteniendo FTSE MIB: {e}")
    return []


def _get_ftse100_tickers() -> list[str]:
    """Obtiene los ~100 tickers del FTSE 100 desde Wikipedia."""
    try:
        import pandas as pd
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/FTSE_100_Index",
            match="Ticker",
        )
        if tables:
            df = tables[0]
            for col in df.columns:
                if "ticker" in str(col).lower() or "epic" in str(col).lower():
                    tickers = df[col].tolist()
                    return [str(t).upper() for t in tickers if isinstance(t, str)]
    except Exception as e:
        logger.warning(f"Error obteniendo FTSE 100: {e}")
    return []


def _get_aex25_tickers() -> list[str]:
    """Obtiene los ~25 tickers del AEX 25 desde Wikipedia."""
    try:
        import pandas as pd
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/AEX_index",
            match="Ticker",
        )
        if tables:
            df = tables[0]
            for col in df.columns:
                if "ticker" in str(col).lower():
                    tickers = df[col].tolist()
                    return [str(t).upper() for t in tickers if isinstance(t, str)]
    except Exception as e:
        logger.warning(f"Error obteniendo AEX 25: {e}")
    return []


# ── Fallback: listas estáticas mínimas ──────────────────────
# Solo se usa si la descarga de Wikipedia falla

_FALLBACK: dict[str, list[str]] = {
    "SP500": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "BRK-B",
        "JPM", "V", "JNJ", "PG", "UNH", "HD", "MA", "DIS", "KO", "XOM",
        "CVX", "PFE", "MRK", "WMT", "ABT", "TMO", "LLY", "ABBV", "CRM",
        "AVGO", "ADBE", "ORCL", "NFLX", "AMD", "INTC", "QCOM", "TXN",
        "BA", "GS", "CAT", "IBM", "HON", "NEE", "BLK", "SPGI", "DE",
    ],
    "IBEX": [
        "SAN", "BBVA", "ITX", "IBE", "TEF", "REP", "AMS", "FER",
        "CABK", "MAP", "ACS", "ENG", "GRF", "MEL", "CLNX",
        "IAG", "AENA", "CIE", "LOG", "ACX", "SAB", "PHM",
        "RED", "MRL", "SGRE", "COL", "VIS", "MTS", "ELE",
    ],
    "DAX": [
        "SAP", "SIE", "ALV", "DTE", "BAS", "AIR", "MBG", "BMW",
        "MUV2", "DPW", "ADS", "IFX", "HEN3", "DB1", "RWE", "ENR",
        "VOW3", "FRE", "BAYN", "BEI", "CON", "HEI", "MTX", "LIN",
        "SHL", "MRK", "QIA", "DTG", "PAH3", "ZAL", "PUM", "SY1",
        "1COV", "HFG", "RHM", "BNR", "LEA", "EVK", "HNR1", "TLX",
    ],
    "CAC40": [
        "AI", "AIR", "ALO", "MT", "CS", "BNP", "EN", "CAP", "SU",
        "SGO", "SAN", "DG", "BN", "EL", "ENGI", "ERF", "RMS",
        "KER", "LR", "MC", "ML", "OR", "ORA", "PUB", "RI",
        "SAF", "SGO", "STLA", "STM", "TEP", "HO", "TTE", "URW",
        "VIE", "VIV", "WLN", "DSY",
    ],
    "FTSE_MIB": [
        "ISP", "UCG", "ENI", "ENEL", "RACE", "STM", "G", "CNHI",
        "AMP", "STLA", "BAMI", "BMED", "BGN", "BPE", "BZU",
        "CPR", "DIA", "EXO", "FBK", "HER", "IGG", "INW",
        "IP", "IVG", "LDO", "MB", "MONC", "NEXI", "PIRC",
        "PRY", "PST", "REC", "SRG", "SPM", "TEN", "TIT",
        "TRN", "UNI",
    ],
    "FTSE100": [
        "SHEL", "AZN", "HSBA", "ULVR", "BP", "GSK", "RIO", "BATS",
        "DGE", "REL", "LSEG", "NGG", "VOD", "BT-A", "LLOY",
        "AAL", "ABF", "AHT", "ANTO", "AUTO", "AV", "BARC",
        "BKG", "BNZL", "CNA", "CPG", "CRDA", "EDV", "EXPN",
        "GLEN", "HL", "HSBA", "IHG", "IMB", "INF", "ITRK",
        "JD", "KGF", "LAND", "MNDI", "NWG", "PSON", "RKT",
        "RR", "SDR", "SGRO", "SKG", "SMDS", "SMT", "SN",
    ],
    "AEX": [
        "ASML", "RDSA", "INGA", "PHIA", "AD", "HEIA", "WKL",
        "DSM", "KPN", "NN", "ABN", "AKZA", "ASM", "BESI",
        "IMCD", "PRX", "RAND", "REN", "SBMO", "UNA", "URW",
        "VPK", "AGN", "ADYEN", "UMG",
    ],
}


# ── Mapeo de mercado a función de descubrimiento ────────────

# Índice principal de cada mercado para yfinance
MARKET_INDEX_MAP: dict[str, dict[str, Any]] = {
    "NASDAQ": {
        "fetch": _get_sp500_tickers,
        "fallback": "SP500",
    },
    "NYSE": {
        "fetch": _get_sp500_tickers,
        "fallback": "SP500",
    },
    "IBEX": {
        "fetch": _get_ibex35_tickers,
        "fallback": "IBEX",
    },
    "XETRA": {
        "fetch": _get_dax40_tickers,
        "fallback": "DAX",
    },
    "EURONEXT_PARIS": {
        "fetch": _get_cac40_tickers,
        "fallback": "CAC40",
    },
    "BORSA_ITALIANA": {
        "fetch": _get_ftse_mib_tickers,
        "fallback": "FTSE_MIB",
    },
    "LSE": {
        "fetch": _get_ftse100_tickers,
        "fallback": "FTSE100",
    },
    "EURONEXT_AMSTERDAM": {
        "fetch": _get_aex25_tickers,
        "fallback": "AEX",
    },
}

def _sync_get_tickers_for_market(market_key: str) -> list[str]:
    """
    Obtiene los tickers de un mercado dado.
    1. Intenta descargar dinámicamente (Wikipedia / yfinance).
    2. Si falla, usa fallback estático.
    3. Cachea resultado 24h.
    """
    cached = _cache_get(market_key)
    if cached is not None:
        return cached

    config = MARKET_INDEX_MAP.get(market_key)
    if config is None:
        logger.warning(f"Mercado {market_key} no tiene configuración de descubrimiento")
        return []

    # 1. Intentar descarga dinámica
    fetch_fn = config["fetch"]
    try:
        tickers = fetch_fn()
    except Exception as e:
        logger.warning(f"Error en descubrimiento dinámico para {market_key}: {e}")
        tickers = []

    # Normalizar tickers a formato interno (sin sufijo yfinance, sin puntos)
    if tickers:
        normalized: list[str] = []
        for t in tickers:
            if not isinstance(t, str):
                continue
            base, _inferred = split_yfinance_suffix(t)
            nt = normalize_ticker(base)
            if nt:
                normalized.append(nt)
        # Preservar orden y eliminar duplicados
        tickers = list(dict.fromkeys(normalized))

    # 2. Fallback si la descarga falló o vino vacía
    if not tickers:
        fallback_key = config.get("fallback", "")
        tickers = list(_FALLBACK.get(fallback_key, []))
        if tickers:
            logger.info(
                f"Usando fallback estático para {market_key}: {len(tickers)} tickers"
            )

    # 3. Cachear y registrar en el mapeo global ticker→mercado
    if tickers:
        _cache_set(market_key, tickers)
        for t in tickers:
            register_ticker_market(t, market_key)
        logger.info(
            f"📊 {market_key}: {len(tickers)} tickers descubiertos"
        )

    return tickers


async def get_tickers_for_market(market_key: str) -> list[str]:
    """Obtiene tickers de un mercado (async, no bloquea event loop)."""
    return await asyncio.to_thread(_sync_get_tickers_for_market, market_key)


async def get_all_available_tickers() -> dict[str, list[str]]:
    """Obtiene todos los tickers de todos los mercados configurados."""
    result: dict[str, list[str]] = {}
    for market_key in MARKET_INDEX_MAP:
        tickers = await get_tickers_for_market(market_key)
        if tickers:
            result[market_key] = tickers
    return result


def get_supported_markets() -> list[str]:
    """Devuelve los mercados con descubrimiento de tickers configurado.

    Nota: NASDAQ y NYSE comparten sufijo en yfinance. Para discovery/screening
    tratamos el universo US como uno solo (vía NASDAQ) para evitar duplicados.
    """
    markets = list(MARKET_INDEX_MAP.keys())
    if "NASDAQ" in markets and "NYSE" in markets:
        markets = [m for m in markets if m != "NYSE"]
    return markets


def invalidate_cache(market_key: str | None = None) -> None:
    """Invalida la caché de tickers. Si market_key es None, invalida todo."""
    if market_key:
        _cache.pop(market_key, None)
    else:
        _cache.clear()


# ── ETFs ─────────────────────────────────────────────────────

# Mapeamos las categorías "legacy" a las categorías canónicas de etf_config.
# El universo real vive en strategy/etf_config.py; aquí solo mantenemos la
# interfaz pública usada por /etf y la watchlist IA.

_LEGACY_CATEGORY_MAP: dict[str, list[str]] = {
    "indices_us": ["core_us"],
    "indices_eu": ["core_eu", "europe_country"],
    "indices_global": ["core_global", "emerging"],
    "sectorial": [
        "tech", "healthcare", "financials", "energy", "consumer_staples",
        "consumer_disc", "communication", "materials", "utilities",
        "industrials", "real_estate",
    ],
    "renta_fija": [
        "bonds_aggregate", "bonds_short", "bonds_intermediate",
        "bonds_long", "bonds_corporate", "bonds_high_yield",
        "bonds_tips", "bonds_intl",
    ],
    "commodities": ["gold", "commodities_broad", "silver"],
    "tematicos": ["innovation"],
}


def get_etf_tickers(categories: list[str] | None = None) -> list[str]:
    """
    Devuelve una lista de tickers ETF.
    Si se especifican categorías (legacy), mapea a las canónicas de etf_config.
    Si no, devuelve todos los ETFs conocidos.
    """
    from strategy.etf_config import get_etf_universe_for_category, get_all_etf_tickers as _all

    if categories is None:
        return sorted(_all())

    result: list[str] = []
    for cat in categories:
        canonical_cats = _LEGACY_CATEGORY_MAP.get(cat, [cat])
        for cc in canonical_cats:
            result.extend(get_etf_universe_for_category(cc))
    return list(dict.fromkeys(result))  # Preserva orden, elimina duplicados


def get_etf_categories() -> list[str]:
    """Devuelve las categorías de ETF disponibles (nombres legacy)."""
    return list(_LEGACY_CATEGORY_MAP.keys())
