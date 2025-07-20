"use client";
import { Box, Container, Typography } from "@mui/material";

export default function Dashboard() {
  return (
    <Container maxWidth="xl" sx={{ height: '100%' }}>
      <Box sx={{ 
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        gap: 3
      }}>
        <Typography variant="h4" component="h1" gutterBottom>
          TradAI Dashboard
        </Typography>
        
        <Box sx={{ 
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          gap: 3,
          minHeight: 0 // This is important for proper scrolling
        }}>
          <Box 
            sx={{ 
              p: 3, 
              bgcolor: 'background.paper',
              borderRadius: 2,
              boxShadow: 1,
              flex: '0 0 auto'
            }}
          >
            <Typography variant="h6" gutterBottom>Market Overview</Typography>
            <Typography>Loading market data...</Typography>
          </Box>
          
          {/* Add more content sections here as needed */}
          <Box 
            sx={{ 
              flex: 1,
              bgcolor: 'background.paper',
              borderRadius: 2,
              boxShadow: 1,
              p: 3,
              minHeight: 400,
              overflow: 'auto'
            }}
          >
            <Typography variant="h6" gutterBottom>Additional Content</Typography>
            <Typography>Your dashboard content will appear here.</Typography>
          </Box>
        </Box>
      </Box>
    </Container>
  );
}
