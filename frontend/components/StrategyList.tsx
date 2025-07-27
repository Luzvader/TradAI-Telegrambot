"use client";
import useSWR from "swr";
import { fetcher } from "../utils/fetcher";
import {
  List,
  ListItem,
  ListItemText,
  Typography,
  CircularProgress,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
} from "@mui/material";
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import { useState } from "react";

interface Strategy {
  name?: string;
  symbol?: string;
  id?: string;
}
interface StratResp {
  strategies: (Strategy | string)[];
}

export default function StrategyList() {
  const { data, error, mutate } = useSWR<StratResp>("/api/strategies", fetcher, {
    refreshInterval: 60000,
  });
  const { data: defaults } = useSWR<StratResp>("/api/strategies/defaults", fetcher);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Strategy | null>(null);

  const handleEdit = (strat: Strategy) => {
    setSelected(strat);
    setOpen(true);
  };
  const handleDelete = async (id?: string) => {
    if (!id) return;
    await fetch(`/api/strategies/${id}`, { method: "DELETE" });
    mutate();
    setOpen(false);
  };
  const handleAdvancedEdit = (id?: string) => {
    if (!id) return;
    window.location.href = `/strategies/edit/${id}`;
  };

  if (!data && !defaults && !error) return <CircularProgress />;
  if (error || !data) return <Typography>Error loading</Typography>;

  const merged: (Strategy & {default?: boolean})[] = [
    ...((defaults?.strategies ?? []) as Strategy[]).map((s) => ({ ...s, default: true })),
    ...(data?.strategies ?? []) as Strategy[],
  ];

  return (
    <>
      <List>
        {merged.map((s, idx) => {
          const strat = typeof s === "string" ? { id: s } : s;
          return (
            <ListItem key={idx} divider secondaryAction={
              <>
                {!s.default && (
                  <>
                    <IconButton edge="end" aria-label="edit" onClick={() => handleEdit(strat)}>
                      <EditIcon />
                    </IconButton>
                    <IconButton edge="end" aria-label="delete" onClick={() => handleDelete(strat.id)}>
                      <DeleteIcon />
                    </IconButton>
                    <Button size="small" onClick={() => handleAdvancedEdit(strat.id)}>Avanzado</Button>
                  </>
                )}
              </>
            }>
              <ListItemText
                primary={`${String(strat.name ?? strat.id)}${s.default ? " (default)" : ""}`}
                secondary={strat.symbol ? `Symbol: ${strat.symbol}` : "Rule-based"}
              />
            </ListItem>
          );
        })}
      </List>
      <Dialog open={open} onClose={() => setOpen(false)}>
        <DialogTitle>Editar Estrategia</DialogTitle>
        <DialogContent>
          {/* Campos básicos para edición rápida */}
          <Typography variant="body2">Nombre: {selected?.name}</Typography>
          <Typography variant="body2">Símbolo: {selected?.symbol}</Typography>
          {/* Aquí podrías agregar inputs para edición básica si lo deseas */}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
          <Button color="error" onClick={() => handleDelete(selected?.id)}>Eliminar</Button>
          <Button onClick={() => handleAdvancedEdit(selected?.id)}>Edición avanzada</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
