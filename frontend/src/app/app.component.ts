import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { NgFor } from '@angular/common';

interface NavItem {
  label: string;
  route: string;
  hint: string;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, NgFor],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css',
})
export class AppComponent {
  readonly navItems: NavItem[] = [
    { label: 'Overview', route: '/', hint: 'ops pulse' },
    { label: 'Portfolios', route: '/portfolios', hint: 'real + backtest' },
    { label: 'Strategy', route: '/strategy', hint: 'active policy' },
    { label: 'Backtesting', route: '/backtesting', hint: 'scenario lab' },
    { label: 'Agents', route: '/agents', hint: 'local / remote ai' },
  ];
}
