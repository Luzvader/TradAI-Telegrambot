"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { Box, Container, Typography } from "@mui/material";
import dynamic from 'next/dynamic';
import { Resizable, ResizableProps, ResizeCallbackData } from 'react-resizable';
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

interface WidgetLayout extends Omit<WidgetProps, 'content'> {
  // For localStorage serialization
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
  overflow: 'hidden',
  '&:active': {
    cursor: 'grabbing',
  },
  transition: 'all 0.2s ease',
  '&:hover': {
    boxShadow: 3,
    transform: 'translateY(-2px)',
    borderColor: 'primary.main',
    '& .resize-handle': {
      opacity: 1,
    },
  },
  '& .react-resizable': {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    '&:hover': {
      '& .resize-handle': {
        opacity: 1,
      },
    },
  },
  '& .resize-handle': {
    position: 'absolute',
    right: 0,
    bottom: 0,
    width: 24,
    height: 24,
    cursor: 'nwse-resize',
    opacity: 0,
    transition: 'opacity 0.2s ease',
    '&:after': {
      content: '""',
      position: 'absolute',
      right: 4,
      bottom: 4,
      width: 12,
      height: 12,
      borderRight: '2px solid',
      borderBottom: '2px solid',
      borderColor: 'action.active',
      transition: 'border-color 0.2s ease',
    },
    '&:hover:after': {
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
  const [isResizing, setIsResizing] = useState(false);

  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const [dragPreview, setDragPreview] = useState<{width: number; height: number} | null>(null);

  const handleDragStart = (e: React.DragEvent<HTMLDivElement>, widget: WidgetProps) => {
    if (isResizing) {
      e.preventDefault();
      return;
    }
    setDraggedWidget(widget);
    
    // Set drag image for better visual feedback
    const target = e.currentTarget;
    setDragPreview({
      width: target.offsetWidth,
      height: target.offsetHeight
    });
    
    // Create a custom drag image for better visual feedback
    const dragImage = document.createElement('div');
    dragImage.style.position = 'absolute';
    dragImage.style.top = '-1000px';
    dragImage.style.left = '-1000px';
    dragImage.style.width = `${target.offsetWidth}px`;
    dragImage.style.height = `${target.offsetHeight}px`;
    dragImage.style.backgroundColor = 'rgba(25, 118, 210, 0.1)';
    dragImage.style.border = '2px dashed #1976d2';
    dragImage.style.borderRadius = '4px';
    document.body.appendChild(dragImage);
    
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setDragImage(dragImage, 0, 0);
    
    // Clean up the drag image after a short delay
    setTimeout(() => document.body.removeChild(dragImage), 0);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>, targetId: string) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'move';
    
    if (draggedWidget && draggedWidget.id !== targetId) {
      setDragOverId(targetId);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>, targetId: string) => {
    e.preventDefault();
    if (isResizing || !draggedWidget || draggedWidget.id === targetId) {
      setDragOverId(null);
      return;
    }

    setWidgets(prevWidgets => {
      const newWidgets = [...prevWidgets];
      const draggedIndex = newWidgets.findIndex(w => w.id === draggedWidget.id);
      const targetIndex = newWidgets.findIndex(w => w.id === targetId);
      
      if (draggedIndex === -1 || targetIndex === -1) return prevWidgets;
      
      const [removed] = newWidgets.splice(draggedIndex, 1);
      newWidgets.splice(targetIndex, 0, removed);
      
      // Save to localStorage
      saveWidgetsToLocalStorage(newWidgets);
      
      return newWidgets;
    });
    
    setDragOverId(null);
  };

  const saveWidgetsToLocalStorage = useCallback((widgetsToSave: WidgetProps[]) => {
    if (typeof window !== 'undefined') {
      const widgetsForStorage: WidgetLayout[] = widgetsToSave.map(({ id, title, defaultSize }) => ({
        id,
        title,
        defaultSize
      }));
      localStorage.setItem('dashboardLayout', JSON.stringify(widgetsForStorage));
    }
  }, []);

  // Track the current widget being resized and its preview size
  const [resizingWidget, setResizingWidget] = useState<{
    id: string;
    size: { width: number; height: number };
    startSize: { width: number; height: number };
  } | null>(null);

  const handleResizeStart = useCallback((id: string) => {
    setIsResizing(true);
    const widget = widgets.find(w => w.id === id);
    if (!widget) return;
    
    const startWidth = widget.defaultSize.w * 100;
    const startHeight = widget.defaultSize.h * 150;
    
    setResizingWidget({
      id,
      size: { width: startWidth, height: startHeight },
      startSize: { width: startWidth, height: startHeight }
    });
  }, [widgets]);

  const handleResize = useCallback((id: string, _e: React.SyntheticEvent, { size }: ResizeCallbackData) => {
    setResizingWidget(prev => {
      if (!prev || prev.id !== id) return prev;
      
      // Calculate grid-aligned size
      const gridColWidth = 100; // Width of one grid column in pixels
      const gridRowHeight = 150; // Height of one grid row in pixels
      
      // Snap to nearest grid multiple
      const snappedWidth = Math.max(
        100, // min width
        Math.min(1200, // max width
          Math.round(size.width / gridColWidth) * gridColWidth
        )
      );
      
      const snappedHeight = Math.max(
        150, // min height
        Math.min(600, // max height
          Math.round(size.height / gridRowHeight) * gridRowHeight
        )
      );
      
      return {
        ...prev,
        size: { width: snappedWidth, height: snappedHeight }
      };
    });
  }, []);

  const handleResizeStop = useCallback((id: string) => {
    setIsResizing(false);
    
    if (!resizingWidget || resizingWidget.id !== id) return;
    
    setWidgets(prevWidgets => {
      const newWidgets = prevWidgets.map(widget => {
        if (widget.id === id) {
          const newWidth = Math.max(1, Math.min(12, Math.round(resizingWidget.size.width / 100)));
          const newHeight = Math.max(1, Math.min(4, Math.round(resizingWidget.size.height / 150)));
          
          return {
            ...widget,
            defaultSize: {
              w: newWidth,
              h: newHeight
            }
          };
        }
        return widget;
      });
      
      // Save to localStorage after resize completes
      saveWidgetsToLocalStorage(newWidgets);
      return newWidgets;
    });
    
    setResizingWidget(null);
  }, [resizingWidget, saveWidgetsToLocalStorage]);

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

  const getDefaultContent = (widgetId: string): React.ReactNode => {
    const content = {
      'balance': <BalanceWidget />,
      'pnl': <PnlWidget />,
      'strategies': <StrategiesWidget />,
      'prices': <PricesWidget />,
      'chart': <Box sx={{ flex: 1, minHeight: 400, width: '100%' }}><TVChartWidget /></Box>,
    }[widgetId];
    
    return content || null;
  };

  // Load saved layout from localStorage on component mount
  useEffect(() => {
    try {
      const savedLayout = typeof window !== 'undefined' ? localStorage.getItem('dashboardLayout') : null;
      if (savedLayout) {
        const parsedLayout = JSON.parse(savedLayout) as WidgetLayout[];
        // Only update if we have a valid layout
        if (Array.isArray(parsedLayout) && parsedLayout.length > 0) {
          // Map the saved layout back to full widget objects
          const fullWidgets = parsedLayout.map(savedWidget => ({
            ...savedWidget,
            content: getDefaultContent(savedWidget.id),
          }));
          setWidgets(fullWidgets);
        }
      }
    } catch (e) {
      console.error('Failed to load saved layout', e);
      // Reset to default layout if there's an error
      localStorage.removeItem('dashboardLayout');
    }
  }, []);

  return (
    <Container maxWidth={false} sx={{ height: '100vh', display: 'flex', flexDirection: 'column', p: 2 }}>
      <Box sx={{ py: 2 }}>
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
            background: `url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2IDYiIHN0eWxlPSJiYWNrZ3JvdW5kLWNvbG9yOiNmZmZmZmYwMCIgeD0iMHB4IiB5PSIwcHgiIHdpZHRoPSI2cHgiIGhlaWdodD0iNnB4Ij48ZyBvcGFjaXR5PSIwLjMwMiI+PHBhdGggZD0iTSA2IDYgTCAwIDYgTCAwIDQuMiBMIDQgNC4yIEwgNC4yIDQuMiBaIiBmaWxsPSIjMDAwMDAwIi8+PC9nPjwvc3ZnPg==`,
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
          <Box
            key={widget.id}
            sx={{
              ...widgetStyles,
              gridColumn: `span ${Math.min(12, widget.defaultSize.w)}`,
              gridRow: `span ${widget.defaultSize.h}`,
              minHeight: '150px',
              display: 'flex',
              flexDirection: 'column',
              position: 'relative',
              '&:hover .resize-handle': {
                opacity: 1,
              },
            }}
          >
            <Box
              ref={(el: HTMLDivElement | null) => (widgetRefs.current[widget.id] = el)}
              draggable={!isResizing}
              onDragStart={(e) => !isResizing && handleDragStart(e, widget)}
              onDragOver={(e) => handleDragOver(e, widget.id)}
              onDrop={(e) => handleDrop(e, widget.id)}
              onDragLeave={() => setDragOverId(null)}
              onDragEnd={() => setDragOverId(null)}
              sx={{
                width: '100%',
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                overflow: 'hidden',
                opacity: dragOverId === widget.id ? 0.5 : 1,
                transition: 'opacity 0.2s ease',
                border: dragOverId === widget.id ? '2px dashed #1976d2' : 'none',
                borderRadius: '4px',
              }}
            >
              <Box sx={{ 
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                p: 1,
                borderBottom: '1px solid',
                borderColor: 'divider',
              }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 'medium' }}>
                  {widget.title}
                </Typography>
              </Box>
              <Box sx={{ flex: 1, overflow: 'auto', p: 1 }}>
                {widget.content}
              </Box>
            </Box>
            <Resizable
              width={resizingWidget?.id === widget.id ? resizingWidget.size.width : widget.defaultSize.w * 100}
              height={resizingWidget?.id === widget.id ? resizingWidget.size.height : widget.defaultSize.h * 150}
              onResize={(e: React.SyntheticEvent, data: ResizeCallbackData) => handleResize(widget.id, e, data)}
              onResizeStart={() => handleResizeStart(widget.id)}
              onResizeStop={() => handleResizeStop(widget.id)}
              resizeHandles={['se']}
              minConstraints={[100, 150]}
              maxConstraints={[1200, 600]}
              draggableOpts={{ enableUserSelectHack: false }}
              className="resizable-container"
              style={{
                // Reset any inherited styles that might interfere
                background: 'transparent',
                position: 'relative',
              }}
            >
              <div 
                className="resize-handle" 
                style={{
                  position: 'absolute',
                  bottom: 0,
                  right: 0,
                  width: 20,
                  height: 20,
                  background: 'transparent',
                  cursor: 'se-resize',
                  opacity: 0,
                  transition: 'opacity 0.2s',
                  zIndex: 10, // Ensure handle is above other elements
                }}
                onMouseDown={(e) => {
                  // Prevent drag events from firing when resizing
                  e.stopPropagation();
                }}
              />
            </Box>
          </Box>
        ))}
      </Box>
    </Container>
  );
}
