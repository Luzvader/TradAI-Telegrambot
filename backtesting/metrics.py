"""
Métricas de rendimiento para backtesting.
Calcula retorno total, anualizado, Sharpe, max drawdown, win rate, etc.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(slots=True)
class BacktestMetrics:
    """Resumen de métricas de un backtest."""

    # Capital
    initial_capital: float
    final_value: float

    # Retorno
    total_return_pct: float
    annualized_return_pct: float

    # Riesgo
    max_drawdown_pct: float
    sharpe_ratio: float | None
    volatility_pct: float | None

    # Operaciones
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float

    # Benchmark
    benchmark_return_pct: float | None = None
    alpha_pct: float | None = None

    # Período
    period_days: int = 0

    @property
    def profit_factor(self) -> float | None:
        """Ratio de ganancias totales / pérdidas totales."""
        if self.losing_trades == 0:
            return None
        if self.winning_trades == 0:
            return 0.0
        return self.winning_trades / self.losing_trades


def compute_metrics(
    daily_values: list[float],
    initial_capital: float,
    trades: list[dict],
    benchmark_values: list[float] | None = None,
    risk_free_rate: float = 0.04,
) -> BacktestMetrics:
    """
    Calcula métricas a partir de la serie de valores diarios del portfolio.

    Args:
        daily_values: Valor del portfolio al cierre de cada día.
        initial_capital: Capital inicial.
        trades: Lista de operaciones ejecutadas ({ticker, side, price, shares, pnl, ...}).
        benchmark_values: Serie de valores diarios del benchmark (mismo tamaño que daily_values).
        risk_free_rate: Tasa libre de riesgo anual (default 4%).
    """
    if not daily_values:
        return BacktestMetrics(
            initial_capital=initial_capital,
            final_value=initial_capital,
            total_return_pct=0.0,
            annualized_return_pct=0.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=None,
            volatility_pct=None,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate_pct=0.0,
        )

    final_value = daily_values[-1]
    period_days = len(daily_values)
    total_return = (final_value - initial_capital) / initial_capital * 100

    # Retorno anualizado
    years = period_days / 252  # Días de trading
    if years > 0 and final_value > 0:
        annualized = ((final_value / initial_capital) ** (1 / years) - 1) * 100
    else:
        annualized = 0.0

    # Max Drawdown
    max_drawdown = _max_drawdown(daily_values)

    # Retornos diarios
    daily_returns = _daily_returns(daily_values)

    # Volatilidad anualizada
    volatility = None
    sharpe = None
    if len(daily_returns) > 1:
        avg_ret = sum(daily_returns) / len(daily_returns)
        var = sum((r - avg_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        std = math.sqrt(var)
        volatility = std * math.sqrt(252) * 100  # Anualizada %

        # Sharpe Ratio
        daily_rf = risk_free_rate / 252
        excess_avg = avg_ret - daily_rf
        if std > 0:
            sharpe = round((excess_avg / std) * math.sqrt(252), 2)

    # Win rate
    winning = sum(1 for t in trades if t.get("pnl", 0) > 0)
    losing = sum(1 for t in trades if t.get("pnl", 0) < 0)
    total = winning + losing
    win_rate = (winning / total * 100) if total > 0 else 0.0

    # Benchmark
    benchmark_ret = None
    alpha = None
    if benchmark_values and len(benchmark_values) > 1:
        benchmark_ret = (benchmark_values[-1] - benchmark_values[0]) / benchmark_values[0] * 100
        alpha = total_return - benchmark_ret

    return BacktestMetrics(
        initial_capital=initial_capital,
        final_value=round(final_value, 2),
        total_return_pct=round(total_return, 2),
        annualized_return_pct=round(annualized, 2),
        max_drawdown_pct=round(max_drawdown, 2),
        sharpe_ratio=sharpe,
        volatility_pct=round(volatility, 2) if volatility is not None else None,
        total_trades=len(trades),
        winning_trades=winning,
        losing_trades=losing,
        win_rate_pct=round(win_rate, 1),
        benchmark_return_pct=round(benchmark_ret, 2) if benchmark_ret is not None else None,
        alpha_pct=round(alpha, 2) if alpha is not None else None,
        period_days=period_days,
    )


def _max_drawdown(values: list[float]) -> float:
    """Calcula el máximo drawdown en porcentaje."""
    if not values:
        return 0.0
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _daily_returns(values: list[float]) -> list[float]:
    """Calcula retornos diarios como fracción."""
    returns = []
    for i in range(1, len(values)):
        if values[i - 1] > 0:
            returns.append((values[i] - values[i - 1]) / values[i - 1])
        else:
            returns.append(0.0)
    return returns
