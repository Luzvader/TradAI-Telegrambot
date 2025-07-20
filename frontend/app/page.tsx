"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { Box, Container, Typography } from "@mui/material";
import dynamic from 'next/dynamic';
import { Resizable, ResizableBox, ResizeCallbackData } from 'react-resizable';
import 'react-resizable/css/styles.css';

// Dynamically import widgets with no SSR to avoid window is not defined errors
const BalanceWidget = dynamic(() => import('../components/BalanceWidget'), { ssr: false });
const PricesWidget = dynamic(() => import('../components/PricesWidget'), { ssr: false });
const PnlWidget = dynamic(() => import('../components/PnlWidget'), { ssr: false });
const TVChartWidget = dynamic(() => import('../components/TVChartWidget'), { ssr: false });
const StrategiesWidget = dynamic(() => import('../components/StrategiesWidget'), { ssr: false });

interface WidgetSize {
  w: number;
  h: number;
}

interface WidgetProps {
  id: string;
  title: string;
  content: React.ReactNode;
  defaultSize: WidgetSize;
}

const widgetStyles = {
  bgcolor: 'background.paper',
  border: '1px solid',
  borderColor: 'divider',
  borderRadius: 2,
  boxShadow: 1,
  p: 2,
  height: '100%',
  display: 'flex',
  flexDirection: 'column',
  cursor: 'grab',
  position: 'relative',
  '&:active': {
    cursor: 'grabbing',
  },
  transition: 'all 0.2s ease',
  '&:hover': {
    boxShadow: 3,
    transform: 'translateY(-2px)',
    borderColor: 'primary.main',
  },
  '& .resize-handle': {
    position: 'absolute',
    right: 0,
    bottom: 0,
    width: 20,
    height: 20,
    cursor: 'nwse-resize',
    '&:before': {
      content: '""',
      position: 'absolute',
      right: 4,
      bottom: 4,
      width: 8,
      height: 8,
      borderRight: '2px solid',
      borderBottom: '2px solid',
      borderColor: 'action.active',
    },
    '&:hover:before': {
      borderColor: 'primary.main',
    },
  },
};

export default function Dashboard() {
  const [widgets, setWidgets] = useState<WidgetProps[]>([
    {
      id: 'balance',
      title: 'Balance',
      content: <BalanceWidget />,
      defaultSize: { w: 4, h: 1 }
    },
    {
      id: 'pnl',
      title: 'P&L',
      content: <PnlWidget />,
      defaultSize: { w: 4, h: 1 }
    },
    {
      id: 'strategies',
      title: 'Strategies',
      content: <StrategiesWidget />,
      defaultSize: { w: 4, h: 1 }
    },
    {
      id: 'prices',
      title: 'Market Prices',
      content: <PricesWidget />,
      defaultSize: { w: 12, h: 2 }
    },
    {
      id: 'chart',
      title: 'Trading Chart',
      content: <Box sx={{ flex: 1, minHeight: 400, width: '100%' }}><TVChartWidget /></Box>,
      defaultSize: { w: 12, h: 3 }
    },
  ]);

  const [draggedWidget, setDraggedWidget] = useState<WidgetProps | null>(null);
  const widgetRefs = useRef<{ [key: string]: HTMLDivElement | null }>({});
  const [isDragging, setIsDragging] = useState(false);
  const [widgets, setWidgets] = useState<WidgetProps[]>([
    { 
      id: 'balance', 
      title: 'Balance', 
      content: <BalanceWidget />, 
      defaultSize: { w: 4, h: 1 } 
    },
    { 
      id: 'prices', 
      title: 'Market Prices', 
      content: <PricesWidget />, 
      defaultSize: { w: 12, h: 2 } 
    },
    { 
      id: 'pnl', 
      title: 'P&L', 
      content: <PnlWidget />, 
      defaultSize: { w: 8, h: 2 } 
    },
    { 
      id: 'chart', 
      title: 'Trading Chart', 
      content: <TVChartWidget />, 
      defaultSize: { w: 12, h: 3 } 
    },
    { 
      id: 'strategies', 
      title: 'Strategies', 
      content: <StrategiesWidget />, 
      defaultSize: { w: 4, h: 2 } 
    },
  ]);

  const handleDragStart = (e: React.DragEvent<HTMLDivElement>, widget: WidgetProps) => {
    if (resizeState.isResizing) {
      e.preventDefault();
      return;
    }
    setDraggedWidget(widget);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/html', '');
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>, targetId: string) => {
    e.preventDefault();
    if (resizeState.isResizing || !draggedWidget || draggedWidget.id === targetId) return;

    setWidgets(prevWidgets => {
      const draggedIndex = prevWidgets.findIndex(w => w.id === draggedWidget.id);
      const targetIndex = prevWidgets.findIndex(w => w.id === targetId);
      
      if (draggedIndex === -1 || targetIndex === -1) return prevWidgets;
      
      const newWidgets = [...prevWidgets];
      const [removed] = newWidgets.splice(draggedIndex, 1);
      newWidgets.splice(targetIndex, 0, removed);
      
      return newWidgets;
    });
  };

  const onResize = useCallback((id: string, size: WidgetSize) => {
    setWidgets(prevWidgets => 
      prevWidgets.map(widget => 
        widget.id === id
          ? { 
              ...widget, 
              defaultSize: { 
                w: Math.max(1, Math.min(12, Math.round(size.w))),
                h: Math.max(1, Math.min(4, Math.round(size.h)))
              } 
            } 
          : widget
      )
    );
  }, []);

  const handleResize = useCallback((id: string, e: any, { size }: ResizeCallbackData) => {
    onResize(id, { w: size.width / 100, h: size.height / 100 });
  }, [onResize]);

  const gridProps = {
    container: true,
    spacing: 2,
    sx: {
      width: '100%',
      margin: 0,
      '& .react-resizable': {
        position: 'relative',
      },
      '& .react-resizable-handle': {
        position: 'absolute',
        width: 20,
        height: 20,
        bottom: 0,
        right: 0,
        background: `url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2IDYiIHN0eWxlPSJiYWNrZ3JvdW5kLWNvbG9yOiNmZmZmZmYwMCIgeD0iMHB4IiB5PSIwcHgiIHdpZHRoPSI2cHgiIGhlaWdodD0iNnB4Ij48ZyBvcGFjaXR5PSIwLjMwMiI+PHBhdGggZD0iTSA2IDYgTCAwIDYgTCAwIDQuMiBMIDQgNC4yIEwgNC4yIDQuMiBaIiBmaWxsPSIjMDAwMDAwIi8+PC9nPjwvc3ZnPg==')`,
        backgroundPosition: 'bottom right',
        padding: '0 3px 3px 0',
        backgroundRepeat: 'no-repeat',
        backgroundOrigin: 'content-box',
        boxSizing: 'border-box',
        cursor: 'se-resize',
      },
    },
  };

  // Load saved layout from localStorage on component mount
  useEffect(() => {
    const savedLayout = typeof window !== 'undefined' ? localStorage.getItem('dashboardLayout') : null;
    if (savedLayout) {
      try {
        const parsedLayout = JSON.parse(savedLayout);
        // Map the saved layout back to full widget objects
        const fullWidgets = parsedLayout.map((savedWidget: any) => {
          const originalWidget = widgets.find(w => w.id === savedWidget.id);
          return originalWidget || {
            id: savedWidget.id,
            title: savedWidget.title,
            content: getDefaultContent(savedWidget.id),
            defaultSize: savedWidget.defaultSize
          };
        });
        setWidgets(fullWidgets);
      } catch (e) {
        console.error('Failed to load saved layout', e);
      }
    }
  }, []);

  // Helper function to get default content for a widget
  const getDefaultContent = (widgetId: string) => {
    switch (widgetId) {
      case 'balance':
        return <BalanceWidget />;
      case 'pnl':
        return <PnlWidget />;
      case 'strategies':
        return <StrategiesWidget />;
      case 'prices':
        return <PricesWidget />;
      case 'chart':
        return <Box sx={{ flex: 1, minHeight: 400, width: '100%' }}><TVChartWidget /></Box>;
      default:
        return null;
    }
  };

  // Save layout to localStorage when it changes
  useEffect(() => {
    if (typeof window !== 'undefined') {
      // Create a simplified version of widgets for storage
      const widgetsForStorage = widgets.map(({ id, title, defaultSize }) => ({
        id,
        title,
        defaultSize
      }));
      localStorage.setItem('dashboardLayout', JSON.stringify(widgetsForStorage));
    }
  }, [widgets]);

  return (
    <Container maxWidth={false} sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ py: 3 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Dashboard
        </Typography>
      </Box>
      
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
          gap: 2,
          flex: 1,
          minHeight: 0,
          overflowY: 'auto',
          p: 1,
          '& .react-resizable': {
            position: 'relative',
            width: '100%',
            height: '100%',
          },
          '& .react-resizable-handle': {
            position: 'absolute',
            width: 20,
            height: 20,
            bottom: 0,
            right: 0,
            background: `url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2IDYiIHN0eWxlPSJiYWNrZ3JvdW5kLWNvbG9yOiNmZmZmZmYwMCIgeD0iMHB4IiB5PSIwcHgiIHdpZHRoPSI2cHgiIGhlaWdodD0iNnB4Ij48ZyBvcGFjaXR5PSIwLjMwMiI+PHBhdGggZD0iTSA2IDYgTCAwIDYgTCAwIDQuMiBMIDQgNC4yIEwgNC4yIDQuMiBaIiBmaWxsPSIjMDAwMDAwIi8+PC9nPjwvc3ZnPg==')`,
            backgroundPosition: 'bottom right',
            padding: '0 3px 3px 0',
            backgroundRepeat: 'no-repeat',
            backgroundOrigin: 'content-box',
            boxSizing: 'border-box',
            cursor: 'se-resize',
          },
          '&::-webkit-scrollbar': {
            width: 8,
            height: 8,
          },
          '&::-webkit-scrollbar-track': {
            bgcolor: 'background.paper',
          },
          '&::-webkit-scrollbar-thumb': {
            bgcolor: 'action.selected',
            borderRadius: 1,
            '&:hover': {
              bgcolor: 'action.active',
            },
          },
        }}
      >
        {widgets.map((widget) => (
          <Resizable
            key={widget.id}
            width={widget.defaultSize.w * 100}
            height={widget.defaultSize.h * 150}
            onResize={(e, data) => handleResize(widget.id, e, data)}
            onResizeStart={() => setIsDragging(true)}
            onResizeStop={() => setIsDragging(false)}
            resizeHandles={['se']}
            minConstraints={[100, 150]}
            maxConstraints={[1200, 600]}
            draggableOpts={{ enableUserSelectHack: false }}
          >
            <Box
              ref={(el: HTMLDivElement | null) => (widgetRefs.current[widget.id] = el)}
              draggable={!isDragging}
              onDragStart={(e) => !isDragging && handleDragStart(e, widget)}
              onDragOver={handleDragOver}
              onDrop={(e) => handleDrop(e, widget.id)}
              sx={{
                ...widgetStyles,
                width: '100%',
                height: '100%',
                minHeight: '100%',
                '&:hover': {
                  boxShadow: 3,
                  transform: 'translateY(-2px)',
                },
                cursor: 'grab',
                '&:active': {
                  cursor: 'grabbing',
                },
              }}
            >
              <Typography variant="h6" sx={{ fontWeight: 'medium' }}>
                {widget.title}
              </Typography>
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Box 
                  className="resize-handle"
                  onMouseDown={(e) => handleResizeStart(e, widget)}
                  onDragStart={(e) => e.preventDefault()}
                  sx={{
                    '&:active': {
                      cursor: 'nwse-resize',
                    },
                  }}
                />
              </Box>
            </Box>
            <Box sx={{ flex: 1, overflow: 'hidden' }}>
              {widget.content}
            </Box>
          </Box>
        </Resizable>
      ))}
    </Box>
  </Container>
);
      </Box>
    </Container>
  );
}
