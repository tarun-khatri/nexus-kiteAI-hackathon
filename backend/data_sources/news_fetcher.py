"""
NEXUS - News Data Fetcher (FREE)
Fetches crypto news from multiple free sources:
1. Google News RSS (free, unlimited)
2. CryptoPanic API (free tier)
3. NewsAPI (free tier: 100 req/day)

Cost: $0
"""

import httpx
import feedparser
from datetime import datetime
from typing import Optional

from backend.config import settings


class NewsFetcher:
    """Fetches news articles from free sources"""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NexusBot/1.0)"},
        )
        self.last_source_status: dict = {}

    async def fetch_news(self, query: str, max_results: int = 20) -> list[dict]:
        """
        Fetch news from multiple free sources and combine.
        Returns deduplicated, sorted list of articles.
        """
        all_articles = []
        status = {
            "source_used": None,
            "google_rss": {"ok": False, "tried": True, "count": 0},
            "cryptopanic": {"ok": False, "tried": True, "count": 0},
            "newsapi": {"ok": False, "tried": True, "count": 0},
        }

        # Fetch from all sources in parallel
        import asyncio
        results = await asyncio.gather(
            self._fetch_google_news_rss(query, max_results),
            self._fetch_cryptopanic(query, max_results),
            self._fetch_newsapi(query, max_results),
            return_exceptions=True,
        )

        source_keys = ["google_rss", "cryptopanic", "newsapi"]
        for src_key, result in zip(source_keys, results):
            if isinstance(result, list) and result:
                all_articles.extend(result)
                status[src_key]["ok"] = True
                status[src_key]["count"] = len(result)
                if status["source_used"] is None:
                    status["source_used"] = src_key
            elif isinstance(result, Exception):
                status[src_key]["error"] = str(result)[:100]

        # Deduplicate by title similarity
        seen_titles = set()
        unique_articles = []
        for article in all_articles:
            title_key = article["title"][:50].lower()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_articles.append(article)

        # Sort by date (newest first) and limit
        unique_articles.sort(key=lambda x: x.get("date", ""), reverse=True)
        if status["source_used"] is None:
            status["source_used"] = "unavailable"
        self.last_source_status = status
        return unique_articles[:max_results]

    async def _fetch_google_news_rss(self, query: str, max_results: int) -> list[dict]:
        """Google News RSS - free, unlimited, no auth"""
        articles = []
        try:
            search_query = query.replace(" ", "+")
            url = f"https://news.google.com/rss/search?q={search_query}+crypto&hl=en-US&gl=US&ceid=US:en"
            response = await self.client.get(url)
            if response.status_code == 200:
                feed = feedparser.parse(response.text)
                for entry in feed.entries[:max_results]:
                    articles.append({
                        "title": entry.get("title", ""),
                        "summary": entry.get("summary", ""),
                        "url": entry.get("link", ""),
                        "source": entry.get("source", {}).get("title", "Google News"),
                        "date": entry.get("published", datetime.utcnow().isoformat()),
                        "provider": "google_news",
                    })
        except Exception as e:
            print(f"[News] Google News RSS error: {e}")
        return articles

    async def _fetch_cryptopanic(self, query: str, max_results: int) -> list[dict]:
        """CryptoPanic - free tier available"""
        articles = []
        try:
            params = {"filter": "important"}
            if settings.cryptopanic_key:
                params["auth_token"] = settings.cryptopanic_key
            else:
                # Use the free public endpoint
                params["public"] = "true"

            url = "https://cryptopanic.com/api/v1/posts/"
            response = await self.client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                for post in data.get("results", [])[:max_results]:
                    articles.append({
                        "title": post.get("title", ""),
                        "summary": "",
                        "url": post.get("url", ""),
                        "source": post.get("source", {}).get("title", "CryptoPanic"),
                        "date": post.get("published_at", datetime.utcnow().isoformat()),
                        "provider": "cryptopanic",
                        "sentiment": post.get("votes", {}).get("positive", 0) - post.get("votes", {}).get("negative", 0),
                    })
        except Exception as e:
            print(f"[News] CryptoPanic error: {e}")
        return articles

    async def _fetch_newsapi(self, query: str, max_results: int) -> list[dict]:
        """NewsAPI - free tier: 100 req/day"""
        articles = []
        if not settings.newsapi_key:
            return articles

        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": f"{query} crypto",
                "sortBy": "publishedAt",
                "pageSize": max_results,
                "apiKey": settings.newsapi_key,
                "language": "en",
            }
            response = await self.client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                for article in data.get("articles", [])[:max_results]:
                    articles.append({
                        "title": article.get("title", ""),
                        "summary": article.get("description", ""),
                        "url": article.get("url", ""),
                        "source": article.get("source", {}).get("name", "NewsAPI"),
                        "date": article.get("publishedAt", datetime.utcnow().isoformat()),
                        "provider": "newsapi",
                    })
        except Exception as e:
            print(f"[News] NewsAPI error: {e}")
        return articles

    async def close(self):
        await self.client.aclose()
