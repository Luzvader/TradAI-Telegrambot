import { ReactNode } from "react";
import BalancePnlWidget from "../components/BalancePnlWidget";
import PricesWidget from "../components/PricesWidget";
import TVChartWidget from "../components/TVChartWidget";
import StrategiesWidget from "../components/StrategiesWidget";
import ChatWidget from "../components/ChatWidget";
import NewsFeedWidget from "../components/NewsFeedWidget";

export interface WidgetConfig {
  key: string;
  name: string;
  component: ReactNode;
  cols: number;
  /** Optional fixed height for the widget (px) */
  height?: number;
  visible: boolean;
}

export const DEFAULT_WIDGETS: WidgetConfig[] = [
  {
    key: "balance-pnl",
    name: "Balance & PnL",
    component: <BalancePnlWidget />,
    cols: 4,
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
    key: "strategies",
    name: "Strategies",
    component: <StrategiesWidget />,
    cols: 3,
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
    key: "news",
    name: "News Feed",
    component: <NewsFeedWidget />,
    cols: 3,
    visible: true,
  },
  {
    key: "chart",
    name: "Market Chart",
    component: <TVChartWidget />,
    cols: 9,
    height: 500,
    visible: true,
  },
];
