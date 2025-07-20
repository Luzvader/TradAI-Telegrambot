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
  defaultSize: WidgetSize;
  content: React.ReactNode;
}

// Widget Component
const Widget = React.memo(({ 
  id, 
  title, 
  content, 
  defaultSize,
  onResize,
  onResizeStop,
  onDragStart,
  onDragOver,
  onDrop,
  isDraggingOver,
  isResizing
}: WidgetLayout & {
  onResize: (e: React.SyntheticEvent, data: ResizeCallbackData) => void;
  onResizeStop: (e: React.SyntheticEvent, data: ResizeCallbackData) => void;
  onDragStart: (e: React.DragEvent<HTMLDivElement>) => void;
  onDragOver: (e: React.DragEvent<HTMLDivElement>) => void;
  onDrop: (e: React.DragEvent<HTMLDivElement>) => void;
  isDraggingOver: boolean;
  isResizing: boolean;
}) => {
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
      '& .resize-handle': { opacity: 1 }
    },
    '& .resize-handle': {
      position: 'absolute',
      bottom: 0,
      right: 0,
      width: 20,
      height: 20,
      background: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'20\' height=\'20\' viewBox=\'0 0 20 20\'%3E%3Cpath fill=\'%23999\' d=\'M14 14v2h2v-2h-2zm-4 0v2h2v-2h-2zm-4 0v2h2v-2H6zm8-4v2h2v-2h-2zm-4 0v2h2v-2h-2zm-4 0v2h2v-2H6z\'/%3E%3C/svg%3E") no-repeat bottom right',
      cursor: 'se-resize',
      opacity: 0,
      transition: 'opacity 0.2s',
    }
  };

  return (
    <Resizable
      width={defaultSize.w * 100}
      height={defaultSize.h * 150}
      onResize={onResize}
      onResizeStop={onResizeStop}
      resizeHandles={['se']}
      minConstraints={[100, 150]}
      maxConstraints={[1200, 900]}
    >
      <Box
        sx={widgetStyles}
        draggable={!isResizing}
        onDragStart={onDragStart}
        onDragOver={onDragOver}
        onDrop={onDrop}
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
        <div className="resize-handle" />
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

    setWidgets(initialWidgets);
  }, []);

  // Event Handlers
  const handleResizeStart = useCallback(() => {
    setIsResizing(true);
  }, []);

  const handleResizeStop = useCallback((widgetId: string) => 
    (e: React.SyntheticEvent, data: ResizeCallbackData) => {
      setIsResizing(false);
      
      setWidgets(prevWidgets => 
        prevWidgets.map(widget => 
          widget.id === widgetId 
            ? { 
                ...widget, 
                defaultSize: { 
                  w: Math.max(1, Math.min(12, Math.round(data.size.width / 100))),
                  h: Math.max(1, Math.min(12, Math.round(data.size.height / 150)))
                } 
              } 
            : widget
        )
      );
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
        {widgets.map((widget) => (
          <Box
            key={widget.id}
            sx={{
              gridColumn: `span ${Math.min(12, widget.defaultSize.w)}`,
              gridRow: 'span 1',
              minHeight: '150px',
            }}
          >
            <Widget
              {...widget}
              onResize={handleResizeStart}
              onResizeStop={handleResizeStop(widget.id)}
              onDragStart={(e) => handleDragStart(e, widget.id)}
              onDragOver={(e) => handleDragOver(e, widget.id)}
              onDrop={(e) => handleDrop(e, widget.id)}
              isDraggingOver={draggedWidgetId === widget.id}
              isResizing={isResizing}
            />
          </Box>
        ))}
      </Box>
    </Container>
  );
};

export default Dashboard;