"use client";
import { useEffect, useState } from "react";
import { Box, CircularProgress, Link, Typography } from "@mui/material";

interface NewsItem {
  title: string;
  link: string;
}

export default function NewsFeedWidget() {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchFeed() {
      try {
        const res = await fetch(
          "https://api.allorigins.win/raw?url=https://cointelegraph.com/rss"
        );
        if (!res.ok) throw new Error("Failed to fetch feed");
        const text = await res.text();
        const parser = new DOMParser();
        const xml = parser.parseFromString(text, "application/xml");
        const entries = Array.from(xml.querySelectorAll("item")).slice(0, 5);
        const news = entries.map((item) => ({
          title: item.querySelector("title")?.textContent || "",
          link: item.querySelector("link")?.textContent || "#",
        }));
        setItems(news);
      } catch (e) {
        console.error(e);
        setError("Error al cargar noticias");
      } finally {
        setLoading(false);
      }
    }
    fetchFeed();
  }, []);

  if (loading) {
    return (
      <Box sx={{ textAlign: "center" }}>
        <CircularProgress size={24} />
      </Box>
    );
  }

  if (error) {
    return (
      <Typography variant="body2" color="error">
        {error}
      </Typography>
    );
  }

  return (
    <Box>
      {items.map((item, idx) => (
        <Typography key={idx} variant="body2" sx={{ mb: 1 }}>
          <Link
            href={item.link}
            target="_blank"
            rel="noopener noreferrer"
            underline="hover"
          >
            {item.title}
          </Link>
        </Typography>
      ))}
    </Box>
  );
}
