"use client";
import { DataGrid, GridColDef, GridRowsProp } from "@mui/x-data-grid";
import { Sparklines, SparklinesLine } from "react-sparklines";
import useSWR from "swr";
import { fetcher } from "../utils/fetcher";
import { Box } from "@mui/material";

interface MarketResponse {
  symbols: string[];
  data: Record<string, number[]>; // Simplified: [price, change, ...]
}

interface Props {
  symbols: string[];
  period: string;
}

export default function MarketsTable({ symbols, period }: Props) {
  // Convert symbols like BTCUSDT to BTC for backend query
  const baseSymbols = symbols.map((s) => s.replace(/USDT$/, ""));
  const { data, error, isLoading } = useSWR<MarketResponse>(
    `/api/markets?symbols=${baseSymbols.join(",")}&period=${period}`,
    fetcher,
    { refreshInterval: 5000 }
  );

  if (isLoading) return <>Loading...</>;
  if (error || !data) return <>Error</>;

  const rows = symbols.map((original, idx) => {
    const base = original.replace(/USDT$/, "");
    const entry = data.data[base] ?? [];
    return {
      id: idx,
      symbol: original,
      price: entry[0] ?? 0,
      change: entry[2] ?? 0, // change % is third column (index 2)
      history: entry,
    };
  });

  const cols: GridColDef[] = [
    { field: "symbol", headerName: "Symbol", flex: 1 },
    { field: "price", headerName: "Price", flex: 1, type: "number" },
    {
      field: "change",
      headerName: `% Change (${period})`,
      flex: 1,
      type: "number",
      valueFormatter: ({ value }) => `${Number(value).toFixed(2)}%`,
    },
    {
      field: "history",
      headerName: period,
      flex: 1.2,
      sortable: false,
      renderCell: (params) => (
        <Sparklines data={params.value as number[]} width={100} height={20}>
          <SparklinesLine color="blue" />
        </Sparklines>
      ),
    },
  ];

  return (
    <div style={{ width: "100%", minHeight: 400, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <Box sx={{ flex: 1, minHeight: 0 }}>
        <DataGrid
          autoHeight
          density="compact"
          disableColumnMenu
          disableSelectionOnClick
          rows={rows}
          columns={cols}
          pageSize={5}
          rowsPerPageOptions={[5, 10]}
          sx={{
            fontSize: "clamp(10px,1.2vw,14px)",
            '& .MuiDataGrid-cell': {
              outline: 'none !important',
              py: 0.5
            },
          }}
        />
      </Box>
    </div>
  );
}
