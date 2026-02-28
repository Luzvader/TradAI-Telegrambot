"""
Obtención de noticias y contexto geopolítico / sectorial.
Usa exclusivamente fuentes RSS gratuitas.
"""

import asyncio
import logging
from typing import Any

import feedparser

from database import repository as repo
from data.cache import news_cache

logger = logging.getLogger(__name__)

# ── Fuentes RSS gratuitas ───────────────────────────────────
RSS_FEEDS = {
    "macro": [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://feeds.reuters.com/reuters/topNews",
        "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB?hl=en-US&gl=US&ceid=US:en",
    ],
    "geopolitical": [
        "https://feeds.reuters.com/Reuters/worldNews",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
    ],
    "sector_tech": [
        "https://feeds.reuters.com/reuters/technologyNews",
        "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
    ],
    "sector_finance": [
        "https://feeds.reuters.com/reuters/financials",
        "https://feeds.bbci.co.uk/news/business/rss.xml",
    ],
    "sector_healthcare": [
        "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",
    ],
    "sector_energy": [
        "https://news.google.com/rss/search?q=energy+oil+commodities&hl=en-US&gl=US&ceid=US:en",
    ],
}


async def fetch_rss_news(
    keyword: str | None = None, feed_type: str = "macro", max_items: int = 10
) -> list[dict[str, Any]]:
    """Obtiene noticias de fuentes RSS (fallback gratuito). Usa caché."""
    cache_key = f"rss:{feed_type}:{keyword or 'all'}"
    cached = news_cache.get(cache_key)
    if cached is not None:
        return cached

    feeds = RSS_FEEDS.get(feed_type, RSS_FEEDS["macro"])
    articles: list[dict[str, Any]] = []

    for feed_url in feeds:
        try:
            parsed = await asyncio.to_thread(feedparser.parse, feed_url)
            for entry in parsed.entries[:max_items]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                if keyword and keyword.lower() not in (title + summary).lower():
                    continue
                articles.append({
                    "title": title,
                    "description": summary,
                    "source": parsed.feed.get("title", feed_url),
                    "url": entry.get("link", ""),
                    "published_at": entry.get("published", ""),
                })
        except Exception as e:
            logger.warning(f"Error leyendo RSS {feed_url}: {e}")

    result = articles[:max_items]
    news_cache.set(cache_key, result)
    return result


async def get_geopolitical_context() -> str:
    """Genera un resumen de contexto geopolítico actual."""
    news = await fetch_rss_news(feed_type="geopolitical", max_items=15)
    if not news:
        return "No se pudo obtener contexto geopolítico actual."

    headlines = "\n".join(
        [f"- {n['title']} ({n['source']})" for n in news[:10]]
    )
    return f"Titulares geopolíticos recientes:\n{headlines}"


async def get_sector_news(sector: str) -> list[dict[str, Any]]:
    """Obtiene noticias relevantes para un sector via RSS."""
    sector_lower = sector.lower()
    if "tech" in sector_lower or "software" in sector_lower or "semiconductor" in sector_lower:
        feed_type = "sector_tech"
    elif "financ" in sector_lower or "bank" in sector_lower:
        feed_type = "sector_finance"
    elif "health" in sector_lower or "pharma" in sector_lower or "biotech" in sector_lower:
        feed_type = "sector_healthcare"
    elif "energy" in sector_lower or "oil" in sector_lower or "utilit" in sector_lower:
        feed_type = "sector_energy"
    else:
        # Buscar por keyword en feeds macro
        return await fetch_rss_news(keyword=sector, feed_type="macro", max_items=5)

    return await fetch_rss_news(feed_type=feed_type, max_items=5)


async def save_context_snapshot() -> None:
    """Guarda una instantánea del contexto actual en la DB."""
    geo = await get_geopolitical_context()
    await repo.save_market_context(
        context_type="geopolitical",
        summary=geo,
        source="RSS",
    )
    logger.info("📰 Contexto geopolítico guardado en DB")
