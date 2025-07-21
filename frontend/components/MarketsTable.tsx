"use client";
import useSWR from "swr";
import { fetcher } from "../utils/fetcher";
import { Box, Typography, Stack, Skeleton } from "@mui/material";
import React from "react";
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import { format } from 'd3-format';

interface MarketResponse {
  symbols: string[];
  data: Record<string, number[]>; // [price, change, changePercent, ...]
}

interface Props {
  symbols: string[];
  period: string;
}

const formatPrice = (value: number) => {
  if (value >= 1000) {
    return format(",.0f")(value);
  } else if (value >= 0.1) {
    return format(",.2f")(value);
  } else {
    return format(".8f")(value).replace(/(\.\d*?[1-9])0+$/, "$1").replace(/\.?0+$/, "");
  }
};

export default function MarketsTable({ symbols, period }: Props) {
  // Convert symbols like BTCUSDT to BTC for backend query
  const baseSymbols = symbols.map((s) => s.replace(/USDT$/, ""));
  const { data, error, isLoading } = useSWR<MarketResponse>(
    `/api/markets?symbols=${baseSymbols.join(",")}&period=${period}`,
    fetcher,
    { refreshInterval: 5000 }
  );

  if (isLoading) {
    return (
      <Box sx={{ width: '100%' }}>
        {symbols.map((symbol, index) => (
          <Box key={index} sx={{ p: 1.5, borderBottom: '1px solid rgba(224, 224, 224, 0.5)' }}>
            <Skeleton variant="text" width="100%" height={40} />
          </Box>
        ))}
      </Box>
    );
  }
  
  if (error || !data) {
    return (
      <Box sx={{ p: 2, color: 'error.main', textAlign: 'center' }}>
        Error al cargar los datos del mercado
      </Box>
    );
  }

  const rows = symbols.map((original, idx) => {
    const base = original.replace(/USDT$/, "");
    const entry = data.data[base] ?? [0, 0];
    return {
      id: idx,
      symbol: original,
      price: entry[0] || 0,
      // The backend returns only price and change %, so the change value is at
      // index 1.
      change: entry[1] || 0,
    };
  });

  return (
    <Box sx={{ width: '100%' }}>
      {rows.map((row) => {
        const isPositive = row.change >= 0;
        const changeColor = isPositive ? 'success.main' : 'error.main';
        const ChangeIcon = isPositive ? TrendingUpIcon : TrendingDownIcon;
        
        return (
          <Box 
            key={row.id}
            sx={{
              p: 1.5,
              borderBottom: '1px solid',
              borderColor: 'divider',
              '&:hover': {
                backgroundColor: 'action.hover',
              },
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <Box>
              <Typography variant="subtitle1" fontWeight={500}>
                {row.symbol.replace('USDT', '')}
              </Typography>
            </Box>
            <Stack direction="row" spacing={2} alignItems="center">
              <Typography variant="body1" fontWeight={500}>
                ${formatPrice(row.price)}
              </Typography>
              <Box 
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  color: changeColor,
                  bgcolor: isPositive ? 'rgba(76, 175, 80, 0.1)' : 'rgba(244, 67, 54, 0.1)',
                  px: 1,
                  py: 0.5,
                  borderRadius: 1,
                  minWidth: 85,
                  justifyContent: 'center'
                }}
              >
                <ChangeIcon fontSize="small" sx={{ mr: 0.5, fontSize: '1rem' }} />
                <Typography variant="body2" fontWeight={500}>
                  {Math.abs(row.change).toFixed(2)}%
                </Typography>
              </Box>
            </Stack>
          </Box>
        );
      })}
    </Box>
  );
}
