import { Box, Typography } from "@mui/material";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

interface SimulationResult {
  timestamp: number;
  symbol: string;
  action: string;
  amount: number;
  price: number;
}

interface Props {
  results: SimulationResult[];
}

export default function StrategyPerformanceChart({ results }: Props) {
  if (!results || results.length === 0) return null;

  // Calcular el equity curve (simulación simple)
  let equity = 1000;
  const equityCurve: number[] = [];
  results.forEach((r) => {
    if (r.action === "BUY") {
      equity -= (r.amount / 100) * equity;
    } else if (r.action === "SELL") {
      equity += (r.amount / 100) * equity;
    }
    equityCurve.push(equity);
  });

  const data = {
    labels: results.map((r) => new Date(r.timestamp * 1000).toLocaleTimeString()),
    datasets: [
      {
        label: "Equity ($)",
        data: equityCurve,
        borderColor: "#1976d2",
        backgroundColor: "rgba(25, 118, 210, 0.1)",
        fill: true,
      },
    ],
  };

  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="subtitle1" sx={{ mb: 1 }}>
        Performance de la estrategia (simulación)
      </Typography>
      <Line data={data} options={{ responsive: true, plugins: { legend: { display: true } } }} />
    </Box>
  );
}
