"use client";
import { useState } from "react";
import { fetcher } from "../utils/fetcher";
import { Box, Typography, Button, Stack, Select, MenuItem, TextField, InputLabel, FormControl } from "@mui/material";


type Condition = {
  indicator: string;
  operator: string;
  value: string;
  timeframe: string;
};

const indicators = ["price", "rsi", "macd", "atr"];
const operators = [">", "<", ">=", "<=", "=="];
const actions = ["BUY", "SELL"];

export default function StrategyBuilder() {
  const [conditions, setConditions] = useState<Condition[]>([
    { indicator: "price", operator: "<", value: "", timeframe: "5m" },
  ]);
  const [action, setAction] = useState<string>("BUY");
  const [amount, setAmount] = useState<number>(10);
  const [simulation, setSimulation] = useState<any[]>([]);

  const handleConditionChange = (idx: number, field: keyof Condition, value: string) => {
    const updated = [...conditions];
    updated[idx] = { ...updated[idx], [field]: value };
    setConditions(updated);
  };

  const addCondition = () => {
    setConditions([...conditions, { indicator: "price", operator: "<", value: "", timeframe: "5m" }]);
  };

  const removeCondition = (idx: number) => {
    setConditions(conditions.filter((_, i) => i !== idx));
  };

  const handleSubmit = async () => {
    // Guardar estrategia en el backend
    await fetcher("/api/strategies", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conditions, action, amount }),
    });
    // Simular estrategia sobre el backlog
    const sim = await fetcher<{ result: any[] }>("/api/simulate-strategy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conditions, action, amount }),
    });
    setSimulation(sim.result);
  };

  return (
    <Box sx={{ p: 2, border: "1px solid #eee", borderRadius: 2, mb: 3 }}>
      <Typography variant="h6" sx={{ mb: 2 }}>Crear estrategia personalizada</Typography>
      {conditions.map((cond, idx) => (
        <Stack direction="row" spacing={2} alignItems="center" key={idx} sx={{ mb: 1 }}>
          <FormControl size="small">
            <InputLabel>Indicador</InputLabel>
            <Select
              value={cond.indicator}
              label="Indicador"
              onChange={e => handleConditionChange(idx, "indicator", e.target.value as string)}
            >
              {indicators.map(ind => <MenuItem key={ind} value={ind}>{ind.toUpperCase()}</MenuItem>)}
            </Select>
          </FormControl>
          <FormControl size="small">
            <InputLabel>Operador</InputLabel>
            <Select
              value={cond.operator}
              label="Operador"
              onChange={e => handleConditionChange(idx, "operator", e.target.value as string)}
            >
              {operators.map(op => <MenuItem key={op} value={op}>{op}</MenuItem>)}
            </Select>
          </FormControl>
          <TextField
            size="small"
            label="Valor"
            type="number"
            value={cond.value}
            onChange={e => handleConditionChange(idx, "value", e.target.value)}
            sx={{ width: 90 }}
          />
          <TextField
            size="small"
            label="Timeframe"
            value={cond.timeframe}
            onChange={e => handleConditionChange(idx, "timeframe", e.target.value)}
            sx={{ width: 80 }}
          />
          <Button color="error" onClick={() => removeCondition(idx)} disabled={conditions.length === 1}>Eliminar</Button>
        </Stack>
      ))}
      <Button variant="outlined" onClick={addCondition} sx={{ mb: 2 }}>Agregar condición</Button>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
        <FormControl size="small">
          <InputLabel>Acción</InputLabel>
          <Select value={action} label="Acción" onChange={e => setAction(e.target.value as string)}>
            {actions.map(a => <MenuItem key={a} value={a}>{a}</MenuItem>)}
          </Select>
        </FormControl>
        <TextField
          size="small"
          label="Cantidad (%)"
          type="number"
          value={amount}
          onChange={e => setAmount(Number(e.target.value))}
          sx={{ width: 100 }}
        />
      </Stack>
      <Button variant="contained" onClick={handleSubmit}>Guardar y simular estrategia</Button>

      {/* Resultados de la simulación */}
      {simulation.length > 0 && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="subtitle1">Resultados de la simulación:</Typography>
          <ul>
            {simulation.slice(-50).reverse().map((res, idx) => (
              <li key={idx}>
                [{new Date(res.timestamp * 1000).toLocaleString()}] {res.symbol}: {res.action} {res.amount}% @ ${res.price}
              </li>
            ))}
          </ul>
        </Box>
      )}
    </Box>
  );
}
