"use client";
import Link from "next/link";
import { AppBar, Toolbar, Typography, Button } from "@mui/material";

export default function NavBar() {
  return (
    <AppBar position="static" color="primary">
      <Toolbar>
        <Typography variant="h6" sx={{ flexGrow: 1 }}>
          TradAI
        </Typography>
        <Button color="inherit" component={Link} href="/">
          Dashboard
        </Button>
        <Button color="inherit" component={Link} href="/markets">
          Markets
        </Button>
        <Button color="inherit" component={Link} href="/strategies">
          Strategies
        </Button>
        <Button color="inherit" component={Link} href="/settings">
          Settings
        </Button>
      </Toolbar>
    </AppBar>
  );
}
