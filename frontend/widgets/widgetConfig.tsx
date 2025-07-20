import { ReactNode } from "react";
import BalanceWidget from "../components/BalanceWidget";
import PricesWidget from "../components/PricesWidget";
import TVChartWidget from "../components/TVChartWidget";
import StrategiesWidget from "../components/StrategiesWidget";
import ChatWidget from "../components/ChatWidget";
import PnlWidget from "../components/PnlWidget";

export interface WidgetConfig {
  key: string;
  name: string;
  component: ReactNode;
  cols: number;
  visible: boolean;
}

export const DEFAULT_WIDGETS: WidgetConfig[] = [
  {
    key: "balance",
    name: "Balance",
    component: <BalanceWidget />,
    cols: 3,
    visible: true,
  },
  {
    key: "prices",
    name: "Prices",
    component: <PricesWidget />,
    cols: 3,
    visible: true,
  },
  {
    key: "chart",
    name: "Market Chart",
    component: <TVChartWidget />,
    cols: 12,
    visible: true,
  },
  {
    key: "strategies",
    name: "Strategies",
    component: <StrategiesWidget />,
    cols: 2,
    visible: true,
  },
  {
    key: "chat",
    name: "Chat",
    component: <ChatWidget />,
    cols: 2,
    visible: true,
  },
  {
    key: "pnl",
    name: "PnL",
    component: <PnlWidget />,
    cols: 2,
    visible: true,
  },
];
