"use client";

import useSWR from "swr";
import { fetcher } from "../utils/fetcher";
import { Box, Typography } from "@mui/material";

interface WalletResponse {
  type: string | null;
  balances: Record<string, number>;
}

export default function BalanceWidget() {
  const { data, error, isLoading } = useSWR<WalletResponse>("/api/wallet", fetcher);

  const balance = data?.balances?.USDT ?? 0;
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
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
