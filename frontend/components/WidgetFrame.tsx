"use client";
import { Paper } from "@mui/material";
import { ReactNode } from "react";

interface Props {
  title: string;
  children: ReactNode;
}

export default function WidgetFrame({ title, children }: Props) {
  return (
    <Paper
      elevation={3}
      sx={{
        p: 1,
        height: "100%",
        boxSizing: "border-box",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <h4 className="widget-drag-handle" style={{ cursor: "move" }}>{title}</h4>
      {children}
    </Paper>
  );
}
