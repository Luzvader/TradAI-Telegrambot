import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/api.service';
import { AgentInfo } from '../../core/models';

@Component({
  selector: 'app-agents',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './agents.component.html',
  styleUrl: './agents.component.css',
})
export class AgentsComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly loadingAgents = signal(true);
  readonly running = signal(false);
  readonly error = signal<string | null>(null);
  readonly result = signal<any>(null);
  readonly agents = signal<AgentInfo[]>([]);

  form = {
    agent_id: '',
    ticker: 'AAPL',
    market: 'NASDAQ',
    strategy: '',
    context: '',
  };

  ngOnInit(): void {
    this.loadAgents();
  }

  loadAgents(): void {
    this.loadingAgents.set(true);
    this.error.set(null);
    this.api.getAgents().subscribe({
      next: (payload) => {
        this.agents.set(payload.agents || []);
        if (!this.form.agent_id && payload.agents?.length) {
          this.form.agent_id = payload.agents[0].id;
        }
        this.loadingAgents.set(false);
      },
      error: (err) => {
        this.error.set(err?.error?.detail || 'Failed loading agents.');
        this.loadingAgents.set(false);
      },
    });
  }

  run(): void {
    this.running.set(true);
    this.error.set(null);
    this.result.set(null);

    this.api
      .runAgent({
        agent_id: this.form.agent_id,
        ticker: this.form.ticker.trim().toUpperCase(),
        market: this.form.market || null,
        strategy: this.form.strategy || null,
        context: this.form.context,
      })
      .subscribe({
        next: (payload) => {
          this.result.set(payload);
          this.running.set(false);
        },
        error: (err) => {
          this.error.set(err?.error?.detail || 'Agent execution failed.');
          this.running.set(false);
        },
      });
  }
}
