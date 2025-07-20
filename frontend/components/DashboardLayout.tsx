"use client";

import { ReactNode, useEffect, useState } from "react";
import { Box, Button, Paper, Stack } from "@mui/material";
import { WidthProvider, Responsive, Layout } from "react-grid-layout";
import BalanceWidget from "./BalanceWidget";
import PricesWidget from "./PricesWidget";
import TVChartWidget from "./TVChartWidget";
import StrategiesWidget from "./StrategiesWidget";
import ChatWidget from "./ChatWidget";
import PnlWidget from "./PnlWidget";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

const ResponsiveGridLayout = WidthProvider(Responsive);

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
    defaultLayout: { i: "balance", x: 0, y: 0, w: 3, h: 4, minH: 4, minW: 3 },
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

export default function DashboardLayout() {
  const [widgets, setWidgets] = useState<WidgetConfig[]>(DEFAULT_WIDGETS);

  const layout = widgets
    .filter((w) => w.visible)
    .map((w) => ({ ...w.defaultLayout, i: w.key }));

  // Prepare layouts for responsive breakpoints
  const layouts = {
    lg: layout,
    md: layout,
    sm: layout,
  };

  // Persist layout/visibility in localStorage
  useEffect(() => {
    const saved = localStorage.getItem("dashboard-widgets");
    if (saved) {
      try {
        const parsed: { key: string; visible: boolean }[] = JSON.parse(saved);
        setWidgets((prev) =>
          prev.map((w) => {
            const found = parsed.find((p) => p.key === w.key);
            return found ? { ...w, visible: found.visible } : w;
          })
        );
      } catch (e) {
        console.error("Failed to parse widgets", e);
      }
    }
  }, []);

  useEffect(() => {
    const compact = widgets.map(({ key, visible }) => ({ key, visible }));
    localStorage.setItem("dashboard-widgets", JSON.stringify(compact));
  }, [widgets]);

  const toggleWidget = (key: string) => {
    setWidgets((prev) =>
      prev.map((w) => (w.key === key ? { ...w, visible: !w.visible } : w))
    );
  };

  return (
    <Box>
      {/* Controls */}
      <Stack direction="row" spacing={1} mb={2}>
        {widgets.map((w) => (
          <Button
            key={w.key}
            variant="outlined"
            size="small"
            onClick={() => toggleWidget(w.key)}
          >
            {w.visible ? "Ocultar" : "Mostrar"} {w.name}
          </Button>
        ))}
      </Stack>
      <ResponsiveGridLayout
        className="layout"
        layouts={layouts}
        breakpoints={{ lg: 1200, md: 996, sm: 768 }}
        cols={{ lg: 12, md: 10, sm: 6 }}
        rowHeight={30}
        isDraggable
        isResizable
        resizeHandles={["s","w","e","n","sw","nw","se","ne"]}
        margin={[8, 8]}
        draggableHandle=".widget-drag-handle"
        draggableCancel="input,textarea,button,select,option,.no-drag"
      >
        {widgets
          .filter((w) => w.visible)
          .map((w) => (
            <Paper
              key={w.key}
              elevation={3}
              sx={{
                p: 1,
                height: "100%",
                boxSizing: "border-box",
                display: "flex",
                flexDirection: "column",
                overflow: "hidden",
              }}
            >
              <h4 className="widget-drag-handle" style={{ cursor: "move" }}>{w.name}</h4>
              {w.component}
            </Paper>
          ))}
      </ResponsiveGridLayout>
    </Box>
  );
}
