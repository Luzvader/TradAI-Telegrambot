"use client";

import { useState } from "react";
import { Box, Autocomplete, TextField } from "@mui/material";

const SYMBOLS = [
  { label: "BTCUSDT", exchange: "BINANCE" },
  { label: "ETHUSDT", exchange: "BINANCE" },
  { label: "XRPUSDT", exchange: "BINANCE" },
  { label: "SOLUSDT", exchange: "BINANCE" },
  { label: "BNBUSDT", exchange: "BINANCE" },
];

export default function TVChartWidget() {
  const [symbol, setSymbol] = useState<string>("BTCUSDT");

  const src = `https://s.tradingview.com/embed-widget/advanced-chart/?symbol=BINANCE:${symbol}&theme=dark&style=1&locale=en`;

  return (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column", pt: 1 }}>
      <Autocomplete
        size="small"
        options={SYMBOLS}
        getOptionLabel={(o) => o.label}
        value={SYMBOLS.find((o) => o.label === symbol) || null}
        onChange={(_, newValue) => {
          if (newValue) {
            setSymbol(newValue.label);
          }
        }}
        renderInput={(params) => <TextField {...params} label="Symbol" />}
        sx={{ mb: 1 }}
      />
      <Box sx={{ flexGrow: 1, height: "100%", overflow: "hidden" }}>
        <iframe
          src={src}
          style={{ width: "100%", height: "100%", border: "none" }}
          loading="lazy"
          sandbox="allow-scripts allow-same-origin"
          referrerPolicy="no-referrer"
        />
      </Box>
    </Box>
  );
}
