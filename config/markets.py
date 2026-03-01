"""
Horarios de mercado y mapeo de tickers a mercados.
Todos los horarios están en la zona horaria local del mercado.
"""

import logging
from dataclasses import dataclass
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# ── Definición de mercados ──────────────────────────────────


@dataclass(frozen=True)
class MarketSchedule:
    """Horario de un mercado."""
    name: str
    timezone: str
    open_hour: int
    open_minute: int
    close_hour: int
    close_minute: int
    # Días de la semana (0=lunes … 4=viernes)
    trading_days: tuple[int, ...] = (0, 1, 2, 3, 4)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


# Mercados soportados
MARKETS: dict[str, MarketSchedule] = {
    "NASDAQ": MarketSchedule(
        name="NASDAQ",
        timezone="America/New_York",
        open_hour=9,
        open_minute=30,
        close_hour=16,
        close_minute=0,
    ),
    "NYSE": MarketSchedule(
        name="NYSE",
        timezone="America/New_York",
        open_hour=9,
        open_minute=30,
        close_hour=16,
        close_minute=0,
    ),
    "IBEX": MarketSchedule(
        name="IBEX 35",
        timezone="Europe/Madrid",
        open_hour=9,
        open_minute=0,
        close_hour=17,
        close_minute=30,
    ),
    "LSE": MarketSchedule(
        name="London Stock Exchange",
        timezone="Europe/London",
        open_hour=8,
        open_minute=0,
        close_hour=16,
        close_minute=30,
    ),
    "XETRA": MarketSchedule(
        name="XETRA / DAX (Frankfurt)",
        timezone="Europe/Berlin",
        open_hour=9,
        open_minute=0,
        close_hour=17,
        close_minute=30,
    ),
    "EURONEXT_PARIS": MarketSchedule(
        name="Euronext Paris (CAC 40)",
        timezone="Europe/Paris",
        open_hour=9,
        open_minute=0,
        close_hour=17,
        close_minute=30,
    ),
    "BORSA_ITALIANA": MarketSchedule(
        name="Borsa Italiana (FTSE MIB)",
        timezone="Europe/Rome",
        open_hour=9,
        open_minute=0,
        close_hour=17,
        close_minute=30,
    ),
    "EURONEXT_AMSTERDAM": MarketSchedule(
        name="Euronext Amsterdam (AEX)",
        timezone="Europe/Amsterdam",
        open_hour=9,
        open_minute=0,
        close_hour=17,
        close_minute=30,
    ),
}

# Moneda por defecto de cada mercado
MARKET_CURRENCY: dict[str, str] = {
    "NASDAQ": "USD",
    "NYSE": "USD",
    "IBEX": "EUR",
    "LSE": "GBp",  # London cotiza en peniques (GBp)
    "XETRA": "EUR",
    "EURONEXT_PARIS": "EUR",
    "BORSA_ITALIANA": "EUR",
    "EURONEXT_AMSTERDAM": "EUR",
    "OMX_COPENHAGEN": "DKK",
    "OMX_STOCKHOLM": "SEK",
    "OMX_HELSINKI": "EUR",
    "OSLO_BORS": "NOK",
    "SIX_SWISS": "CHF",
    "WIENER_BORSE": "EUR",
    "EURONEXT_BRUSSELS": "EUR",
    "EURONEXT_LISBON": "EUR",
    "ISE_DUBLIN": "EUR",
    "WSE_WARSAW": "PLN",
    "TSX_TORONTO": "CAD",
    "ASX_AUSTRALIA": "AUD",
    "HKEX": "HKD",
    "TSE_TOKYO": "JPY",
}

# Símbolo de moneda para display
CURRENCY_SYMBOL: dict[str, str] = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "GBp": "p",  # Peniques británicos
    "CHF": "CHF",
    "DKK": "DKK",
    "SEK": "SEK",
    "NOK": "NOK",
    "PLN": "PLN",
    "CAD": "CA$",
    "AUD": "A$",
    "HKD": "HK$",
    "JPY": "¥",
}


def get_currency_symbol(currency: str | None) -> str:
    """Devuelve el símbolo de moneda para display."""
    if not currency:
        return "$"
    return CURRENCY_SYMBOL.get(currency, currency)


def format_price(price: float | None, currency: str | None = None) -> str:
    """Formatea un precio con su símbolo de moneda.

    Para GBp (peniques) no muestra decimales.
    Para JPY no muestra decimales.
    Para el resto, 2 decimales.
    """
    if price is None:
        return "N/D"
    sym = get_currency_symbol(currency)
    if currency in ("GBp", "JPY"):
        return f"{price:.0f}{sym}"
    # Símbolo al final para EUR y monedas europeas, al inicio para USD/etc.
    if currency in ("EUR",):
        return f"{price:.2f}{sym}"
    return f"{price:.2f}{sym}"


# Nombres cortos para mostrar en UI (Telegram, web, etc.)
MARKET_DISPLAY_NAME: dict[str, str] = {
    "NASDAQ": "NASDAQ",
    "NYSE": "NYSE",
    "IBEX": "IBEX",
    "LSE": "LSE",
    "XETRA": "XETRA",
    "EURONEXT_PARIS": "Euronext Paris",
    "BORSA_ITALIANA": "Borsa Italiana",
    "EURONEXT_AMSTERDAM": "Euronext Amsterdam",
    "OMX_COPENHAGEN": "OMX Copenhagen",
    "OMX_STOCKHOLM": "OMX Stockholm",
    "OMX_HELSINKI": "OMX Helsinki",
    "OSLO_BORS": "Oslo Børs",
    "SIX_SWISS": "SIX Swiss",
    "WIENER_BORSE": "Wiener Börse",
    "EURONEXT_BRUSSELS": "Euronext Brussels",
    "EURONEXT_LISBON": "Euronext Lisbon",
    "ISE_DUBLIN": "ISE Dublin",
    "WSE_WARSAW": "WSE Warsaw",
    "TSX_TORONTO": "TSX",
    "ASX_AUSTRALIA": "ASX",
    "HKEX": "HKEX",
    "TSE_TOKYO": "TSE Tokyo",
}


def market_display(market: str) -> str:
    """Devuelve el nombre bonito de un mercado para mostrar en mensajes."""
    return MARKET_DISPLAY_NAME.get(market, market.replace("_", " "))

# Sufijos de yfinance por mercado
YFINANCE_SUFFIX: dict[str, str] = {
    "NASDAQ": "",
    "NYSE": "",
    "IBEX": ".MC",
    "LSE": ".L",
    "XETRA": ".DE",
    "EURONEXT_PARIS": ".PA",
    "BORSA_ITALIANA": ".MI",
    "EURONEXT_AMSTERDAM": ".AS",
    "OMX_COPENHAGEN": ".CO",
    "OMX_STOCKHOLM": ".ST",
    "OMX_HELSINKI": ".HE",
    "OSLO_BORS": ".OL",
    "SIX_SWISS": ".SW",
    "WIENER_BORSE": ".VI",
    "EURONEXT_BRUSSELS": ".BR",
    "EURONEXT_LISBON": ".LS",
    "ISE_DUBLIN": ".IR",
    "WSE_WARSAW": ".WA",
    "TSX_TORONTO": ".TO",
    "ASX_AUSTRALIA": ".AX",
    "HKEX": ".HK",
    "TSE_TOKYO": ".T",
}

# Reverse mapping para inferir mercado desde un ticker con sufijo yfinance.
# Nota: NASDAQ/NYSE comparten sufijo vacío y no se pueden inferir por sufijo.
_SUFFIX_TO_MARKET: dict[str, str] = {
    suffix: market for market, suffix in YFINANCE_SUFFIX.items() if suffix
}
_KNOWN_YFINANCE_SUFFIXES: tuple[str, ...] = tuple(sorted(_SUFFIX_TO_MARKET.keys()))

# Mapeo estático mínimo de tickers conocidos a mercados.
# Sirve como fallback cuando no se puede determinar el mercado
# dinámicamente. El descubrimiento real de tickers se hace
# en data/ticker_discovery.py a partir de los índices.
DEFAULT_TICKER_MARKET: dict[str, str] = {
    # US – NASDAQ (referencia rápida)
    "AAPL": "NASDAQ", "MSFT": "NASDAQ", "GOOGL": "NASDAQ", "AMZN": "NASDAQ",
    "META": "NASDAQ", "NVDA": "NASDAQ", "TSLA": "NASDAQ", "NFLX": "NASDAQ",
    "AMD": "NASDAQ", "INTC": "NASDAQ", "AVGO": "NASDAQ", "ADBE": "NASDAQ",
    "CRM": "NASDAQ", "ORCL": "NASDAQ", "CSCO": "NASDAQ", "QCOM": "NASDAQ",
    # US – NYSE (referencia rápida)
    "JPM": "NYSE", "V": "NYSE", "JNJ": "NYSE", "PG": "NYSE",
    "UNH": "NYSE", "HD": "NYSE", "DIS": "NYSE", "KO": "NYSE",
    "BRK-B": "NYSE", "XOM": "NYSE", "BA": "NYSE", "GS": "NYSE",
    # España – IBEX
    "SAN": "IBEX", "BBVA": "IBEX", "ITX": "IBEX", "IBE": "IBEX",
    "TEF": "IBEX", "REP": "IBEX",
    # Alemania – XETRA / DAX
    "SAP": "XETRA", "SIE": "XETRA", "ALV": "XETRA", "DTE": "XETRA",
    "BAS": "XETRA", "MBG": "XETRA", "BMW": "XETRA",
    # Francia – Euronext Paris
    "MC": "EURONEXT_PARIS", "OR": "EURONEXT_PARIS", "TTE": "EURONEXT_PARIS",
    "AI": "EURONEXT_PARIS", "BNP": "EURONEXT_PARIS",
    # Italia – Borsa Italiana
    "ISP": "BORSA_ITALIANA", "UCG": "BORSA_ITALIANA", "ENI": "BORSA_ITALIANA",
    "ENEL": "BORSA_ITALIANA", "RACE": "BORSA_ITALIANA",
    # UK – LSE
    "SHEL": "LSE", "AZN": "LSE", "HSBA": "LSE", "BP": "LSE",
    # Países Bajos – Euronext Amsterdam
    "ASML": "EURONEXT_AMSTERDAM", "RDSA": "EURONEXT_AMSTERDAM",
    "INGA": "EURONEXT_AMSTERDAM", "PHIA": "EURONEXT_AMSTERDAM",
    "AD": "EURONEXT_AMSTERDAM",
}


def register_ticker_market(ticker: str, market: str) -> None:
    """Registra un ticker-mercado en el mapeo en memoria."""
    key = normalize_ticker(ticker)
    existing = DEFAULT_TICKER_MARKET.get(key)
    if existing and existing != market:
        # Evitar sobreescribir tickers ambiguos (ej. SAN en IBEX y EURONEXT).
        logger.debug(
            "register_ticker_market: conflicto %s (%s vs %s); manteniendo %s",
            key, existing, market, existing,
        )
        return
    DEFAULT_TICKER_MARKET[key] = market


def split_yfinance_suffix(ticker: str) -> tuple[str, str | None]:
    """Divide un ticker con sufijo yfinance conocido y devuelve (base, market)."""
    t = (ticker or "").strip().upper()
    for suf, mkt in _SUFFIX_TO_MARKET.items():
        if t.endswith(suf) and len(t) > len(suf):
            base = t[: -len(suf)]
            return base, mkt
    return t, None


def normalize_ticker(ticker: str) -> str:
    """Normaliza un ticker: convierte puntos a guiones (formato yfinance).

    Ejemplos: BRK.B → BRK-B, BF.B → BF-B
    """
    t = (ticker or "").strip().upper()
    # Si el usuario ya pasó un ticker con sufijo yfinance (ej. SAN.MC),
    # no debemos reemplazar el punto por guion.
    for suf in _KNOWN_YFINANCE_SUFFIXES:
        if t.endswith(suf) and len(t) > len(suf):
            return t
    return t.replace(".", "-")


def get_yfinance_ticker(ticker: str, market: str | None = None) -> str:
    """Devuelve el ticker con el sufijo correcto para yfinance."""
    raw = (ticker or "").strip().upper()
    base, inferred_market = split_yfinance_suffix(raw)
    normalized = normalize_ticker(base)
    if market is None:
        market = inferred_market or DEFAULT_TICKER_MARKET.get(normalized, "NASDAQ")
    suffix = YFINANCE_SUFFIX.get(market, "")
    return f"{normalized}{suffix}"
