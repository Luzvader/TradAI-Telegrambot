"use client";
import useSWR from "swr";
import { fetcher } from "../utils/fetcher";

interface BalanceResponse {
  balance: number;
}

export default function BalanceWidget() {
  // TODO: replace portfolio id with real selection
  const { data, error, isLoading } = useSWR<BalanceResponse>(
    "/api/portfolio/default/balance",
    fetcher
  );
  if (isLoading) return <>Loading...</>;
  if (error || !data) return <>Error</>;
  return <div>{data.balance.toFixed(2)} USDT</div>;
}
