import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../core/api.service';
import { PortfoliosPayload, PortfolioSummary } from '../../core/models';

@Component({
  selector: 'app-portfolios',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './portfolios.component.html',
  styleUrl: './portfolios.component.css',
})
export class PortfoliosComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly data = signal<PortfoliosPayload>({ real: null, backtest: null });
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.getPortfolios().subscribe({
      next: (payload) => {
        this.data.set(payload);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(err?.error?.detail || 'Failed loading portfolios.');
        this.loading.set(false);
      },
    });
  }

  labelClass(pnlPct: number | null | undefined): string {
    if ((pnlPct || 0) >= 0) {
      return 'chip positive';
    }
    return 'chip negative';
  }

  asMoney(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '-';
    }
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
  }

  trackByTicker(_: number, row: { ticker: string }): string {
    return row.ticker;
  }

  portfolioRows(portfolio: PortfolioSummary | null): Array<any> {
    return portfolio?.positions || [];
  }
}
