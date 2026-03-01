import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { ApiService } from '../../core/api.service';
import { OpenAIUsageSummary, PortfoliosPayload, SignalItem } from '../../core/models';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.css',
})
export class DashboardComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly portfolios = signal<PortfoliosPayload>({ real: null, backtest: null });
  readonly signals = signal<SignalItem[]>([]);
  readonly usage = signal<OpenAIUsageSummary | null>(null);

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading.set(true);
    this.error.set(null);

    forkJoin({
      portfolios: this.api.getPortfolios(),
      signals: this.api.getSignals(12),
      usage: this.api.getOpenaiUsage(30),
    })
      .pipe(
        catchError((err) => {
          this.error.set(err?.error?.detail || 'Failed loading dashboard data.');
          return of({ portfolios: { real: null, backtest: null }, signals: [], usage: null });
        }),
      )
      .subscribe((payload) => {
        this.portfolios.set(payload.portfolios);
        this.signals.set(payload.signals || []);
        this.usage.set(payload.usage);
        this.loading.set(false);
      });
  }

  asMoney(value: number | null | undefined, currency = 'USD'): string {
    if (value === null || value === undefined) {
      return '-';
    }
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      maximumFractionDigits: 2,
    }).format(value);
  }
}
