import { ReactNode } from "react";
import { Layout } from "react-grid-layout";
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
  defaultLayout: Layout;
  visible: boolean;
}

export const DEFAULT_WIDGETS: WidgetConfig[] = [
  {
    key: "balance",
    name: "Balance",
    component: <BalanceWidget />,
    defaultLayout: { i: "balance", x: 0, y: 0, w: 3, h: 8, minH: 6, minW: 3 },
    visible: true,
  },
  {
    key: "prices",
    name: "Prices",
    component: <PricesWidget />,
    defaultLayout: { i: "prices", x: 3, y: 0, w: 3, h: 10, minH: 10 },
    visible: true,
  },
  {
    key: "chart",
    name: "Market Chart",
    component: <TVChartWidget />,
    defaultLayout: { i: "chart", x: 0, y: 2, w: 6, h: 10, minH: 6, minW: 4 },
    visible: true,
  },
  {
    key: "strategies",
    name: "Strategies",
    component: <StrategiesWidget />,
    defaultLayout: { i: "strategies", x: 6, y: 0, w: 2, h: 4 },
    visible: true,
  },
  {
    key: "chat",
    name: "Chat",
    component: <ChatWidget />,
    defaultLayout: { i: "chat", x: 6, y: 4, w: 2, h: 6, minH: 6, minW: 2 },
    visible: true,
  },
  {
    key: "pnl",
    name: "PnL",
    component: <PnlWidget />,
    defaultLayout: { i: "pnl", x: 0, y: 8, w: 2, h: 2 },
    visible: true,
  },
];
