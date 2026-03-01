import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/api.service';
import { BacktestRunPayload } from '../../core/models';

@Component({
  selector: 'app-backtesting',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './backtesting.component.html',
  styleUrl: './backtesting.component.css',
})
export class BacktestingComponent {
  private readonly api = inject(ApiService);

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly result = signal<any>(null);

  form = {
    tickersText: 'AAPL,MSFT,NVDA',
    period: '1y',
    strategy: '',
    initial_capital: 10000,
    rebalance_days: 5,
    max_positions: 10,
    position_size_pct: 0.1,
    buy_threshold: 70,
    sell_threshold: 30,
    use_technicals: true,
    use_learning: true,
    auto_learn: false,
  };

  run(): void {
    this.loading.set(true);
    this.error.set(null);
    this.result.set(null);

    const tickers = this.form.tickersText
      .split(',')
      .map((item) => item.trim().toUpperCase())
      .filter((item) => item.length > 0);

    const payload: BacktestRunPayload = {
      tickers,
      period: this.form.period,
      strategy: this.form.strategy || null,
      initial_capital: this.form.initial_capital,
      rebalance_days: this.form.rebalance_days,
      max_positions: this.form.max_positions,
      position_size_pct: this.form.position_size_pct,
      buy_threshold: this.form.buy_threshold,
      sell_threshold: this.form.sell_threshold,
      use_technicals: this.form.use_technicals,
      use_learning: this.form.use_learning,
      auto_learn: this.form.auto_learn,
    };

    this.api.runBacktest(payload).subscribe({
      next: (response) => {
        this.result.set(response);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(err?.error?.detail || 'Backtest execution failed.');
        this.loading.set(false);
      },
    });
  }
}
