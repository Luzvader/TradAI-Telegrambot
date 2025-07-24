"use client";
import useSWR from "swr";
import { fetcher } from "../utils/fetcher";
import { Box, Typography, Table, TableHead, TableRow, TableCell, TableBody, Skeleton } from "@mui/material";
import React from "react";

interface BacklogEntry {
  symbol: string;
  timestamp: number;
  price: number;
  signal: string;
  rsi: number | null;
  macd: number | null;
  atr: number | null;
  candle: string;
}

interface Props {
  symbol?: string;
}

export default function BacklogTable({ symbol }: Props) {
  const url = symbol ? `/api/backlog?symbol=${symbol}` : "/api/backlog";
  const { data, error, isLoading } = useSWR<{ backlog: BacklogEntry[] }>(url, fetcher, { refreshInterval: 15000 });

  if (isLoading) {
    return <Skeleton variant="rectangular" width={600} height={180} />;
  }
  if (error || !data) {
    return <Box sx={{ p: 2, color: "error.main" }}>Error al cargar el backlog</Box>;
  }

  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="h6" sx={{ mb: 2 }}>Histórico de señales y performance</Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Símbolo</TableCell>
            <TableCell>Fecha</TableCell>
            <TableCell>Precio</TableCell>
            <TableCell>Señal</TableCell>
            <TableCell>RSI</TableCell>
            <TableCell>MACD</TableCell>
            <TableCell>ATR</TableCell>
            <TableCell>Patrón de vela</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.backlog.slice(-50).reverse().map((entry, idx) => (
            <TableRow key={idx}>
              <TableCell>{entry.symbol}</TableCell>
              <TableCell>{new Date(entry.timestamp * 1000).toLocaleString()}</TableCell>
              <TableCell>{entry.price}</TableCell>
              <TableCell>{entry.signal}</TableCell>
              <TableCell>{entry.rsi ?? "N/A"}</TableCell>
              <TableCell>{entry.macd ?? "N/A"}</TableCell>
              <TableCell>{entry.atr ?? "N/A"}</TableCell>
              <TableCell>{entry.candle}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}
