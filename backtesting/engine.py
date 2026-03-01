"""
Motor de backtesting – simula una estrategia sobre datos históricos.

Características:
  • Decisiones inteligentes: combina fundamentales + técnicos + aprendizaje
    previo del bot para comprar/hold/vender automáticamente.
  • Aprendizaje continuo: cada backtest alimenta el sistema de learning
    para mejorar futuras decisiones (reales y de backtesting).
  • Feedback loop: el bot aprende de sus propios backtests.

Limitaciones conocidas:
  • Los fundamentales usados son los *actuales* (yfinance no ofrece
    fundamentales históricos), por lo que los scores sólo reflejan el
    momento presente aplicado a precios históricos.
  • Es un backtester simplificado: no modela comisiones, slippage,
    dividendos ni splits (aunque yfinance los ajusta automáticamente).

A pesar de estas limitaciones, es útil para:
  • Evaluar la sensibilidad de una estrategia al timing de mercado.
  • Comparar rendimiento relativo entre estrategias.
  • Comprobar que una estrategia no es destructiva antes de usarla.
  • Generar aprendizaje que mejora las decisiones del bot en producción.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from config.markets import DEFAULT_TICKER_MARKET, get_yfinance_ticker, normalize_ticker
from data.fundamentals import fetch_fundamentals
from data.market_data import get_historical_data
from database.models import StrategyType
from strategy.score import StrategyScore
from strategy.selector import get_strategy_analyzer

from config.settings import SIGNAL_BUY_THRESHOLD, SIGNAL_SELL_THRESHOLD
from backtesting.metrics import BacktestMetrics, compute_metrics
from backtesting.learning_bridge import (
    compute_technical_signal_at_date,
    get_learning_adjustments,
    get_learning_context_for_decisions,
    process_backtest_trades_for_learning,
    analyze_backtest_session,
)

logger = logging.getLogger(__name__)

# ── Configuración por defecto ────────────────────────────────
DEFAULT_CAPITAL = 10_000.0
DEFAULT_PERIOD = "1y"
REBALANCE_INTERVAL_DAYS = 5  # Re-evalúa cada 5 días de trading
MAX_POSITIONS = 10
POSITION_SIZE_PCT = 0.10  # 10 % del capital por posición


@dataclass
class BacktestPosition:
    """Posición abierta durante el backtest."""
    ticker: str
    shares: float
    entry_price: float
    entry_date: str
    market: str | None = None


@dataclass
class BacktestConfig:
    """Configuración de un backtest."""
    tickers: list[str]
    strategy: StrategyType | str = StrategyType.VALUE
    period: str = DEFAULT_PERIOD
    initial_capital: float = DEFAULT_CAPITAL
    rebalance_days: int = REBALANCE_INTERVAL_DAYS
    max_positions: int = MAX_POSITIONS
    position_size_pct: float = POSITION_SIZE_PCT
    buy_threshold: float = SIGNAL_BUY_THRESHOLD
    sell_threshold: float = SIGNAL_SELL_THRESHOLD
    benchmark: str = "SPY"  # Ticker de referencia
    use_technicals: bool = True  # Usar indicadores técnicos en decisiones
    use_learning: bool = True    # Usar aprendizaje previo del bot
    auto_learn: bool = True      # Alimentar learning automáticamente tras el backtest


@dataclass
class BacktestResult:
    """Resultado completo de un backtest."""
    config: BacktestConfig
    metrics: BacktestMetrics
    trades: list[dict[str, Any]]
    daily_values: list[dict[str, Any]]  # [{date, value}]
    final_positions: list[dict[str, Any]]
    learning_logs_created: int = 0       # Nº de registros de aprendizaje generados
    session_analysis: str = ""           # Análisis IA de la sesión completa

    def format_summary(self) -> str:
        """Formatea el resultado como texto para Telegram."""
        m = self.metrics
        lines = [
            f"📊 **Backtest: {self.config.strategy}**",
            f"📅 Período: {self.config.period} ({m.period_days} días)",
            f"💰 Capital inicial: ${m.initial_capital:,.0f}",
            f"💵 Valor final: ${m.final_value:,.0f}",
            "",
            f"📈 Retorno total: {m.total_return_pct:+.1f}%",
            f"📈 Retorno anualizado: {m.annualized_return_pct:+.1f}%",
            f"📉 Max Drawdown: {m.max_drawdown_pct:.1f}%",
        ]
        if m.sharpe_ratio is not None:
            lines.append(f"⚡ Sharpe Ratio: {m.sharpe_ratio:.2f}")
        if m.volatility_pct is not None:
            lines.append(f"🌊 Volatilidad: {m.volatility_pct:.1f}%")

        lines += [
            "",
            f"🔄 Operaciones: {m.total_trades}",
            f"✅ Ganadoras: {m.winning_trades} ({m.win_rate_pct:.0f}%)",
            f"❌ Perdedoras: {m.losing_trades}",
        ]

        if m.benchmark_return_pct is not None:
            lines += [
                "",
                f"📊 Benchmark ({self.config.benchmark}): {m.benchmark_return_pct:+.1f}%",
                f"🎯 Alpha: {m.alpha_pct:+.1f}%",
            ]

        if self.final_positions:
            lines.append("")
            lines.append("📌 Posiciones finales:")
            for p in self.final_positions[:5]:
                lines.append(f"  • {p['ticker']}: {p['shares']:.0f} acc @ ${p['entry_price']:.2f}")

        if self.learning_logs_created > 0:
            lines += [
                "",
                f"🧠 Aprendizaje: {self.learning_logs_created} trades analizados",
            ]

        if self.session_analysis:
            lines += [
                "",
                "📝 Análisis de la sesión:",
                self.session_analysis[:500],
            ]

        return "\n".join(lines)


async def run_backtest(config: BacktestConfig) -> BacktestResult:
    """
    Ejecuta un backtest completo con decisiones inteligentes.

    Flujo:
      1. Descarga precios históricos de todos los tickers + benchmark.
      2. Evalúa fundamentales (snapshot actual) para asignar scores.
      3. Consulta el aprendizaje previo del bot para ajustar scores.
      4. Simula rebalanceo periódico con decisiones enriquecidas:
         - Score fundamental (estrategia)
         - Señales técnicas históricas (RSI, MACD, BB)
         - Ajuste por aprendizaje previo (track record por ticker)
      5. Calcula valor diario del portfolio.
      6. Computa métricas de rendimiento.
      7. Alimenta el sistema de learning con todos los trades.
      8. Genera análisis IA de la sesión completa.
    """
    analyzer = get_strategy_analyzer(config.strategy)
    tickers = [normalize_ticker(t).upper() for t in config.tickers]
    strategy_name = str(config.strategy.value if hasattr(config.strategy, 'value') else config.strategy)

    # 1. Descargar precios históricos en paralelo
    logger.info(f"Backtesting {len(tickers)} tickers, período {config.period}")
    price_data = await _fetch_all_prices(tickers, config.period)

    if not price_data:
        raise ValueError("No se pudieron obtener datos históricos para ningún ticker")

    # Benchmark
    benchmark_prices: pd.Series | None = None
    try:
        bm_df = await get_historical_data(config.benchmark, period=config.period)
        if bm_df is not None and not bm_df.empty:
            benchmark_prices = bm_df["Close"]
    except Exception as e:
        logger.warning(f"No se pudo obtener benchmark {config.benchmark}: {e}")

    # 2. Evaluar fundamentales (snapshot actual)
    scores = await _score_tickers(tickers, analyzer)

    # 3. Consultar aprendizaje previo del bot
    learning_adj: dict[str, float] = {}
    learning_context: str = ""
    if config.use_learning:
        try:
            learning_adj = await get_learning_adjustments(tickers)
            learning_context = await get_learning_context_for_decisions()
            if learning_context:
                logger.info(f"🧠 Aprendizaje aplicado: ajustes para {sum(1 for v in learning_adj.values() if v != 0)} tickers")
        except Exception as e:
            logger.warning(f"No se pudo consultar aprendizaje: {e}")

    # 4. Construir fechas de trading (unión de todos los DataFrames)
    all_dates = _get_common_dates(price_data)
    if not all_dates:
        raise ValueError("No hay fechas de trading comunes entre los tickers")

    # 5. Simular con decisiones inteligentes
    cash = config.initial_capital
    positions: dict[str, BacktestPosition] = {}
    trades: list[dict[str, Any]] = []
    daily_values: list[dict[str, Any]] = []
    last_rebalance_idx = -config.rebalance_days  # Forzar rebalanceo inicial

    for idx, date in enumerate(all_dates):
        date_str = str(date.date()) if hasattr(date, "date") else str(date)

        # Rebalancear periódicamente con decisiones inteligentes
        if idx - last_rebalance_idx >= config.rebalance_days:
            last_rebalance_idx = idx
            cash, positions, new_trades = _smart_rebalance(
                date_str=date_str,
                cash=cash,
                positions=positions,
                scores=scores,
                price_data=price_data,
                date=date,
                config=config,
                learning_adj=learning_adj,
            )
            trades.extend(new_trades)

        # Calcular valor del portfolio
        portfolio_value = cash
        for ticker, pos in positions.items():
            price = _get_price_at(price_data, ticker, date)
            if price is not None:
                portfolio_value += pos.shares * price

        daily_values.append({"date": date_str, "value": round(portfolio_value, 2)})

    # 6. Métricas
    value_series = [dv["value"] for dv in daily_values]
    benchmark_series = None
    if benchmark_prices is not None:
        # Alinear benchmark con las fechas del backtest
        benchmark_series = []
        for dv in daily_values:
            dt = pd.Timestamp(dv["date"])
            # Buscar la fecha más cercana en el benchmark
            if dt in benchmark_prices.index:
                benchmark_series.append(float(benchmark_prices[dt]))
            else:
                closest = benchmark_prices.index[benchmark_prices.index.get_indexer([dt], method="nearest")[0]]
                benchmark_series.append(float(benchmark_prices[closest]))

    metrics = compute_metrics(
        daily_values=value_series,
        initial_capital=config.initial_capital,
        trades=trades,
        benchmark_values=benchmark_series,
    )

    final_pos = [
        {
            "ticker": pos.ticker,
            "shares": pos.shares,
            "entry_price": pos.entry_price,
            "entry_date": pos.entry_date,
            "current_price": _get_price_at(price_data, pos.ticker, all_dates[-1]),
        }
        for pos in positions.values()
    ]

    # 7. Auto-learning: alimentar el sistema de aprendizaje con los trades
    learning_logs_created = 0
    session_analysis = ""

    if config.auto_learn and trades:
        try:
            config_summary = (
                f"{strategy_name} | {config.period} | "
                f"Capital: ${config.initial_capital:,.0f} | "
                f"Rebalanceo: {config.rebalance_days}d | "
                f"Técnicos: {'sí' if config.use_technicals else 'no'} | "
                f"Learning: {'sí' if config.use_learning else 'no'}"
            )
            logs = await process_backtest_trades_for_learning(
                trades=trades,
                strategy=strategy_name,
                config_summary=config_summary,
            )
            learning_logs_created = len(logs)
            logger.info(
                f"🧠 Auto-learning: {learning_logs_created} trades → learning"
            )
        except Exception as e:
            logger.warning(f"Error en auto-learning: {e}")

    # 8. Análisis IA de la sesión completa
    if config.auto_learn and trades:
        try:
            session_analysis = await analyze_backtest_session(
                trades=trades,
                metrics_summary=f"Retorno: {metrics.total_return_pct:+.1f}% | "
                    f"Sharpe: {metrics.sharpe_ratio or 'N/A'} | "
                    f"MaxDD: {metrics.max_drawdown_pct:.1f}% | "
                    f"Win rate: {metrics.win_rate_pct:.0f}% | "
                    f"Alpha: {metrics.alpha_pct or 'N/A'}%",
                strategy=strategy_name,
            )
        except Exception as e:
            logger.warning(f"Error en análisis de sesión: {e}")

    return BacktestResult(
        config=config,
        metrics=metrics,
        trades=trades,
        daily_values=daily_values,
        final_positions=final_pos,
        learning_logs_created=learning_logs_created,
        session_analysis=session_analysis,
    )


# ── Helpers internos ─────────────────────────────────────────


async def _fetch_all_prices(
    tickers: list[str], period: str
) -> dict[str, pd.DataFrame]:
    """Descarga datos históricos para todos los tickers (paralelo con semáforo)."""
    sem = asyncio.Semaphore(5)
    result: dict[str, pd.DataFrame] = {}

    async def _one(ticker: str):
        async with sem:
            market = DEFAULT_TICKER_MARKET.get(ticker)
            df = await get_historical_data(ticker, period=period, market=market)
            if df is not None and not df.empty:
                result[ticker] = df

    await asyncio.gather(*[_one(t) for t in tickers])
    return result


async def _score_tickers(
    tickers: list[str], analyzer
) -> dict[str, StrategyScore]:
    """Evalúa fundamentales de cada ticker con la estrategia dada."""
    scores: dict[str, StrategyScore] = {}
    sem = asyncio.Semaphore(5)

    async def _one(ticker: str):
        async with sem:
            try:
                market = DEFAULT_TICKER_MARKET.get(ticker)
                fd = await asyncio.to_thread(fetch_fundamentals, ticker, market)
                if fd is not None:
                    vs = await asyncio.to_thread(analyzer, fd)
                    scores[ticker] = vs
            except Exception as e:
                logger.debug(f"Error evaluando {ticker}: {e}")

    await asyncio.gather(*[_one(t) for t in tickers])
    return scores


def _get_common_dates(price_data: dict[str, pd.DataFrame]) -> list:
    """Obtiene las fechas comunes entre todos los DataFrames (unión)."""
    if not price_data:
        return []
    # Usar unión de fechas para no descartar tickers con menos historial
    all_idx = None
    for df in price_data.values():
        if all_idx is None:
            all_idx = df.index
        else:
            all_idx = all_idx.union(df.index)
    return sorted(all_idx) if all_idx is not None else []


def _get_price_at(
    price_data: dict[str, pd.DataFrame], ticker: str, date
) -> float | None:
    """Obtiene el precio de cierre de un ticker en una fecha dada."""
    df = price_data.get(ticker)
    if df is None:
        return None
    if date in df.index:
        return float(df.loc[date, "Close"])
    # Buscar la fecha anterior más cercana
    earlier = df.index[df.index <= date]
    if len(earlier) > 0:
        return float(df.loc[earlier[-1], "Close"])
    return None


def _smart_rebalance(
    date_str: str,
    cash: float,
    positions: dict[str, BacktestPosition],
    scores: dict[str, StrategyScore],
    price_data: dict[str, pd.DataFrame],
    date,
    config: BacktestConfig,
    learning_adj: dict[str, float] | None = None,
) -> tuple[float, dict[str, BacktestPosition], list[dict]]:
    """
    Ejecuta un ciclo de rebalanceo inteligente:
      1. Para cada posición abierta, evalúa si VENDER o HOLD:
         - Score fundamental ≤ sell_threshold → vender
         - Señal técnica BEARISH fuerte → vender
         - Ajuste de learning muy negativo → vender
      2. Comprar tickers con score alto ajustado:
         - Score fundamental + ajuste técnico + ajuste learning
         - Solo compra si el score combinado ≥ buy_threshold
      3. HOLD implícito: posiciones que no se venden se mantienen.

    El score efectivo se calcula como:
      effective_score = fundamental_score + technical_adj + learning_adj

    Esto permite que el bot tome decisiones basadas en TODO su conocimiento.
    """
    if learning_adj is None:
        learning_adj = {}

    new_trades: list[dict] = []

    # 1. VENTAS: evaluar cada posición con criterios enriquecidos
    tickers_to_sell = []
    for ticker, pos in positions.items():
        score = scores.get(ticker)
        base_score = score.overall_score if score else 0

        # Ajuste técnico
        tech_adj = 0.0
        if config.use_technicals:
            tech = compute_technical_signal_at_date(
                price_data.get(ticker), date
            )
            tech_adj = tech.get("signal_adj", 0.0)

        # Ajuste de learning
        learn_adj = learning_adj.get(ticker, 0.0)

        # Score efectivo para decisión de venta
        effective_score = base_score + tech_adj + learn_adj

        # Decisión de VENTA
        should_sell = False
        sell_reason = ""

        if effective_score <= config.sell_threshold:
            should_sell = True
            sell_reason = f"score_efectivo={effective_score:.0f}≤{config.sell_threshold}"
        elif tech_adj <= -7 and base_score < config.buy_threshold:
            # Señal técnica fuertemente bearish + score no convincente
            should_sell = True
            sell_reason = f"técnico_bearish(adj={tech_adj:.0f})"
        elif learn_adj <= -10 and base_score < config.buy_threshold:
            # Learning dice que este ticker suele perder
            should_sell = True
            sell_reason = f"learning_negativo(adj={learn_adj:.0f})"

        if should_sell:
            price = _get_price_at(price_data, ticker, date)
            if price is not None:
                proceeds = pos.shares * price
                pnl = proceeds - (pos.shares * pos.entry_price)
                cash += proceeds
                new_trades.append({
                    "date": date_str,
                    "ticker": ticker,
                    "side": "SELL",
                    "shares": pos.shares,
                    "price": round(price, 4),
                    "pnl": round(pnl, 2),
                    "reason": sell_reason,
                    "effective_score": round(effective_score, 1),
                    "tech_adj": round(tech_adj, 1),
                    "learn_adj": round(learn_adj, 1),
                })
                tickers_to_sell.append(ticker)
        # else: HOLD — la posición se mantiene (decisión implícita)

    for t in tickers_to_sell:
        del positions[t]

    # 2. COMPRAS: ordenar por score efectivo (fundamental + técnico + learning)
    buy_candidates = []
    for ticker, score in scores.items():
        if ticker in positions:
            continue

        base = score.overall_score

        tech_adj = 0.0
        if config.use_technicals:
            tech = compute_technical_signal_at_date(
                price_data.get(ticker), date
            )
            tech_adj = tech.get("signal_adj", 0.0)

        learn_adj = learning_adj.get(ticker, 0.0)
        effective = base + tech_adj + learn_adj

        if effective >= config.buy_threshold:
            buy_candidates.append((ticker, score, effective, tech_adj, learn_adj))

    # Ordenar por score efectivo descendente
    buy_candidates.sort(key=lambda x: x[2], reverse=True)

    for ticker, score, effective, tech_adj_val, learn_adj_val in buy_candidates:
        if len(positions) >= config.max_positions:
            break

        price = _get_price_at(price_data, ticker, date)
        if price is None or price <= 0:
            continue

        # Tamaño de posición: % del valor total del portfolio
        total_value = cash + sum(
            (pos.shares * (_get_price_at(price_data, pos.ticker, date) or pos.entry_price))
            for pos in positions.values()
        )
        alloc = total_value * config.position_size_pct
        shares = int(alloc // price)

        if shares <= 0 or shares * price > cash:
            continue

        cost = shares * price
        cash -= cost
        positions[ticker] = BacktestPosition(
            ticker=ticker,
            shares=shares,
            entry_price=round(price, 4),
            entry_date=date_str,
            market=DEFAULT_TICKER_MARKET.get(ticker),
        )
        new_trades.append({
            "date": date_str,
            "ticker": ticker,
            "side": "BUY",
            "shares": shares,
            "price": round(price, 4),
            "pnl": 0,
            "reason": f"score_efectivo={effective:.0f}",
            "effective_score": round(effective, 1),
            "tech_adj": round(tech_adj_val, 1),
            "learn_adj": round(learn_adj_val, 1),
        })

    return cash, positions, new_trades
