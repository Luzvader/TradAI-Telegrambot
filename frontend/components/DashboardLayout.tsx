"use client";

import { useEffect, useState } from "react";
import { Box, Button, Stack, Grid } from "@mui/material";
import WidgetFrame from "./WidgetFrame";
import { DEFAULT_WIDGETS, WidgetConfig } from "../widgets/widgetConfig";
import TVChartWidget from "./TVChartWidget";

export default function DashboardLayout() {
  const [widgets, setWidgets] = useState<WidgetConfig[]>(DEFAULT_WIDGETS);


  // Persist visibility in localStorage
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
      <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 180px)' }}>
        <Grid container spacing={2} sx={{ flex: '0 0 auto' }}>
          {widgets
            .filter(w => w.visible && w.key !== 'chart')
            .map((w) => (
              <Grid
                key={w.key}
                item
                xs={12}
                sm={6}
                md={4}
                lg={w.cols}
                xl={w.cols}
              >
                <WidgetFrame title={w.name}>{w.component}</WidgetFrame>
              </Grid>
            ))}
        </Grid>
        {widgets.some(w => w.visible && w.key === 'chart') && (
          <Box sx={{ flex: '1 1 auto', mt: 2, minHeight: '400px' }}>
            <WidgetFrame title="Market Chart">
              <TVChartWidget />
            </WidgetFrame>
          </Box>
        )}
      </Box>
    </Box>
  );
}
