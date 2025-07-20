"use client";
import { Box, Typography } from "@mui/material";

export default function Dashboard() {
  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        TradAI Dashboard
      </Typography>
      <Box sx={{ 
        p: 2, 
        bgcolor: 'background.paper',
        borderRadius: 1,
        boxShadow: 1
      }}>
        <Typography variant="h6">Market Overview</Typography>
        <Typography>Loading market data...</Typography>
      </Box>
    </Box>
  );
}
