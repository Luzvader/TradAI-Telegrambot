"use client";

import { useState, useEffect } from "react";
import useSWR from "swr";
import { fetcher } from "../utils/fetcher";
import { Box, Typography, Paper, useTheme } from "@mui/material";
import { Sparklines, SparklinesLine, SparklinesReferenceLine } from 'react-sparklines';

interface WalletResponse {
  type: string | null;
  balances: Record<string, number>;
}

interface PnlResp {
  pnl: number;
  pnlPercent: number;
  history?: number[];
}

export default function BalancePnlWidget() {
  // Fetch wallet data
  const { data: walletData, error: walletError, isLoading: walletLoading } = 
    useSWR<WalletResponse>("/api/wallet", fetcher, { revalidateOnFocus: false });
  
  // Fetch PnL data
  const { data: pnlData, error: pnlError, isLoading: pnlLoading } = 
    useSWR<PnlResp>("/api/pnl", fetcher);

  const theme = useTheme();
  const balance = walletError ? 10000 : walletData?.balances?.USDT ?? 0;
  // Get PnL values from data or use zero values if not available
  const pnl = pnlData?.pnl ?? 0;
  const pnlPercent = pnlData?.pnlPercent ?? 0;
  const pnlColor = pnl >= 0 ? theme.palette.success.main : theme.palette.error.main;
  const pnlSign = pnl >= 0 ? "+" : "";
  
  // Generate real-looking cumulative PnL data starting from 0
  const generateChartData = (points = 24) => {
    // If we have history data from the API, use it
    if (pnlData?.history?.length) {
      return pnlData.history;
    }
    
    // Otherwise generate sample data based on current PnL
    const data = [0]; // Start at 0
    const finalValue = pnl; // We want to show the PnL change, not absolute value
    
    // Generate points with realistic market-like movement
    const volatility = 0.4; // Controls how much the line wiggles
    
    for (let i = 1; i < points; i++) {
      const progress = i / (points - 1);
      const targetValue = finalValue * progress;
      
      // Add realistic market noise that decreases towards the end
      const noise = Math.sin(progress * Math.PI * 3) * volatility * Math.abs(finalValue) * 0.5;
      const randomFactor = 1 + (Math.random() * 2 - 1) * 0.01; // Small random noise
      
      const currentValue = targetValue * randomFactor + noise;
      data.push(currentValue);
    }
    
    // Ensure the last point matches the final PnL exactly
    if (data.length > 1) {
      data[data.length - 1] = finalValue;
    }
    
    return data;
  };
  
  // Generate or use provided history
  const pnlHistory = pnlData?.history || generateChartData(20);
  
  // Calculate min and max for the chart
  const minPnl = Math.min(...pnlHistory);
  const maxPnl = Math.max(...pnlHistory);
  const range = maxPnl - minPnl || 1; // Avoid division by zero

  return (
    <Box sx={{ 
      display: "flex", 
      flexDirection: "column",
      height: '100%',
      boxSizing: 'border-box',
      position: 'relative',
      overflow: 'hidden',
      '& .MuiPaper-root': {
        p: 2,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'flex-start',
        position: 'relative',
        zIndex: 1,
        backgroundColor: theme.palette.background.paper + '33', // 20% transparency (33 in hex)
        backdropFilter: 'none',
      },
      '& .sparkline-container': {
        position: 'absolute',
        left: 0,
        right: 0,
        bottom: 0,
        height: '60%',
        opacity: 0.6, // Increased opacity for better visibility
        zIndex: 0,
        display: { xs: 'none', sm: 'block' }, // Hide on mobile
      },
      '& .sparkline': {
        width: '100%',
        height: '100%',
      },
      '& .content-wrapper': {
        position: 'relative',
        zIndex: 2,
        transform: 'translateY(-25%)',
        '@media (max-width: 600px)': {
          transform: 'none',
        }
      }
    }}>
      {/* Background PnL Chart */}
      <Box className="sparkline-container">
        <Sparklines 
          data={pnlHistory} 
          className="sparkline" 
          margin={0}
          min={Math.min(0, ...pnlHistory) * 1.1} // Add 10% padding below minimum
          max={Math.max(0, ...pnlHistory) * 1.1} // Add 10% padding above maximum
        >
          <defs>
            <linearGradient id="sparkline-gradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={pnlColor} stopOpacity="0.8" />
              <stop offset="100%" stopColor={pnlColor} stopOpacity="0.1" />
            </linearGradient>
          </defs>
          <SparklinesLine 
            style={{ 
              stroke: pnlColor, 
              strokeWidth: 2.5,
              fill: 'url(#sparkline-gradient)',
              strokeLinecap: 'round',
              strokeLinejoin: 'round'
            }} 
          />
          <SparklinesReferenceLine 
            type="avg" 
            style={{ 
              stroke: pnlColor, 
              strokeDasharray: '3, 3',
              opacity: 0.6
            }} 
          />
        </Sparklines>
      </Box>

      <Paper elevation={2}>
        <Box className="content-wrapper">
          <Box sx={{ mb: 3 }}>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              Balance Total
            </Typography>
            <Typography variant="h4" fontWeight="bold" gutterBottom>
              {balance.toLocaleString('en-US', { style: 'currency', currency: 'USD' })}
            </Typography>
          </Box>
          
          <Box>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              PnL (24h)
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="h6" color={pnlColor}>
                {pnlSign}{pnl.toFixed(2)} USDT
              </Typography>
              <Typography 
                variant="body2" 
                color={pnlColor}
                sx={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  px: 1,
                  py: 0.25,
                  borderRadius: 1,
                  backgroundColor: `${pnlColor}22`, // 10% opacity of the color
                  fontWeight: 'medium'
                }}
              >
                {pnlSign}{Math.abs(pnlPercent).toFixed(2)}%
              </Typography>
            </Box>
            <Typography variant="caption" color="text.secondary">
              {walletData?.type ? `Wallet: ${walletData.type}` : 'Demo Wallet'}
            </Typography>
          </Box>
        </Box>
      </Paper>
    </Box>
  );
}
