"use client";
import useSWR from "swr";
import { fetcher } from "../utils/fetcher";
import { Box, Typography, Stack, Skeleton, Button } from "@mui/material";
import React, { useState } from "react";

interface SignalResponse {
  symbol: string;
  latest_price: number;
  latest_signal: string;
  latest_rsi: number | null;
  latest_macd: number | null;
  latest_atr: number | null;
  latest_candle: string;
  signals: string[];
}

interface Props {
  symbol: string;
  interval?: string;
}

export default function SignalsWidget({ symbol, interval = "5m" }: Props) {
  const { data, error, isLoading } = useSWR<SignalResponse>(
    `/api/signals?symbol=${symbol}&interval=${interval}`,
    fetcher,
    { refreshInterval: 10000 }
  );

  if (isLoading) {
    return <Skeleton variant="rectangular" width={300} height={120} />;
  }
  if (error || !data) {
    return <Box sx={{ p: 2, color: "error.main" }}>Error al cargar señales</Box>;
  }

  return (
    <Box sx={{ p: 2, border: "1px solid #eee", borderRadius: 2, minWidth: 300 }}>
      <Typography variant="h6">Señales para {data.symbol}</Typography>
      <Typography variant="body2">Precio actual: ${data.latest_price}</Typography>
      <Typography variant="body2">Señal: <b>{data.latest_signal}</b></Typography>
      <Typography variant="body2">RSI: {data.latest_rsi ?? "N/A"}</Typography>
      <Typography variant="body2">MACD: {data.latest_macd ?? "N/A"}</Typography>
      <Typography variant="body2">ATR: {data.latest_atr ?? "N/A"}</Typography>
      <Typography variant="body2">Patrón de vela: {data.latest_candle}</Typography>
      <Typography variant="body2" sx={{ mt: 1 }}>Histórico de señales:</Typography>
      <Box sx={{ maxHeight: 80, overflowY: "auto", fontSize: 13, bgcolor: "#fafafa", p: 1, borderRadius: 1 }}>
        {data.signals.slice(-10).map((s, i) => (
          <span key={i}>{s}{i < data.signals.slice(-10).length - 1 ? ", " : ""}</span>
        ))}
      </Box>
    </Box>
  );
}
