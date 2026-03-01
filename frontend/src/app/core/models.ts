export interface PositionSummary {
  ticker: string;
  market: string;
  sector: string;
  shares: number;
  avg_price: number;
  current_price: number;
  value: number;
  pnl_abs: number;
  pnl_pct: number;
}

export interface PortfolioSummary {
  name: string;
  strategy: string;
  cash: number;
  initial_capital: number;
  total_invested: number;
  total_value: number;
  total_pnl: number;
  total_pnl_pct: number;
  total_assets: number;
  num_positions: number;
  positions: PositionSummary[];
}

export interface PortfoliosPayload {
  real: PortfolioSummary | null;
  backtest: PortfolioSummary | null;
}

export interface SignalItem {
  id: number;
  ticker: string;
  market: string;
  type: string;
  price: number;
  score: number;
  created_at: string;
  reasoning: string;
}

export interface OpenAIUsageSummary {
  total_calls: number;
  total_tokens: number;
  total_cost_usd: number;
}

export interface StrategySwitchPayload {
  portfolio_type: 'real' | 'backtest';
  strategy: 'value' | 'growth' | 'dividend' | 'balanced' | 'conservative';
}

export interface BacktestRunPayload {
  tickers: string[];
  period: string;
  strategy?: string | null;
  initial_capital: number;
  rebalance_days: number;
  max_positions: number;
  position_size_pct: number;
  buy_threshold: number;
  sell_threshold: number;
  use_technicals: boolean;
  use_learning: boolean;
  auto_learn: boolean;
}

export interface AgentInfo {
  id: string;
  name: string;
  kind: 'local' | 'remote';
  description: string;
  timeout_seconds: number;
  enabled: boolean;
}

export interface AgentRunPayload {
  agent_id: string;
  ticker: string;
  market?: string | null;
  strategy?: string | null;
  context?: string;
}
