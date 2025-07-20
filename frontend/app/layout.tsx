"use client";
import * as React from "react";
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import NavBar from "../components/NavBar";
import "./globals.css";


const theme = createTheme({
  palette: {
    mode: "dark",
    primary: {
      main: "#1976d2",
    },
  },
  components: {
    MuiGrid: {
      styleOverrides: {
        root: {
          '& > *': {
            minWidth: 0, // Prevent grid items from overflowing
          },
        },
      },
    },
  },
});

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Global styles for consistent widget sizing
  const globalStyles = `
    html, body, #__next {
      height: 100%;
      margin: 0;
      padding: 0;
      overflow-x: hidden;
    }
    
    body {
      display: flex;
      flex-direction: column;
      min-height: 100vh;
    }
    
    .MuiDataGrid-root {
      min-height: 300px;
    }
    
    .MuiPaper-root {
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
  `;

  return (
    <html lang="en">
      <head>
        <style>{globalStyles}</style>
      </head>
      <body style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          <NavBar />
          <main style={{ 
            flex: 1,
            padding: "1.5rem 2rem",
            width: '100%',
            maxWidth: '100%',
            overflow: 'auto',
            boxSizing: 'border-box'
          }}>
            {children}
          </main>
        </ThemeProvider>
      </body>
    </html>
  );
}
