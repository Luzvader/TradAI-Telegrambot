import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import {
  AgentInfo,
  AgentRunPayload,
  BacktestRunPayload,
  OpenAIUsageSummary,
  PortfoliosPayload,
  SignalItem,
  StrategySwitchPayload,
} from './models';
import { Observable } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  getPortfolios(): Observable<PortfoliosPayload> {
    return this.http.get<PortfoliosPayload>('/api/portfolios');
  }

  getSignals(limit = 20): Observable<SignalItem[]> {
    return this.http.get<SignalItem[]>(`/api/signals?limit=${limit}`);
  }

  getOpenaiUsage(days = 30): Observable<OpenAIUsageSummary> {
    return this.http.get<OpenAIUsageSummary>(`/api/openai-usage?days=${days}`);
  }

  setStrategy(payload: StrategySwitchPayload): Observable<unknown> {
    return this.http.post('/api/strategy', payload);
  }

  runBacktest(payload: BacktestRunPayload): Observable<any> {
    return this.http.post('/api/backtest/run', payload);
  }

  getAgents(): Observable<{ agents: AgentInfo[] }> {
    return this.http.get<{ agents: AgentInfo[] }>('/api/agents');
  }

  runAgent(payload: AgentRunPayload): Observable<any> {
    return this.http.post('/api/agents/run', payload);
  }
}
