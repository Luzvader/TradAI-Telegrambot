"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "../utils/fetcher";
import { Box, Autocomplete, TextField, Typography } from "@mui/material";

interface WalletResponse {
  type: string | null;
  balances: Record<string, number>;
}

export default function BalanceWidget() {
  const [selected, setSelected] = useState<string>("demo");

  const { data, error, isLoading } = useSWR<WalletResponse>("/api/wallet", fetcher);

  const balance = data?.balances?.USDT ?? 0;
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      <Autocomplete
        size="small"
        options={[{ id: "demo", name: "Demo" }]}
        getOptionLabel={(o) => o.name}
        value={{ id: selected, name: "Demo" }}
        onChange={(_, val) => val && setSelected(val.id)}
        renderInput={(params) => <TextField {...params} label="Cartera" />}
      />
      {isLoading && <Typography variant="body2">Loading…</Typography>}
      {error && <Typography variant="body2" color="error">Error</Typography>}
      {data && (
        <>
          <Typography variant="body2">Wallet: {data.type ?? "-"}</Typography>
          <Typography variant="h6" sx={{ mt: 1 }}>
            {balance.toFixed(2)} USDT
          </Typography>
        </>
      )}
    </Box>
  );
}
