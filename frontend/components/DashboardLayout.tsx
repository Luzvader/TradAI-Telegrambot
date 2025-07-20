"use client";

import { useEffect, useState } from "react";
import { Box, Button, Stack } from "@mui/material";
import { WidthProvider, Responsive } from "react-grid-layout";
import WidgetFrame from "./WidgetFrame";
import { DEFAULT_WIDGETS, WidgetConfig } from "../widgets/widgetConfig";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

const ResponsiveGridLayout = WidthProvider(Responsive);


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
            <WidgetFrame key={w.key} title={w.name}>
              {w.component}
            </WidgetFrame>
          ))}
      </ResponsiveGridLayout>
    </Box>
  );
}
