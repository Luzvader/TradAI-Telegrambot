import { Routes } from '@angular/router';
import { DashboardComponent } from './features/dashboard/dashboard.component';
import { PortfoliosComponent } from './features/portfolios/portfolios.component';
import { StrategyComponent } from './features/strategy/strategy.component';
import { BacktestingComponent } from './features/backtesting/backtesting.component';
import { AgentsComponent } from './features/agents/agents.component';

export const routes: Routes = [
  { path: '', pathMatch: 'full', component: DashboardComponent },
  { path: 'portfolios', component: PortfoliosComponent },
  { path: 'strategy', component: StrategyComponent },
  { path: 'backtesting', component: BacktestingComponent },
  { path: 'agents', component: AgentsComponent },
  { path: '**', redirectTo: '' },
];
