"use client";
import { Box, Paper } from "@mui/material";
import { ReactNode } from "react";

interface Props {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}

export default function WidgetFrame({ title, children, action }: Props) {
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
      }}
    >
      <Box sx={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'flex-start',
        mb: 1,
        minHeight: '40px',
        '& h4': {
          m: 0,
          fontSize: '1.25rem',
          fontWeight: 500,
          lineHeight: '40px',
          letterSpacing: '0.0075em',
          paddingTop: '4px' // Ajuste fino para alinear con el selector
        },
        '& > *:last-child': {
          marginTop: '8px' // Ajuste para alinear el selector con el texto
        }
      }}>
        <h4>{title}</h4>
        {action && (
          <Box sx={{ display: 'flex', alignItems: 'center', height: '100%' }}>
            {action}
          </Box>
        )}
      </Box>
      {children}
    </Paper>
  );
}
