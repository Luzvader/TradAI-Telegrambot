"use client";
import * as React from "react";
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import NavBar from "../components/NavBar";

const theme = createTheme({
  palette: {
    mode: "dark",
    primary: {
      main: "#1976d2",
    },
  },
});

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          <NavBar />
          <main style={{ padding: "1rem" }}>{children}</main>
        </ThemeProvider>
      </body>
    </html>
  );
}
