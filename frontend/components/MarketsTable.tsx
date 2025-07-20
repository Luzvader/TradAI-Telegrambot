"use client";
import { DataGrid, GridColDef } from "@mui/x-data-grid";
import useSWR from "swr";
import { Sparklines, SparklinesLine } from "react-sparklines";
import { fetcher } from "../utils/fetcher";

interface MarketResponse {
  symbols: string[];
  data: Record<string, number[]>; // Simplified: [price, change, ...]
}

export default function MarketsTable({ symbols }: { symbols: string[] }) {
  const { data, error, isLoading } = useSWR<MarketResponse>(
    `/api/markets?symbols=${symbols.join(",")}`,
    fetcher,
    { refreshInterval: 5000 }
  );

  if (isLoading) return <>Loading...</>;
  if (error || !data) return <>Error</>;

  const rows = data.symbols.map((sym, idx) => ({
    id: idx,
    symbol: sym,
    price: data.data[sym]?.[0] ?? 0,
    change: data.data[sym]?.[1] ?? 0,
    history: data.data[sym] ?? [],
  }));

  const cols: GridColDef[] = [
    { field: "symbol", headerName: "Symbol", width: 120 },
    { field: "price", headerName: "Price", width: 120, type: "number" },
    {
      field: "change",
      headerName: "% Change",
      width: 120,
      type: "number",
      valueFormatter: ({ value }) => `${Number(value).toFixed(2)}%`,
    },
    {
      field: "history",
      headerName: "24h",
      width: 140,
      sortable: false,
      renderCell: (params) => (
        <Sparklines data={params.value as number[]} width={100} height={20}>
          <SparklinesLine color="blue" />
        </Sparklines>
      ),
    },
  ];

  return (
    <div style={{ height: 400 }}>
      <DataGrid rows={rows} columns={cols} pageSize={5} rowsPerPageOptions={[5, 10]} />
    </div>
  );
}
