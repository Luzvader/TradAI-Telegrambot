"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "../utils/fetcher";
import { Box, Typography, Autocomplete, TextField } from "@mui/material";

interface WalletResponse {
  type: string | null;
  balances: Record<string, number>;
}

export default function BalanceWidget() {
  const [selected, setSelected] = useState<string>("demo");
  const { data, error, isLoading } = useSWR<WalletResponse>("/api/wallet", fetcher, {
    revalidateOnFocus: false,
  });

  const balance = error ? 10000 : data?.balances?.USDT ?? 0;
  return (
    <Box sx={{ 
      display: "flex", 
      flexDirection: "column", 
      gap: 2, 
      minHeight: 400,
      p: 2,
      '& .MuiAutocomplete-root': {
        width: '100%',
        maxWidth: 300,
        mb: 2
      },
      '& .MuiTypography-h6': {
        fontSize: '1.5rem',
        fontWeight: 'bold',
        color: 'primary.main'
      }
    }}>
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
          <Box sx={{ 
            bgcolor: 'background.paper', 
            p: 2, 
            borderRadius: 1,
            boxShadow: 1,
            mt: 2
          }}>
            <Typography variant="h6">
              {balance.toFixed(2)} USDT
            </Typography>
          </Box>
        </>
      )}
    </Box>
  );
}
