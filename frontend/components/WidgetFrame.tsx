"use client";
import { Box, Paper } from "@mui/material";
import { ReactNode } from "react";

interface Props {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  sx?: any;
}

export default function WidgetFrame({ title, children, action, sx = {} }: Props) {
  return (
    <Paper
      elevation={3}
      sx={{
        p: 1,
        height: "100%",
        boxSizing: "border-box",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        '& > *': {
          minHeight: 0, // Prevent flex children from overflowing
        },
        ...sx
      }}
    >
      <Box sx={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'flex-start',
        mb: 1,
        minHeight: '40px',
        flexShrink: 0, // Prevent header from shrinking
        '& h4': {
          m: 0,
          fontSize: '1.25rem',
          fontWeight: 500,
          lineHeight: '40px',
          letterSpacing: '0.0075em',
          paddingTop: '4px',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis'
        },
        '& > *:last-child': {
          marginTop: '8px',
          flexShrink: 0 // Prevent action controls from shrinking
        }
      }}>
        <h4>{title}</h4>
        {action && (
          <Box sx={{ display: 'flex', alignItems: 'center', height: '100%' }}>
            {action}
          </Box>
        )}
      </Box>
      <Box sx={{ 
        flex: 1,
        minHeight: 0, // Allow this container to shrink below its content size
        overflow: 'auto', // Changed to auto to allow scrolling if needed
        '& > *': {
          minHeight: '100%',
          width: '100%',
          boxSizing: 'border-box'
        }
      }}>
        {children}
      </Box>
    </Paper>
  );
}
