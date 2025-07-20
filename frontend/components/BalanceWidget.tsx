"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "../utils/fetcher";
import { Box, Autocomplete, TextField, Typography } from "@mui/material";

interface Portfolio {
  id: string;
  name: string;
}

interface BalanceResponse {
  balance: number;
}

export default function BalanceWidget() {
  // fetch available portfolios
  const { data: portfolios } = useSWR<Portfolio[]>("/api/portfolio", fetcher);
  const [selected, setSelected] = useState<string>("demo");

  const { data, error, isLoading } = useSWR<BalanceResponse>(
    `/api/portfolio/${selected}/balance`,
    fetcher
  );

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      <Autocomplete
        size="small"
        options={portfolios || [{ id: "demo", name: "Demo" }]}
        getOptionLabel={(o) => o.name}
        value={(portfolios || []).find((p) => p.id === selected) || null}
        onChange={(_, val) => val && setSelected(val.id)}
        renderInput={(params) => <TextField {...params} label="Portfolio" />}
      />
      {isLoading && <Typography variant="body2">Loading…</Typography>}
      {error && <Typography variant="body2" color="error">Error</Typography>}
      {data && (
        <Typography variant="h6" sx={{ mt: 1 }}>
          {data.balance.toFixed(2)} USDT
        </Typography>
      )}
    </Box>
  );
}
