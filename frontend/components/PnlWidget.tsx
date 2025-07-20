"use client";
import useSWR from "swr";
import { fetcher } from "../utils/fetcher";

interface PnlResp {
  pnl: number;
}

export default function PnlWidget() {
  const { data, error, isLoading } = useSWR<PnlResp>("/api/pnl", fetcher);
  if (isLoading) return <>Loading...</>;
  if (error || !data) return <>Error</>;
  const color = data.pnl >= 0 ? "green" : "red";
  return <div style={{ color }}>{data.pnl.toFixed(2)} USDT</div>;
}
