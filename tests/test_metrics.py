"""
Tests para backtesting/metrics.py — cálculo de métricas.
"""

from backtesting.metrics import compute_metrics, BacktestMetrics


def test_compute_metrics_basic():
    daily_values = [10000.0, 10100.0, 10050.0, 10200.0]
    m = compute_metrics(
        initial_capital=10000.0,
        daily_values=daily_values,
        trades=[],
    )
    assert isinstance(m, BacktestMetrics)
    assert m.total_return_pct > 0
    assert m.initial_capital == 10000.0
    assert m.final_value == 10200.0


def test_compute_metrics_loss():
    daily_values = [10000.0, 9500.0]
    m = compute_metrics(
        initial_capital=10000.0,
        daily_values=daily_values,
        trades=[],
    )
    assert m.total_return_pct < 0
    assert m.max_drawdown_pct > 0


def test_compute_metrics_empty():
    m = compute_metrics(
        initial_capital=10000.0,
        daily_values=[],
        trades=[],
    )
    assert m.total_return_pct == 0.0
    assert m.sharpe_ratio is None


def test_win_rate_calculation():
    trades = [
        {"pnl": 100},
        {"pnl": -50},
        {"pnl": 200},
        {"pnl": -30},
    ]
    daily_values = [10000.0, 10220.0]
    m = compute_metrics(
        initial_capital=10000.0,
        daily_values=daily_values,
        trades=trades,
    )
    assert m.win_rate_pct == 50.0  # 2 de 4


def test_benchmark_alpha():
    daily_values = [10000.0, 11000.0]
    benchmark = [100.0, 105.0]
    m = compute_metrics(
        initial_capital=10000.0,
        daily_values=daily_values,
        trades=[],
        benchmark_values=benchmark,
    )
    assert m.benchmark_return_pct == 5.0
    assert m.alpha_pct == 5.0  # 10% - 5%
