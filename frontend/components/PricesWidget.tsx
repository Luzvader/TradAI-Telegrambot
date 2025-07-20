"use client";
import { useState } from "react";
import { Box, TextField, Button, Typography, ToggleButton, ToggleButtonGroup } from "@mui/material";
import MarketsTable from "./MarketsTable";
import { fetcher } from "../utils/fetcher";

export default function PricesWidget() {
  const defaultSymbols = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT"];
  const [symbols, setSymbols] = useState<string[]>(defaultSymbols);
  const [period, setPeriod] = useState<string>("24h");
  const [newSymbol, setNewSymbol] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const handleAddSymbol = async () => {
    const sym = newSymbol.trim().toUpperCase();
    if (!sym || symbols.includes(sym)) {
      setNewSymbol("");
      return;
    }
    try {
      const res = await fetcher<{ data: Record<string, any> }>(
        `/api/markets?symbols=${sym}`
      );
      if (res.data && res.data[sym]) {
        setSymbols([...symbols, sym]);
        setError(null);
      } else {
        setError(`Símbolo "${sym}" no encontrado.`);
      }
    } catch {
      setError(`Símbolo "${sym}" no encontrado.`);
    } finally {
      setNewSymbol("");
    }
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
        <TextField
          label="Agregar símbolo"
          size="small"
          value={newSymbol}
          onChange={(e) => setNewSymbol(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              handleAddSymbol();
            }
          }}
        />
        <Button variant="contained" onClick={handleAddSymbol} sx={{ ml: 1 }}>
          Añadir
        </Button>
      </Box>
      <ToggleButtonGroup
        size="small"
        exclusive
        value={period}
        onChange={(_, val) => val && setPeriod(val)}
        sx={{ my: 1 }}
      >
        {[
          "1h",
          "3h",
          "6h",
          "24h",
          "3d",
          "1w",
          "1m",
          "6m",
          "1y",
        ].map((p) => (
          <ToggleButton key={p} value={p} sx={{ fontSize: "0.75rem" }}>
            {p}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>

      {error && (
        <Typography variant="body2" color="error">
          {error}
        </Typography>
      )}
      <MarketsTable symbols={symbols} period={period} />
    </Box>
  );
}
