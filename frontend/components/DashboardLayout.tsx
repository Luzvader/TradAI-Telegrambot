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
      <Box sx={{ 
        display: 'flex', 
        flexDirection: 'column', 
        height: 'calc(100vh - 180px)',
        minHeight: 0, // Allow this container to shrink
        overflow: 'hidden' // Prevent main container from scrolling
      }}>
        {/* Top section - Other widgets (45% of available height) */}
        <Box sx={{ 
          flex: '0 0 auto', // Changed to auto to fit content
          mb: 2,
          minHeight: 0, // Allow this container to shrink
          '& .MuiGrid-container': {
            height: 'auto',
            alignItems: 'stretch',
            margin: 0, // Remove default grid spacing
            width: '100%' // Ensure grid takes full width
          },
          '& .MuiGrid-item': {
            display: 'flex',
            flexDirection: 'column',
            padding: '8px',
            boxSizing: 'border-box',
            minHeight: 0, // Allow grid items to shrink below content size
            height: 'auto' // Allow items to determine their own height
          }
        }}>
          <Grid container spacing={2}>
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
                  <WidgetFrame title={w.name}>
                    {w.component}
                  </WidgetFrame>
                </Grid>
              ))}
          </Grid>
        </Box>
        
        {/* Bottom section - TradingView widget (55% of available height) */}
        {widgets.some(w => w.visible && w.key === 'chart') && (
          <Box sx={{ 
            flex: '1 1 auto', // Changed to auto to fit content
            mt: 2,
            minHeight: '300px',
            display: 'flex',
            flexDirection: 'column',
            '& > div': {
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              minHeight: 0 // Allow this container to shrink below content size
            }
          }}>
            <WidgetFrame title="Market Chart">
              <TVChartWidget />
            </WidgetFrame>
          </Box>
        )}
      </Box>
    </Box>
  );
}
