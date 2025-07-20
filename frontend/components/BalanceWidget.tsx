"use client";
import React
import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "../utils/fetcher";

interface WalletResponse {
  type: string | null;
  balances: Record<string, number>;
}

export default function BalanceWidget() {
  const [selected, setSelected] = useState<string>("demo");
  const { data, error, isLoading } = useSWR<WalletResponse>("/api/wallet", fetcher);
  const balance = data?.balances?.USDT ?? 0;

  if (isLoading) return <>Loading...</>;
  if (error || !data) return <>Error</>;

  return (
    <div>
      <select value={selected} onChange={(e) => setSelected(e.target.value)}>
        <option value="demo">Demo</option>
        <option value="binance">Binance</option>
      </select>
      <div>{balance.toFixed(2)} USDT</div>
    </div>
  );
}
