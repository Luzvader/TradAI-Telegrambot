"use client";
import { useState } from "react";
import { TextField, IconButton, Box, Typography } from "@mui/material";
import SendIcon from "@mui/icons-material/Send";

export default function ChatWidget() {
  const [msg, setMsg] = useState("");
  const [messages, setMessages] = useState<string[]>([]);

  const handleSend = () => {
    const trimmed = msg.trim();
    if (!trimmed) return;
    setMessages((prev) => [...prev, trimmed]);
    setMsg("");
    // TODO: send to backend
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      {/* Conversation area */}
      <Box
        sx={{
          flex: "1 1 0%",
          overflowY: "auto",
          mb: 1,
          border: 1,
          borderColor: "divider",
          borderRadius: 1,
          p: 1,
          minHeight: 0,
          maxHeight: "100%",
        }}
      >
        {messages.map((m, i) => (
          <Typography variant="body2" key={i} sx={{ mb: 0.5 }}>
            {m}
          </Typography>
        ))}
      </Box>
      {/* Input */}
      <TextField
        sx={{ flexShrink: 0 }}
        size="small"
        fullWidth
        placeholder="Pregunta al bot..."
        value={msg}
        onChange={(e) => setMsg(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
          }
        }}
        InputProps={{
          endAdornment: (
            <IconButton size="small" onClick={handleSend} disabled={!msg.trim()}>
              <SendIcon fontSize="small" />
            </IconButton>
          ),
        }}
      />
    </Box>
  );
}
