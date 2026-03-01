import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/api.service';
import { StrategySwitchPayload } from '../../core/models';

@Component({
  selector: 'app-strategy',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './strategy.component.html',
  styleUrl: './strategy.component.css',
})
export class StrategyComponent {
  private readonly api = inject(ApiService);

  readonly loading = signal(false);
  readonly success = signal<string | null>(null);
  readonly error = signal<string | null>(null);

  form: StrategySwitchPayload = {
    portfolio_type: 'real',
    strategy: 'value',
  };

  readonly options: Array<{ value: StrategySwitchPayload['strategy']; label: string; profile: string }> = [
    { value: 'value', label: 'Value', profile: 'margin of safety and fundamentals' },
    { value: 'growth', label: 'Growth', profile: 'high momentum and expansion' },
    { value: 'dividend', label: 'Dividend', profile: 'income stability and payout quality' },
    { value: 'balanced', label: 'Balanced', profile: 'value-growth compromise' },
    { value: 'conservative', label: 'Conservative', profile: 'defensive low-volatility profile' },
  ];

  submit(): void {
    this.loading.set(true);
    this.success.set(null);
    this.error.set(null);

    this.api.setStrategy(this.form).subscribe({
      next: () => {
        this.success.set(
          `Strategy switched to ${this.form.strategy.toUpperCase()} for ${this.form.portfolio_type.toUpperCase()} portfolio.`,
        );
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(err?.error?.detail || 'Failed switching strategy.');
        this.loading.set(false);
      },
    });
  }
}
