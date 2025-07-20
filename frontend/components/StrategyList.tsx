"use client";
import useSWR from "swr";
import { fetcher } from "../utils/fetcher";
import {
  List,
  ListItem,
  ListItemText,
  Typography,
  CircularProgress,
} from "@mui/material";

interface Strategy {
  name?: string;
  symbol?: string;
  id?: string;
}
interface StratResp {
  strategies: Strategy[];
}

export default function StrategyList() {
  const { data, error } = useSWR<StratResp>("/api/strategies", fetcher, {
    refreshInterval: 60000,
  });

  if (!data && !error) return <CircularProgress />;
  if (error || !data) return <Typography>Error loading</Typography>;

  return (
    <List>
      {data.strategies.map((s, idx) => (
        <ListItem key={idx} divider>
          <ListItemText
            primary={s.name ?? s.id}
            secondary={s.symbol ? `Symbol: ${s.symbol}` : "Rule-based"}
          />
        </ListItem>
      ))}
    </List>
  );
}
