"""
Configuración de asignación de ETFs por estrategia.

Define para cada estrategia:
  - Porcentaje objetivo de la cartera en ETFs
  - Categorías de ETF preferidas con pesos relativos
  - Límites de concentración por ETF individual
  - Número máximo de posiciones ETF

Los ETFs complementan la cartera de acciones. Se seleccionan
dinámicamente según la composición real del portfolio (sectores,
mercados, clases de activo) para maximizar la diversificación.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from database.models import StrategyType


@dataclass(frozen=True)
class EtfCategoryWeight:
    """Peso relativo de una categoría de ETFs dentro de la estrategia."""
    category: str          # ej: "core_equity", "bonds", "commodities"
    weight: float          # 0-1, pesos relativos dentro de la asignación ETF
    description: str = ""  # Descripción para logs/UI


@dataclass(frozen=True)
class EtfStrategyConfig:
    """Configuración completa de ETFs para una estrategia."""

    # ── Asignación global ────────────────────────────────────
    target_etf_pct: float              # % objetivo del portfolio en ETFs (0.0-1.0)
    min_etf_pct: float = 0.05          # % mínimo antes de disparar compra de ETFs
    max_etf_pct: float = 0.60          # % máximo absoluto en ETFs
    rebalance_threshold: float = 0.05  # Desviación (abs) para disparar rebalanceo

    # ── Posiciones individuales ──────────────────────────────
    max_etf_positions: int = 5         # Número máximo de ETFs distintos en cartera
    max_single_etf_pct: float = 0.10   # Concentración máxima en un solo ETF
    min_etf_amount: float = 50.0       # Monto mínimo para abrir posición ETF (USD/EUR)

    # ── Categorías con pesos ─────────────────────────────────
    categories: list[EtfCategoryWeight] = field(default_factory=list)

    @property
    def normalized_category_weights(self) -> dict[str, float]:
        """Devuelve los pesos normalizados a sumar 1.0."""
        total = sum(c.weight for c in self.categories)
        if total <= 0:
            return {}
        return {c.category: c.weight / total for c in self.categories}


# ── Universo de ETFs por categoría funcional ─────────────────
# Cada categoría agrupa ETFs de similar exposición.
# El selector dinámico filtra según el portfolio actual.

ETF_CATEGORY_UNIVERSE: dict[str, list[str]] = {
    # ── Renta variable core ──
    "core_us": ["VOO", "VTI", "SPY", "IVV", "ITOT", "IWM", "DIA"],
    "core_eu": ["VGK", "EZU", "FEZ", "IEUR"],
    "europe_country": ["EWG", "EWQ", "EWP", "EWI", "EWU"],
    "core_global": ["VT", "ACWI", "VXUS", "EFA", "VEA"],
    "emerging": ["VWO", "EEM", "IEMG", "SCHE"],

    # ── Factores / smart beta ──
    "value_factor": ["VTV", "IUSV", "RPV", "VLUE", "SPYV", "VONV", "EFV", "FNDF"],
    "growth_factor": ["VUG", "IWF", "SPYG", "SCHG", "VONG", "MGK", "EFG"],
    "quality_factor": ["QUAL", "SPHQ", "DGRW", "MOAT"],
    "low_vol": ["SPLV", "USMV", "EFAV", "ACWV"],
    "small_cap_value": ["IWN", "VBR", "SLYV", "AVUV"],
    "small_cap_growth": ["IWO", "VBK", "SLYG"],
    "dividend_growth": ["VIG", "DGRO", "NOBL", "SDY"],
    "high_dividend": ["SCHD", "VYM", "HDV", "DVY", "SPYD", "SPHD", "VYMI", "IDV"],
    "intl_dividend": ["DWX", "SDIV", "IHDG"],

    # ── Sectorial ──
    "tech": ["QQQ", "XLK", "VGT", "FTEC", "IGV", "HACK"],
    "healthcare": ["XLV", "VHT", "IBB", "IHI"],
    "financials": ["XLF", "VFH", "KRE"],
    "energy": ["XLE", "VDE", "IXC"],
    "consumer_staples": ["XLP", "VDC", "KXI"],
    "consumer_disc": ["XLY"],
    "communication": ["XLC"],
    "materials": ["XLB"],
    "utilities": ["XLU", "VPU"],
    "industrials": ["XLI", "VIS"],
    "real_estate": ["VNQ", "SCHH", "IYR", "XLRE"],
    "innovation": ["ARKK", "ARKG", "ARKW", "SOXX", "SMH", "BOTZ", "ICLN"],

    # ── Renta fija ──
    "bonds_aggregate": ["AGG", "BND", "BNDX"],
    "bonds_short": ["SHY", "SHV", "BSV", "VGSH", "BIL"],
    "bonds_intermediate": ["IEF", "VGIT"],
    "bonds_long": ["TLT", "VGLT", "EDV"],
    "bonds_corporate": ["LQD", "VCIT", "VCSH"],
    "bonds_high_yield": ["HYG", "JNK", "SHYG"],
    "bonds_tips": ["TIP", "SCHP", "VTIP"],
    "bonds_intl": ["BNDX", "IAGG", "EMB"],

    # ── Multi-asset ──
    "multi_asset": ["AOR", "AOA"],

    # ── Commodities / alternativas ──
    "gold": ["GLD", "IAU", "SGOL"],
    "commodities_broad": ["DBC", "PDBC", "GSG", "USO", "DBA"],
    "silver": ["SLV"],
}


# ── Configuración por estrategia ─────────────────────────────

_STRATEGY_ETF_CONFIGS: dict[StrategyType, EtfStrategyConfig] = {

    StrategyType.VALUE: EtfStrategyConfig(
        target_etf_pct=0.20,   # 20% en ETFs
        max_etf_positions=4,
        max_single_etf_pct=0.08,
        categories=[
            EtfCategoryWeight("value_factor", 0.30, "Factor value para reforzar estilo"),
            EtfCategoryWeight("dividend_growth", 0.20, "Dividendos crecientes como colchón"),
            EtfCategoryWeight("core_global", 0.15, "Diversificación geográfica"),
            EtfCategoryWeight("small_cap_value", 0.15, "Small caps value para alpha"),
            EtfCategoryWeight("bonds_corporate", 0.10, "Renta fija corporativa"),
            EtfCategoryWeight("gold", 0.10, "Cobertura contra inflación"),
        ],
    ),

    StrategyType.GROWTH: EtfStrategyConfig(
        target_etf_pct=0.15,   # 15% en ETFs (más peso en acciones individuales)
        max_etf_positions=4,
        max_single_etf_pct=0.08,
        categories=[
            EtfCategoryWeight("growth_factor", 0.25, "Factor growth amplio"),
            EtfCategoryWeight("tech", 0.25, "Tecnología / QQQ"),
            EtfCategoryWeight("innovation", 0.20, "Innovación disruptiva"),
            EtfCategoryWeight("emerging", 0.15, "Mercados emergentes (crecimiento)"),
            EtfCategoryWeight("small_cap_growth", 0.15, "Small caps growth"),
        ],
    ),

    StrategyType.DIVIDEND: EtfStrategyConfig(
        target_etf_pct=0.30,   # 30% en ETFs (income + diversificación)
        max_etf_positions=6,
        max_single_etf_pct=0.10,
        categories=[
            EtfCategoryWeight("high_dividend", 0.25, "Alto dividendo"),
            EtfCategoryWeight("dividend_growth", 0.20, "Crecimiento de dividendo"),
            EtfCategoryWeight("real_estate", 0.15, "REITs para income"),
            EtfCategoryWeight("bonds_aggregate", 0.15, "Bonos agregados"),
            EtfCategoryWeight("bonds_high_yield", 0.10, "High yield para income"),
            EtfCategoryWeight("bonds_intl", 0.10, "Deuda internacional"),
            EtfCategoryWeight("gold", 0.05, "Cobertura"),
        ],
    ),

    StrategyType.BALANCED: EtfStrategyConfig(
        target_etf_pct=0.25,   # 25% en ETFs
        max_etf_positions=5,
        max_single_etf_pct=0.08,
        categories=[
            EtfCategoryWeight("core_us", 0.20, "Core renta variable US"),
            EtfCategoryWeight("core_global", 0.15, "Diversificación global"),
            EtfCategoryWeight("quality_factor", 0.15, "Factor calidad"),
            EtfCategoryWeight("bonds_aggregate", 0.15, "Bonos agregados"),
            EtfCategoryWeight("bonds_corporate", 0.10, "Renta fija corporativa"),
            EtfCategoryWeight("real_estate", 0.10, "REITs"),
            EtfCategoryWeight("gold", 0.10, "Cobertura gold"),
            EtfCategoryWeight("emerging", 0.05, "Emergentes"),
        ],
    ),

    StrategyType.CONSERVATIVE: EtfStrategyConfig(
        target_etf_pct=0.40,   # 40% en ETFs (máxima diversificación/estabilidad)
        max_etf_positions=6,
        max_single_etf_pct=0.10,
        categories=[
            EtfCategoryWeight("bonds_short", 0.20, "Bonos corto plazo (baja duración)"),
            EtfCategoryWeight("bonds_aggregate", 0.15, "Bonos agregados"),
            EtfCategoryWeight("bonds_tips", 0.10, "Protección contra inflación"),
            EtfCategoryWeight("low_vol", 0.15, "Baja volatilidad"),
            EtfCategoryWeight("consumer_staples", 0.10, "Consumo básico defensivo"),
            EtfCategoryWeight("utilities", 0.05, "Utilities defensivas"),
            EtfCategoryWeight("gold", 0.15, "Cobertura/refugio"),
            EtfCategoryWeight("core_us", 0.10, "Core equity defensivo"),
        ],
    ),
}


def get_etf_config(strategy: StrategyType | str | None) -> EtfStrategyConfig:
    """Devuelve la configuración de ETFs para una estrategia."""
    from strategy.selector import normalize_strategy
    st = normalize_strategy(strategy)
    return _STRATEGY_ETF_CONFIGS.get(st, _STRATEGY_ETF_CONFIGS[StrategyType.VALUE])


def get_etf_universe_for_category(category: str) -> list[str]:
    """Devuelve los tickers ETF de una categoría."""
    return list(ETF_CATEGORY_UNIVERSE.get(category, []))


def get_all_etf_tickers() -> set[str]:
    """Devuelve todos los tickers ETF del universo (sin duplicados, como set para O(1) lookup)."""
    result: set[str] = set()
    for tickers in ETF_CATEGORY_UNIVERSE.values():
        result.update(tickers)
    return result


def get_etf_category_for_ticker(ticker: str) -> str | None:
    """Devuelve la categoría de un ticker ETF, o None si no está en el universo."""
    ticker = ticker.upper()
    for cat, tickers in ETF_CATEGORY_UNIVERSE.items():
        if ticker in tickers:
            return cat
    return None
