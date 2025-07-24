"use client";
import { useState, useEffect } from "react";
import { 
  Box, 
  TextField, 
  Button, 
  Typography, 
  Chip, 
  Stack, 
  Select, 
  MenuItem, 
  FormControl, 
  SelectChangeEvent
} from "@mui/material";
import WidgetFrame from "./WidgetFrame";
import { Close } from "@mui/icons-material";
import MarketsTable from "./MarketsTable";
import { fetcher } from "../utils/fetcher";

const STORAGE_KEY = 'tradai_prices_widget_symbols';

const PERIODS = [
  { value: "1h", label: "1H" },
  { value: "4h", label: "4H" },
  { value: "24h", label: "24H" },
  { value: "1w", label: "1W" },
  { value: "1m", label: "1M" },
  { value: "3m", label: "3M" },
  { value: "6m", label: "6M" },
  { value: "1y", label: "1Y" },
  { value: "ytd", label: "YTD" },
];

export default function PricesWidget() {
  const defaultSymbols = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT"];
  const [symbols, setSymbols] = useState<string[]>([]);
  const [period, setPeriod] = useState<string>("24h");
  const [newSymbol, setNewSymbol] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  // Load symbols from localStorage on component mount
  useEffect(() => {
    try {
      const savedSymbols = localStorage.getItem(STORAGE_KEY);
      if (savedSymbols) {
        setSymbols(JSON.parse(savedSymbols));
      } else {
        // If no saved symbols, use defaults and save them
        setSymbols(defaultSymbols);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(defaultSymbols));
      }
    } catch (e) {
      console.error('Failed to load symbols from localStorage', e);
      setSymbols(defaultSymbols);
    }
  }, []);

  // Save symbols to localStorage whenever they change
  useEffect(() => {
    if (symbols.length > 0) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(symbols));
      } catch (e) {
        console.error('Failed to save symbols to localStorage', e);
      }
    }
  }, [symbols]);

  const handleRemoveSymbol = (symbolToRemove: string) => {
    setSymbols(symbols.filter(sym => sym !== symbolToRemove));
  };

  const handleResetToDefaults = () => {
    setSymbols([...defaultSymbols]);
  };

  const handleAddSymbol = async () => {
    const sym = newSymbol.trim().toUpperCase();
    if (!sym) {
      setNewSymbol("");
      return;
    }
    
    if (symbols.includes(sym)) {
      setError(`El símbolo "${sym}" ya está en la lista.`);
      setNewSymbol("");
      return;
    }
    
    try {
      const res = await fetcher<{ data: Record<string, any> }>(
        `/api/markets?symbols=${sym}`
      );
      const base = sym.replace(/USDT$/, "");
      if (res.data && res.data[base]) {
        const updatedSymbols = [...symbols, sym];
        setSymbols(updatedSymbols);
        setError(null);
      } else {
        setError(`Símbolo "${sym}" no encontrado.`);
      }
    } catch {
      setError(`Error al buscar el símbolo "${sym}".`);
    } finally {
      setNewSymbol("");
    }
  };

  const handlePeriodChange = (event: SelectChangeEvent) => {
    setPeriod(event.target.value);
  };

  // Create the period selector to be used in the header
  const periodSelector = (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, height: '100%' }}>
      <Typography 
        variant="body2" 
        color="text.secondary" 
        sx={{ 
          fontSize: '0.875rem',
          lineHeight: '1.5',
          marginTop: '1px' // Ajuste fino para alinear con el selector
        }}
      >
        Período:
      </Typography>
      <FormControl 
        size="small" 
        sx={{ 
          minWidth: 90,
          '& .MuiInput-root': {
            margin: 0,
            '&:before, &:after': {
              display: 'none'
            }
          },
          '& .MuiSelect-select': {
            padding: '4px 24px 4px 8px',
            fontSize: '0.875rem',
            lineHeight: '1.5',
            backgroundColor: 'transparent',
            '&:focus': {
              backgroundColor: 'transparent'
            }
          },
          '& .MuiSelect-icon': {
            right: '4px'
          }
        }}
        variant="standard"
      >
        <Select
          value={period}
          onChange={handlePeriodChange}
          variant="standard"
          disableUnderline
          MenuProps={{
            PaperProps: {
              sx: {
                marginTop: '8px',
                boxShadow: 3
              }
            }
          }}
        >
          {PERIODS.map((p) => (
            <MenuItem key={p.value} value={p.value}>
              {p.label}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
    </Box>
  );

  return (
    <WidgetFrame title="" action={periodSelector}>
      <Box sx={{ display: "flex", flexDirection: 'column', gap: 2 }}>
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
            sx={{ flexGrow: 1 }}
            placeholder="Ej: BTCUSDT"
          />
          <Button variant="contained" onClick={handleAddSymbol}>
            Añadir
          </Button>
          <Button 
            variant="outlined" 
            onClick={handleResetToDefaults}
            sx={{ ml: 1 }}
            title="Restaurar símbolos por defecto"
          >
            Restaurar valores por defecto
          </Button>
        </Box>
        
        {symbols.length > 0 && (
          <Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Símbolos mostrados:
            </Typography>
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
              {symbols.map((symbol) => (
                <Chip
                  key={symbol}
                  label={symbol}
                  onDelete={() => handleRemoveSymbol(symbol)}
                  deleteIcon={<Close />}
                  variant="outlined"
                  size="small"
                />
              ))}
            </Stack>
          </Box>
        )}
      </Box>

      {error && (
        <Typography variant="body2" color="error">
          {error}
        </Typography>
      )}
      <MarketsTable symbols={symbols} period={period} compact />
    </WidgetFrame>
  );
}
