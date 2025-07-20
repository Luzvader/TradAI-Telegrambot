"use client";
import { useState } from "react";
import { TextField, IconButton, Paper } from "@mui/material";
import SendIcon from "@mui/icons-material/Send";

export default function ChatWidget() {
  const [msg, setMsg] = useState("");
  const handleSend = () => {
    if (!msg.trim()) return;
    // TODO: connect to backend LLM chat endpoint
    setMsg("");
    alert("(Placeholder) Sent: " + msg);
  };
  return (
    <Paper style={{ padding: 8 }}>
      <TextField
        size="small"
        fullWidth
        placeholder="Pregunta al bot..."
        value={msg}
        onChange={(e) => setMsg(e.target.value)}
        InputProps={{
          endAdornment: (
            <IconButton size="small" onClick={handleSend}>
              <SendIcon fontSize="small" />
            </IconButton>
          ),
        }}
      />
    </Paper>
  );
}
