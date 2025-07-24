"use client";
import { useState } from "react";
import { TextField, IconButton, Box, Typography } from "@mui/material";
import SendIcon from "@mui/icons-material/Send";
import { fetcher } from "../utils/fetcher";

export default function ChatWidget() {
  const [msg, setMsg] = useState("");
  interface ChatMsg {
    sender: "user" | "bot";
    text: string;
  }
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [error, setError] = useState<string | null>(null);

  const handleSend = async () => {
    const trimmed = msg.trim();
    if (!trimmed) return;
    setMessages((prev) => [...prev, { sender: "user", text: trimmed }]);
    try {
      const data = await fetcher<{ reply: string }>("/api/chat", {
        method: "POST",
        body: JSON.stringify({ message: trimmed }),
        headers: { "Content-Type": "application/json" },
      });
      setMessages((prev) => [...prev, { sender: "bot", text: data.reply }]);
      setError(null);
    } catch {
      setError("Error al enviar el mensaje.");
    }
    setMsg("");
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
            <strong>{m.sender === "user" ? "Tú" : "Bot"}:</strong> {m.text}
          </Typography>
        ))}
      </Box>
      {error && (
        <Typography variant="body2" color="error" sx={{ mb: 1 }}>
          {error}
        </Typography>
      )}
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
