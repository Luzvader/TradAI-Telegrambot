"use client";
import { DataGrid, GridColDef } from "@mui/x-data-grid";
import useSWR from "swr";
import { fetcher } from "../utils/fetcher";

interface MarketResponse {
  symbols: string[];
  data: Record<string, number[]>; // Simplified: [price, change, ...]
}

export default function MarketsTable({ symbols }: { symbols: string[] }) {
  const { data, error, isLoading } = useSWR<MarketResponse>(
    `/api/markets?symbols=${symbols.join(",")}`,
    fetcher
  );

  if (isLoading) return <>Loading...</>;
  if (error || !data) return <>Error</>;

  const rows = data.symbols.map((sym, idx) => ({
    id: idx,
    symbol: sym,
    price: data.data[sym]?.[0] ?? 0,
  }));

  const cols: GridColDef[] = [
    { field: "symbol", headerName: "Symbol", width: 120 },
    { field: "price", headerName: "Price", width: 150, type: "number" },
  ];

  return (
    <div style={{ height: 400 }}>
      <DataGrid rows={rows} columns={cols} />
    </div>
  );
}
