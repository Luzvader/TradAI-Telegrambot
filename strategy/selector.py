"""
Selector de estrategias.

Centraliza el routing de StrategyType -> función analyze_* para mantener
el resto del código simple y desacoplado.
"""

from __future__ import annotations

from collections.abc import Callable

from data.fundamentals import FundamentalData
from database.models import StrategyType
from strategy.score import StrategyScore

Analyzer = Callable[[FundamentalData], StrategyScore]


def normalize_strategy(strategy: StrategyType | str | None) -> StrategyType:
    if isinstance(strategy, StrategyType):
        return strategy

    if not strategy:
        return StrategyType.VALUE

    name = str(strategy).strip().lower()
    for st in StrategyType:
        if st.value == name:
            return st
    return StrategyType.VALUE


def get_strategy_analyzer(strategy: StrategyType | str | None) -> Analyzer:
    st = normalize_strategy(strategy)

    # Imports locales para evitar ciclos y coste al importar el paquete.
    from strategy.value_strategy import analyze_value
    from strategy.growth_strategy import analyze_growth
    from strategy.dividend_strategy import analyze_dividend
    from strategy.balanced_strategy import analyze_balanced
    from strategy.conservative_strategy import analyze_conservative

    analyzers: dict[StrategyType, Analyzer] = {
        StrategyType.VALUE: analyze_value,
        StrategyType.GROWTH: analyze_growth,
        StrategyType.DIVIDEND: analyze_dividend,
        StrategyType.BALANCED: analyze_balanced,
        StrategyType.CONSERVATIVE: analyze_conservative,
    }

    return analyzers.get(st, analyze_value)


def analyze_fundamentals(
    fd: FundamentalData, strategy: StrategyType | str | None
) -> StrategyScore:
    """Conveniencia: analiza directamente con una estrategia."""
    analyzer = get_strategy_analyzer(strategy)
    return analyzer(fd)

