"use client";

import { ReactNode, useEffect, useState } from "react";
import GridLayout, { Layout } from "react-grid-layout";
import BalanceWidget from "./BalanceWidget";
import PricesWidget from "./PricesWidget";
import TVChartWidget from "./TVChartWidget";
import StrategiesWidget from "./StrategiesWidget";
import ChatWidget from "./ChatWidget";
import PnlWidget from "./PnlWidget";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

interface WidgetConfig {
  key: string;
  name: string;
  component: ReactNode;
  defaultLayout: Layout;
  visible: boolean;
}

const DEFAULT_WIDGETS: WidgetConfig[] = [
  {
    key: "balance",
    name: "Balance",
    component: <BalanceWidget />,
    defaultLayout: { i: "balance", x: 0, y: 0, w: 3, h: 2 },
    visible: true,
  },
  {
    key: "prices",
    name: "Prices",
    component: <PricesWidget />,
    defaultLayout: { i: "prices", x: 3, y: 0, w: 3, h: 4 },
    visible: true,
  },
  {
    key: "chart",
    name: "Market Chart",
    component: <TVChartWidget />,
    defaultLayout: { i: "chart", x: 0, y: 2, w: 6, h: 6 },
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
    defaultLayout: { i: "chat", x: 6, y: 4, w: 2, h: 3 },
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

export default function DashboardLayout() {
  const [widgets, setWidgets] = useState<WidgetConfig[]>(DEFAULT_WIDGETS);

  const layout = widgets
    .filter((w) => w.visible)
    .map((w) => ({ ...w.defaultLayout, i: w.key }));

  // Persist layout/visibility in localStorage
  useEffect(() => {
    const saved = localStorage.getItem("dashboard-widgets");
    if (saved) {
      try {
        const parsed: WidgetConfig[] = JSON.parse(saved);
        setWidgets(parsed);
      } catch (e) {
        console.error("Failed to parse widgets", e);
      }
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("dashboard-widgets", JSON.stringify(widgets));
  }, [widgets]);

  const toggleWidget = (key: string) => {
    setWidgets((prev) =>
      prev.map((w) => (w.key === key ? { ...w, visible: !w.visible } : w))
    );
  };

  return (
    <div>
      {/* Controls */}
      <div style={{ marginBottom: 16 }}>
        {widgets.map((w) => (
          <button
            key={w.key}
            onClick={() => toggleWidget(w.key)}
            style={{ marginRight: 8 }}
          >
            {w.visible ? "Ocultar" : "Mostrar"} {w.name}
          </button>
        ))}
      </div>
      <GridLayout
        className="layout"
        layout={layout}
        cols={12}
        rowHeight={30}
        width={1200}
        isDraggable={true}
        isResizable={true}
      >
        {widgets
          .filter((w) => w.visible)
          .map((w) => (
            <div key={w.key} style={{ border: "1px solid #ddd", padding: 8 }}>
              <h4>{w.name}</h4>
              {w.component}
            </div>
          ))}
      </GridLayout>
    </div>
  );
}
