"""
Selector dinámico de ETFs basado en la composición real del portfolio.

A diferencia de la watchlist estática, este módulo:
  1. Analiza qué sectores, mercados y clases de activo tiene la cartera.
  2. Identifica huecos de diversificación y sobreexposiciones.
  3. Puntúa cada ETF candidato según lo bien que complementa el portfolio.
  4. Devuelve los mejores ETFs para alcanzar el % objetivo de la estrategia.

La selección se adapta dinámicamente tanto a compras automáticas como
manuales del usuario, dando así flexibilidad y adaptabilidad real.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from config.markets import MARKET_CURRENCY
from config.settings import YFINANCE_MAX_CONCURRENCY
from data.fundamentals import fetch_fundamentals
from database import repository as repo
from database.models import AssetType, Position, PortfolioType, StrategyType
from strategy.etf_config import (
    ETF_CATEGORY_UNIVERSE,
    EtfStrategyConfig,
    get_etf_category_for_ticker,
    get_etf_config,
)

logger = logging.getLogger(__name__)


# ── Análisis del portfolio ────────────────────────────────────


@dataclass
class PortfolioProfile:
    """Perfil del portfolio actual para guiar la selección de ETFs."""

    # Exposición sectorial: sector -> % del portfolio
    sector_weights: dict[str, float] = field(default_factory=dict)
    # Exposición por mercado/región: market -> %
    market_weights: dict[str, float] = field(default_factory=dict)
    # Tickers actuales (stocks)
    stock_tickers: list[str] = field(default_factory=list)
    # Tickers ETF actuales
    etf_tickers: list[str] = field(default_factory=list)
    # Categorías ETF ya cubiertas (con su peso)
    etf_category_weights: dict[str, float] = field(default_factory=dict)
    # Valor total y splits
    total_value: float = 0.0
    stock_value: float = 0.0
    etf_value: float = 0.0
    cash: float = 0.0

    @property
    def current_etf_pct(self) -> float:
        """Porcentaje actual de la cartera en ETFs."""
        if self.total_value <= 0:
            return 0.0
        return self.etf_value / self.total_value

    @property
    def current_stock_pct(self) -> float:
        """Porcentaje actual de la cartera en acciones."""
        if self.total_value <= 0:
            return 0.0
        return self.stock_value / self.total_value

    @property
    def top_sectors(self) -> list[str]:
        """Top 3 sectores con más peso."""
        sorted_sectors = sorted(
            self.sector_weights.items(), key=lambda x: x[1], reverse=True
        )
        return [s[0] for s in sorted_sectors[:3]]

    @property
    def underweight_regions(self) -> list[str]:
        """Regiones con poca o nula exposición."""
        all_regions = {"US", "EU", "UK", "EM", "ASIA"}
        market_to_region = {
            "NASDAQ": "US", "NYSE": "US",
            "IBEX": "EU", "XETRA": "EU", "EURONEXT_PARIS": "EU",
            "BORSA_ITALIANA": "EU", "EURONEXT_AMSTERDAM": "EU",
            "LSE": "UK",
        }
        covered = set()
        for market in self.market_weights:
            region = market_to_region.get(market, "OTHER")
            if self.market_weights[market] > 0.05:
                covered.add(region)
        return list(all_regions - covered)


async def analyze_portfolio(portfolio_id: int) -> PortfolioProfile:
    """Analiza la composición actual del portfolio para guiar la selección de ETFs."""
    positions = list(await repo.get_open_positions(portfolio_id))
    portfolio = await repo.get_portfolio(portfolio_id)

    profile = PortfolioProfile()
    profile.cash = portfolio.cash if portfolio else 0.0

    if not positions:
        return profile

    # Calcular valores
    for pos in positions:
        value = (pos.current_price or pos.avg_price) * pos.shares
        is_etf = _is_etf_position(pos)

        if is_etf:
            profile.etf_value += value
            profile.etf_tickers.append(pos.ticker)
            cat = get_etf_category_for_ticker(pos.ticker)
            if cat:
                profile.etf_category_weights[cat] = (
                    profile.etf_category_weights.get(cat, 0) + value
                )
        else:
            profile.stock_value += value
            profile.stock_tickers.append(pos.ticker)

        # Sectores (solo stocks, ETFs no se asignan a sector individual)
        if not is_etf and pos.sector:
            sector = pos.sector
            profile.sector_weights[sector] = (
                profile.sector_weights.get(sector, 0) + value
            )

        # Mercados
        market = pos.market or "NASDAQ"
        profile.market_weights[market] = (
            profile.market_weights.get(market, 0) + value
        )

    profile.total_value = profile.stock_value + profile.etf_value + profile.cash

    # Normalizar a porcentajes
    if profile.total_value > 0:
        for sector in profile.sector_weights:
            profile.sector_weights[sector] /= profile.total_value
        for market in profile.market_weights:
            profile.market_weights[market] /= profile.total_value
        for cat in profile.etf_category_weights:
            profile.etf_category_weights[cat] /= profile.total_value

    return profile


def _is_etf_position(pos: Position) -> bool:
    """Determina si una posición es un ETF.

    Usa el campo asset_type si existe; si no, compara contra el universo ETF.
    """
    if hasattr(pos, "asset_type") and pos.asset_type is not None:
        return pos.asset_type == AssetType.ETF

    # Fallback: comprobar contra el universo conocido
    ticker = pos.ticker.upper()
    for tickers in ETF_CATEGORY_UNIVERSE.values():
        if ticker in tickers:
            return True
    return False


# ── Scoring de ETFs candidatos ────────────────────────────────


@dataclass
class EtfCandidate:
    """Candidato a ETF con su puntuación de idoneidad."""
    ticker: str
    category: str
    score: float = 0.0           # 0-100 puntuación de idoneidad
    category_target_weight: float = 0.0  # Peso objetivo de su categoría
    complementarity: float = 0.0  # Qué tan bien complementa el portfolio
    price: float | None = None
    expense_ratio: float | None = None
    name: str | None = None
    reasoning: list[str] = field(default_factory=list)


def _score_etf_for_portfolio(
    ticker: str,
    category: str,
    profile: PortfolioProfile,
    config: EtfStrategyConfig,
) -> EtfCandidate:
    """Puntúa un ETF candidato según lo bien que complementa el portfolio.

    Factores de scoring:
    1. Peso de la categoría en la estrategia (30%)
    2. Complementariedad: cubrir huecos del portfolio (35%)
    3. No duplicar exposición ya existente (20%)
    4. Diversificación regional (15%)
    """
    candidate = EtfCandidate(ticker=ticker, category=category)
    cat_weights = config.normalized_category_weights
    reasons: list[str] = []

    # ── 1. Peso de la categoría en la estrategia (30 pts máx) ──
    cat_weight = cat_weights.get(category, 0.0)
    candidate.category_target_weight = cat_weight
    category_score = cat_weight * 100 * 0.30  # Máx 30 si es la categoría top
    if cat_weight > 0:
        reasons.append(f"Categoría '{category}' peso={cat_weight:.0%} en estrategia")

    # ── 2. Complementariedad sectorial (35 pts máx) ──
    complementarity_score = 0.0

    # Mapeo categoría ETF -> sectores que cubre
    sector_coverage = _get_category_sector_coverage(category)

    if sector_coverage:
        # Si el portfolio tiene sobreexposición en los mismos sectores, penalizar
        overlap = sum(
            profile.sector_weights.get(s, 0) for s in sector_coverage
        )
        if overlap > 0.25:
            # Portfolio ya muy expuesto a estos sectores
            complementarity_score = 5.0
            reasons.append(f"Solapamiento sectorial alto ({overlap:.0%})")
        elif overlap > 0.10:
            complementarity_score = 15.0
            reasons.append(f"Solapamiento sectorial moderado ({overlap:.0%})")
        else:
            # Gran complementariedad: cubre sectores nuevos
            complementarity_score = 35.0
            reasons.append(f"Aporta exposición a sectores nuevos ({', '.join(sector_coverage[:3])})")
    else:
        # Categorías genéricas (bonds, gold) siempre complementan
        if _is_non_equity_category(category):
            complementarity_score = 30.0
            reasons.append("Clase de activo distinta (no renta variable)")
        else:
            complementarity_score = 20.0

    # ── 3. No duplicar ETFs existentes (20 pts máx) ──
    duplication_score = 20.0  # Empieza con puntuación máxima
    if category in profile.etf_category_weights:
        existing_weight = profile.etf_category_weights[category]
        if existing_weight > 0.05:
            duplication_score = 0.0
            reasons.append(f"⚠️ Categoría ya cubierta ({existing_weight:.1%})")
        elif existing_weight > 0.02:
            duplication_score = 8.0
            reasons.append(f"Categoría parcialmente cubierta ({existing_weight:.1%})")
    if ticker in profile.etf_tickers:
        duplication_score = 0.0
        reasons.append("⚠️ Ticker ya en cartera")

    # ── 4. Diversificación regional (15 pts máx) ──
    regional_score = 0.0
    underweight = profile.underweight_regions
    category_regions = _get_category_regions(category)

    if category_regions and any(r in underweight for r in category_regions):
        regional_score = 15.0
        matching = [r for r in category_regions if r in underweight]
        reasons.append(f"Aporta exposición a regiones infraponderadas: {', '.join(matching)}")
    elif not category_regions:
        regional_score = 8.0  # Neutral (ej: bonds, gold)
    else:
        regional_score = 5.0  # Ya hay exposición regional

    # ── Total ──
    total = category_score + complementarity_score + duplication_score + regional_score
    candidate.score = min(100.0, max(0.0, total))
    candidate.complementarity = complementarity_score / 35.0  # Normalizar 0-1
    candidate.reasoning = reasons

    return candidate


def _get_category_sector_coverage(category: str) -> list[str]:
    """Mapea una categoría ETF a los sectores que cubre."""
    mapping = {
        "tech": ["Technology"],
        "healthcare": ["Healthcare"],
        "financials": ["Financial Services"],
        "energy": ["Energy"],
        "consumer_staples": ["Consumer Defensive"],
        "utilities": ["Utilities"],
        "industrials": ["Industrials"],
        "real_estate": ["Real Estate"],
        "innovation": ["Technology", "Communication Services"],
    }
    return mapping.get(category, [])


def _get_category_regions(category: str) -> list[str]:
    """Mapea una categoría ETF a las regiones geográficas que cubre."""
    mapping = {
        "core_us": ["US"],
        "core_eu": ["EU"],
        "core_global": ["US", "EU", "UK", "EM", "ASIA"],
        "emerging": ["EM", "ASIA"],
        "value_factor": ["US"],
        "growth_factor": ["US"],
        "quality_factor": ["US"],
        "low_vol": ["US", "EU"],
        "small_cap_value": ["US"],
        "small_cap_growth": ["US"],
        "dividend_growth": ["US"],
        "high_dividend": ["US"],
        "tech": ["US"],
        "healthcare": ["US"],
        "financials": ["US"],
        "energy": ["US", "EU"],
        "consumer_staples": ["US"],
        "utilities": ["US"],
        "industrials": ["US"],
        "real_estate": ["US"],
        "innovation": ["US"],
        "bonds_intl": ["EU", "EM"],
    }
    return mapping.get(category, [])


def _is_non_equity_category(category: str) -> bool:
    """Devuelve True si la categoría no es renta variable."""
    non_equity = {
        "bonds_aggregate", "bonds_short", "bonds_intermediate",
        "bonds_long", "bonds_corporate", "bonds_high_yield",
        "bonds_tips", "bonds_intl", "multi_asset",
        "gold", "silver", "commodities_broad",
    }
    return category in non_equity


# ── Selección dinámica principal ──────────────────────────────


async def select_etfs_for_portfolio(
    portfolio_id: int,
    strategy: StrategyType | str | None = None,
    max_results: int | None = None,
) -> list[EtfCandidate]:
    """
    Selecciona dinámicamente los mejores ETFs para el portfolio actual.

    1. Analiza el perfil del portfolio (sectores, mercados, ETFs existentes).
    2. Determina la configuración ETF de la estrategia activa.
    3. Puntúa todos los ETFs candidatos por complementariedad.
    4. Devuelve los best-fit ordenados por score.

    La selección se adapta a compras automáticas Y manuales del usuario.
    """

    # Resolver estrategia
    if strategy is None:
        portfolio = await repo.get_portfolio(portfolio_id)
        strategy = portfolio.strategy if portfolio and portfolio.strategy else StrategyType.VALUE

    from strategy.selector import normalize_strategy
    st = normalize_strategy(strategy)
    config = get_etf_config(st)

    if max_results is None:
        max_results = config.max_etf_positions

    # ── 1. Analizar portfolio actual ──
    profile = await analyze_portfolio(portfolio_id)

    logger.info(
        f"📊 Portfolio profile: stocks={profile.current_stock_pct:.0%}, "
        f"ETFs={profile.current_etf_pct:.0%}, "
        f"target ETFs={config.target_etf_pct:.0%}, "
        f"sectors={len(profile.sector_weights)}, "
        f"underweight regions={profile.underweight_regions}"
    )

    # ── 2. Generar y puntuar candidatos ──
    candidates: list[EtfCandidate] = []
    cat_weights = config.normalized_category_weights

    for cat_cfg in config.categories:
        category = cat_cfg.category
        etf_tickers = ETF_CATEGORY_UNIVERSE.get(category, [])

        for ticker in etf_tickers:
            if ticker in profile.etf_tickers:
                continue  # Ya en cartera
            candidate = _score_etf_for_portfolio(ticker, category, profile, config)
            candidates.append(candidate)

    # ── 3. Enriquecer con datos de mercado (precio, nombre) ──
    candidates = await _enrich_candidates(candidates)

    # ── 4. Ordenar por score y seleccionar ──
    candidates.sort(key=lambda c: c.score, reverse=True)

    # Asegurar diversificación: máximo 1 ETF por categoría en el top
    selected: list[EtfCandidate] = []
    used_categories: set[str] = set()

    for c in candidates:
        if len(selected) >= max_results:
            break
        # Si ya seleccionamos un ETF de esta categoría, saltar
        # (a menos que la categoría ya esté en el portfolio)
        if c.category in used_categories and c.category not in profile.etf_category_weights:
            continue
        if c.price is None or c.price <= 0:
            continue  # Sin datos de precio
        selected.append(c)
        used_categories.add(c.category)

    logger.info(
        f"📦 ETF selection: {len(selected)} ETFs seleccionados de "
        f"{len(candidates)} candidatos para estrategia {st.value}"
    )
    for c in selected:
        logger.info(
            f"  → {c.ticker} ({c.category}): score={c.score:.0f}, "
            f"complementarity={c.complementarity:.0%}"
        )

    return selected


async def _enrich_candidates(
    candidates: list[EtfCandidate],
) -> list[EtfCandidate]:
    """Enriquece los candidatos con datos de mercado (precio, nombre, etc.)."""
    sem = asyncio.Semaphore(max(1, int(YFINANCE_MAX_CONCURRENCY)))

    async def _fetch_one(candidate: EtfCandidate) -> EtfCandidate:
        try:
            async with sem:
                fd = await asyncio.to_thread(
                    fetch_fundamentals, candidate.ticker, "NASDAQ"
                )
                candidate.price = fd.current_price
                candidate.name = fd.name
                if hasattr(fd, "expense_ratio") and fd.expense_ratio is not None:
                    candidate.expense_ratio = fd.expense_ratio
        except Exception as e:
            logger.debug(f"Error fetching ETF {candidate.ticker}: {e}")
        return candidate

    results = await asyncio.gather(*[_fetch_one(c) for c in candidates])
    return list(results)


# ── Cálculo de asignación óptima ──────────────────────────────


@dataclass
class EtfAllocationPlan:
    """Plan de asignación de ETFs para el portfolio."""
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    current_etf_pct: float = 0.0
    target_etf_pct: float = 0.0
    gap_pct: float = 0.0             # target - current (positivo = subponderado)
    total_amount_to_invest: float = 0.0  # Monto total a invertir en ETFs
    rebalance_needed: bool = False
    summary: str = ""


async def compute_etf_allocation(
    portfolio_id: int,
    strategy: StrategyType | str | None = None,
) -> EtfAllocationPlan:
    """
    Calcula el plan de asignación de ETFs para el portfolio.

    Retorna:
      - ETFs recomendados con montos a invertir
      - Si se necesita rebalanceo
      - Resumen legible
    """
    from strategy.selector import normalize_strategy

    if strategy is None:
        portfolio = await repo.get_portfolio(portfolio_id)
        strategy = portfolio.strategy if portfolio and portfolio.strategy else StrategyType.VALUE

    st = normalize_strategy(strategy)
    config = get_etf_config(st)
    profile = await analyze_portfolio(portfolio_id)

    plan = EtfAllocationPlan()
    plan.current_etf_pct = profile.current_etf_pct
    plan.target_etf_pct = config.target_etf_pct
    plan.gap_pct = config.target_etf_pct - profile.current_etf_pct

    # ¿Necesita rebalanceo?
    plan.rebalance_needed = abs(plan.gap_pct) >= config.rebalance_threshold

    if not plan.rebalance_needed:
        plan.summary = (
            f"✅ Asignación de ETFs dentro del rango: "
            f"{profile.current_etf_pct:.1%} actual vs {config.target_etf_pct:.1%} objetivo "
            f"(tolerancia ±{config.rebalance_threshold:.0%})"
        )
        return plan

    # Solo actuar si estamos por debajo del objetivo (no vendemos ETFs automáticamente)
    if plan.gap_pct <= 0:
        plan.summary = (
            f"ℹ️ ETFs sobreponderados: {profile.current_etf_pct:.1%} actual "
            f"vs {config.target_etf_pct:.1%} objetivo. "
            f"No se recomienda vender ETFs, se ajustará con nuevas compras de acciones."
        )
        plan.rebalance_needed = False
        return plan

    # Calcular monto a invertir en ETFs
    target_etf_value = profile.total_value * config.target_etf_pct
    amount_needed = target_etf_value - profile.etf_value
    available_cash = profile.cash
    plan.total_amount_to_invest = min(amount_needed, available_cash)

    if plan.total_amount_to_invest < config.min_etf_amount:
        plan.summary = (
            f"ℹ️ ETFs infraponderados ({profile.current_etf_pct:.1%} vs {config.target_etf_pct:.1%}) "
            f"pero cash insuficiente para ajustar "
            f"(necesario: {amount_needed:.0f}, disponible: {available_cash:.0f})"
        )
        plan.rebalance_needed = False
        return plan

    # Seleccionar ETFs
    candidates = await select_etfs_for_portfolio(portfolio_id, strategy)
    if not candidates:
        plan.summary = "⚠️ No se encontraron ETFs candidatos adecuados."
        plan.rebalance_needed = False
        return plan

    # Distribuir monto entre los candidatos según sus scores
    total_score = sum(c.score for c in candidates if c.score > 0)
    if total_score <= 0:
        plan.summary = "⚠️ Ningún ETF candidato tiene score positivo."
        plan.rebalance_needed = False
        return plan

    recommendations: list[dict[str, Any]] = []
    remaining_amount = plan.total_amount_to_invest

    for c in candidates:
        if remaining_amount < config.min_etf_amount:
            break

        # Monto proporcional al score
        proportion = c.score / total_score
        raw_amount = plan.total_amount_to_invest * proportion

        # Limitar por concentración máxima individual
        max_for_etf = profile.total_value * config.max_single_etf_pct
        existing_etf_value = 0
        # Si ya tenemos este ETF, descontar
        for pos_ticker in profile.etf_tickers:
            if pos_ticker == c.ticker:
                positions = list(await repo.get_open_positions(portfolio_id))
                for p in positions:
                    if p.ticker == c.ticker:
                        existing_etf_value = (p.current_price or p.avg_price) * p.shares
                        break
                break
        allowed = max(0, max_for_etf - existing_etf_value)
        amount = min(raw_amount, allowed, remaining_amount)

        if amount < config.min_etf_amount:
            continue

        if c.price and c.price > 0:
            shares = amount / c.price
        else:
            continue

        recommendations.append({
            "ticker": c.ticker,
            "category": c.category,
            "score": round(c.score, 1),
            "amount": round(amount, 2),
            "shares": round(shares, 4),
            "price": c.price,
            "name": c.name,
            "reasoning": c.reasoning,
            "complementarity": round(c.complementarity * 100, 0),
        })
        remaining_amount -= amount

    plan.recommendations = recommendations

    # Resumen
    etf_list = ", ".join(f"{r['ticker']}({r['amount']:.0f})" for r in recommendations)
    plan.summary = (
        f"📦 Plan ETF: {profile.current_etf_pct:.1%} → {config.target_etf_pct:.1%}\n"
        f"💰 A invertir: {plan.total_amount_to_invest:.2f}\n"
        f"📋 ETFs: {etf_list}\n"
        f"🎯 Complementariedad media: "
        f"{sum(r['complementarity'] for r in recommendations) / max(len(recommendations), 1):.0f}%"
    )

    return plan


async def get_etf_portfolio_status(portfolio_id: int) -> dict[str, Any]:
    """
    Devuelve el estado actual de ETFs en el portfolio con métricas
    de asignación y recomendaciones.
    """
    portfolio = await repo.get_portfolio(portfolio_id)
    strategy = portfolio.strategy if portfolio and portfolio.strategy else StrategyType.VALUE

    profile = await analyze_portfolio(portfolio_id)
    config = get_etf_config(strategy)
    plan = await compute_etf_allocation(portfolio_id, strategy)

    # Posiciones ETF actuales con detalle
    positions = list(await repo.get_open_positions(portfolio_id))
    etf_positions = []
    for pos in positions:
        if _is_etf_position(pos):
            value = (pos.current_price or pos.avg_price) * pos.shares
            pnl = ((pos.current_price or pos.avg_price) - pos.avg_price) * pos.shares
            pnl_pct = ((pos.current_price or pos.avg_price) / pos.avg_price - 1) * 100 if pos.avg_price else 0
            cat = get_etf_category_for_ticker(pos.ticker) or "unknown"
            etf_positions.append({
                "ticker": pos.ticker,
                "category": cat,
                "shares": pos.shares,
                "avg_price": pos.avg_price,
                "current_price": pos.current_price,
                "value": round(value, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "weight_pct": round(value / profile.total_value * 100, 2) if profile.total_value > 0 else 0,
            })

    # Cobertura por categoría
    category_coverage: dict[str, list[str]] = {}
    for ep in etf_positions:
        cat = ep["category"]
        category_coverage.setdefault(cat, []).append(ep["ticker"])

    return {
        "strategy": strategy.value if hasattr(strategy, "value") else str(strategy),
        "target_etf_pct": round(config.target_etf_pct * 100, 1),
        "current_etf_pct": round(profile.current_etf_pct * 100, 1),
        "gap_pct": round(plan.gap_pct * 100, 1),
        "rebalance_needed": plan.rebalance_needed,
        "total_value": round(profile.total_value, 2),
        "etf_value": round(profile.etf_value, 2),
        "stock_value": round(profile.stock_value, 2),
        "etf_positions": etf_positions,
        "recommendations": plan.recommendations,
        "category_coverage": category_coverage,
        "top_sectors": profile.top_sectors,
        "underweight_regions": profile.underweight_regions,
        "summary": plan.summary,
    }
