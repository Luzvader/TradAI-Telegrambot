"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { Box, Container, Typography, IconButton, SxProps, Theme } from '@mui/material';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import { Resizable, ResizeCallbackData } from 'react-resizable';
import 'react-resizable/css/styles.css';

// Types
interface WidgetSize {
  w: number;  // Width in grid units (1-12)
  h: number;  // Height in grid units
}

interface WidgetLayout {
  id: string;
  title: string;
  content: React.ReactNode;
  defaultSize: WidgetSize;
}

interface WidgetProps extends Omit<WidgetLayout, 'content'> {
  content: React.ReactNode;
  onResize: (e: React.SyntheticEvent, data: ResizeCallbackData) => void;
  onResizeStart: () => void;
  onResizeStop: (e: React.SyntheticEvent, data: ResizeCallbackData) => void;
  onDragStart: (e: React.DragEvent) => void;
  onDragOver: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent) => void;
  isDraggingOver: boolean;
  isResizing: boolean;
}

// Widget Component
const Widget: React.FC<WidgetProps> = React.memo(({
  id,
  title,
  content,
  defaultSize,
  onResize,
  onResizeStart,
  onResizeStop,
  onDragStart,
  onDragOver,
  onDrop,
  isDraggingOver,
  isResizing,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [size, setSize] = useState({
    width: defaultSize.w * 100,
    height: defaultSize.h * 150,
  });

  // Update size when defaultSize changes
  useEffect(() => {
    setSize({
      width: Math.max(100, defaultSize.w * 100),
      height: Math.max(150, defaultSize.h * 150),
    });
  }, [defaultSize]);

  // Handle drag start
  const handleDragStart = (e: React.DragEvent) => {
    if (isResizing) return;
    e.dataTransfer.setData('text/plain', id);
    setIsDragging(true);
    onDragStart(e);
  };

  // Handle drag end
  const handleDragEnd = () => {
    setIsDragging(false);
    document.body.style.cursor = 'default';
  };

  // Handle drag over
  const handleDragOver = (e: React.DragEvent) => {
    if (isResizing) return;
    e.preventDefault();
    onDragOver(e);
  };

  // Handle drop
  const handleDrop = (e: React.DragEvent) => {
    if (isResizing) return;
    e.preventDefault();
    onDrop(e);
  };

  // Handle resize
  const handleResize = (e: React.SyntheticEvent, data: ResizeCallbackData) => {
    setSize(data.size);
    onResize(e, data);
  };

  const widgetStyles: SxProps<Theme> = {
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
    transition: 'all 0.2s ease',
    opacity: isDraggingOver ? 0.6 : 1,
    transform: isDraggingOver ? 'scale(0.98)' : 'none',
    '&:active': { cursor: 'grabbing' },
    '&:hover': {
      boxShadow: 3,
      '& .resize-handle-bottom, & .resize-handle-corner': { opacity: 1 }
    },
    '& .resize-handle-bottom, & .resize-handle-corner': {
      position: 'absolute',
      opacity: 0,
      transition: 'opacity 0.2s',
    },
    '& .resize-handle-bottom': {
      left: 0,
      right: 20, // Don't overlap with corner handle
      bottom: 0,
      height: 10,
      cursor: 's-resize',
      '&:hover': {
        background: 'linear-gradient(0deg, rgba(0,0,0,0.05) 0%, rgba(0,0,0,0) 100%)',
      },
    },
    '& .resize-handle-corner': {
      bottom: 0,
      right: 0,
      width: 20,
      height: 20,
      background: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'20\' height=\'20\' viewBox=\'0 0 20 20\'%3E%3Cpath fill=\'%23999\' d=\'M14 14v2h2v-2h-2zm-4 0v2h2v-2h-2zm-4 0v2h2v-2H6zm8-4v2h2v-2h-2zm-4 0v2h2v-2h-2zm-4 0v2h2v-2H6z\'/%3E%3C/svg%3E") no-repeat bottom right',
      cursor: 'se-resize',
    }
  };

  return (
    <Resizable
      width={size.width}
      height={size.height}
      onResize={handleResize}
      onResizeStart={onResizeStart}
      onResizeStop={onResizeStop}
      minConstraints={[100, 150]}
      maxConstraints={[1200, 900]}
      resizeHandles={['s', 'se']}
    >
      <Box
        sx={widgetStyles}
        draggable={!isResizing}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        data-widget-id={id}
      >
        <Box 
          sx={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center',
            mb: 2,
            pb: 1,
            borderBottom: '1px solid',
            borderColor: 'divider',
            cursor: 'move',
          }}
        >
          <Typography variant="subtitle1" fontWeight="medium">
            {title}
          </Typography>
          <IconButton size="small" edge="end">
            <MoreVertIcon fontSize="small" />
          </IconButton>
        </Box>
        <Box sx={{ flex: 1, overflow: 'auto' }}>
          {content}
        </Box>
        <div className="resize-handle-bottom" />
      <div className="resize-handle-corner" />
      </Box>
    </Resizable>
  );
});

Widget.displayName = 'Widget';

// Main Dashboard Component
const Dashboard = () => {
  // Widget state
  const [widgets, setWidgets] = useState<WidgetLayout[]>([]);
  const [isResizing, setIsResizing] = useState(false);
  const [draggedWidgetId, setDraggedWidgetId] = useState<string | null>(null);
  const [widgetSizes, setWidgetSizes] = useState<Record<string, { width: number; height: number }>>({});

  // Initialize widgets
  useEffect(() => {
    const initialWidgets: WidgetLayout[] = [
      {
        id: 'balance',
        title: 'Balance',
        defaultSize: { w: 4, h: 3 },
        content: (
          <Box sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="h4" color="primary" gutterBottom>
              $12,450.75
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Total Balance
            </Typography>
          </Box>
        ),
      },
      {
        id: 'prices',
        title: 'Market Prices',
        defaultSize: { w: 4, h: 3 },
        content: (
          <Box sx={{ p: 2 }}>
            <Typography variant="body1" gutterBottom>BTC: $42,380.50</Typography>
            <Typography variant="body1" gutterBottom>ETH: $2,340.20</Typography>
            <Typography variant="body1">SOL: $98.75</Typography>
          </Box>
        ),
      },
      {
        id: 'pnl',
        title: 'P&L',
        defaultSize: { w: 4, h: 3 },
        content: (
          <Box sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="h5" color="success.main" gutterBottom>
              +$1,234.56
            </Typography>
            <Typography variant="body2" color="text.secondary">
              24h Profit/Loss
            </Typography>
          </Box>
        ),
      },
    ];

    // Initialize widget sizes based on default sizes
    const initialSizes = initialWidgets.reduce((acc, widget) => ({
      ...acc,
      [widget.id]: { 
        width: widget.defaultSize.w * 100,
        height: widget.defaultSize.h * 150
      }
    }), {});

    setWidgetSizes(initialSizes);
    setWidgets(initialWidgets);
  }, []);

  // Event Handlers
  const handleResize = useCallback((widgetId: string, _: React.SyntheticEvent, { size }: ResizeCallbackData) => {
    setWidgetSizes(prevSizes => ({
      ...prevSizes,
      [widgetId]: size
    }));
  }, []);

  const handleResizeStart = useCallback(() => {
    setIsResizing(true);
  }, []);

  const handleResizeStop = useCallback((widgetId: string) => 
    (e: React.SyntheticEvent, data: ResizeCallbackData) => {
      setIsResizing(false);
      
      // Calculate grid units from pixel sizes
      const gridCols = Math.max(1, Math.min(12, Math.round(data.size.width / 100)));
      const gridRows = Math.max(1, Math.min(12, Math.round(data.size.height / 150)));
      
      // Update both the widget sizes and the grid layout
      setWidgets(prevWidgets => 
        prevWidgets.map(widget => 
          widget.id === widgetId 
            ? { 
                ...widget, 
                defaultSize: { 
                  w: gridCols,
                  h: gridRows
                } 
              } 
            : widget
        )
      );
      
      // Update the widget sizes for smooth resizing
      setWidgetSizes(prevSizes => ({
        ...prevSizes,
        [widgetId]: {
          width: gridCols * 100,
          height: gridRows * 150
        }
      }));
    },
    []
  );

  const handleDragStart = useCallback((e: React.DragEvent, widgetId: string) => {
    if (isResizing) return;
    e.dataTransfer.setData('text/plain', widgetId);
    setDraggedWidgetId(widgetId);
    document.body.style.cursor = 'grabbing';
  }, [isResizing]);

  const handleDragOver = useCallback((e: React.DragEvent, targetWidgetId: string) => {
    e.preventDefault();
    if (draggedWidgetId === targetWidgetId) return;
  }, [draggedWidgetId]);

  const handleDrop = useCallback((e: React.DragEvent, targetWidgetId: string) => {
    e.preventDefault();
    const sourceWidgetId = e.dataTransfer.getData('text/plain');
    
    if (sourceWidgetId === targetWidgetId) return;
    
    setWidgets(prevWidgets => {
      const newWidgets = [...prevWidgets];
      const sourceIndex = newWidgets.findIndex(w => w.id === sourceWidgetId);
      const targetIndex = newWidgets.findIndex(w => w.id === targetWidgetId);
      
      if (sourceIndex !== -1 && targetIndex !== -1) {
        const [movedWidget] = newWidgets.splice(sourceIndex, 1);
        newWidgets.splice(targetIndex, 0, movedWidget);
        return newWidgets;
      }
      
      return prevWidgets;
    });
    
    document.body.style.cursor = '';
    setDraggedWidgetId(null);
  }, []);

  // Cleanup effect
  useEffect(() => {
    const cleanup = () => {
      document.body.style.cursor = '';
    };
    
    window.addEventListener('dragend', cleanup);
    return () => {
      window.removeEventListener('dragend', cleanup);
      cleanup();
    };
  }, []);

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4, p: 2 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        Dashboard
      </Typography>
      
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: 'repeat(12, 1fr)',
          gap: 2,
          width: '100%',
          minHeight: '80vh',
        }}
      >
        {widgets.map((widget) => {
          const size = widgetSizes[widget.id] || {
            width: widget.defaultSize.w * 100,
            height: widget.defaultSize.h * 150
          };
          
          return (
            <Box
              key={widget.id}
              sx={{
                gridColumn: `span ${Math.min(12, widget.defaultSize.w)}`,
                gridRow: `span ${widget.defaultSize.h}`,
                minHeight: `${widget.defaultSize.h * 50}px`,
              }}
            >
              <Widget
                {...widget}
                defaultSize={{
                  w: size.width / 100,
                  h: size.height / 150
                }}
                onResize={(e, data) => handleResize(widget.id, e, data)}
                onResizeStart={handleResizeStart}
                onResizeStop={handleResizeStop(widget.id)}
                onDragStart={(e) => handleDragStart(e, widget.id)}
                onDragOver={(e) => handleDragOver(e, widget.id)}
                onDrop={(e) => handleDrop(e, widget.id)}
                isDraggingOver={draggedWidgetId === widget.id}
                isResizing={isResizing}
              />
            </Box>
          );
        })}
      </Box>
    </Container>
  );
};

export default Dashboard;