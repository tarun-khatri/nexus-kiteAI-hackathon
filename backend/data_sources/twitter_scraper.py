"""
NEXUS - Twitter/Social Data Scraper (REAL DATA)
Fetches REAL tweets using Rettiwt-API via Node.js microservice.

Architecture:
  Python backend --> HTTP --> Node.js twitter-service (port 3001) --> Rettiwt-API --> Twitter/X

Fallback chain:
  1. Rettiwt microservice (real tweets with engagement metrics)
  2. Nitter RSS (real tweets, no engagement metrics)
  3. CryptoPanic social aggregator (real social mentions)
  4. NEVER returns fake data - returns empty with error flag instead
"""

import os
import asyncio
import httpx
import feedparser
from datetime import datetime, timedelta
from typing import Optional

# Where the Node-based twitter scraping microservice lives.
# Dev default: localhost. In docker-compose the backend container reaches
# the service via its Docker service name: TWITTER_SERVICE_URL=http://twitter-service:3001
TWITTER_SERVICE_URL = os.getenv("TWITTER_SERVICE_URL", "http://localhost:3001")


class TwitterScraper:
    """Fetches REAL social media data for sentiment analysis"""

    NITTER_INSTANCES = [
        "https://nitter.net",
        "https://nitter.privacydev.net",
        "https://nitter.poast.org",
    ]

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NexusBot/1.0)"},
        )
        self._service_available = None
        # Per-source health telemetry. Reset at the start of every fetch_tweets call
        # so callers can read `scraper.last_source_status` after the call.
        self.last_source_status: dict = {}

    async def fetch_tweets(self, query: str, max_results: int = 30) -> list[dict]:
        """
        Fetch recent tweets about a topic.
        Tries real sources only - NEVER generates fake data.
        Updates `self.last_source_status` with per-source health info.
        """
        all_tweets: list[dict] = []
        status = {
            "rettiwt": {"ok": False, "count": 0, "error": None, "tried": False},
            "nitter": {"ok": False, "count": 0, "error": None, "tried": False},
            "cryptopanic": {"ok": False, "count": 0, "error": None, "tried": False},
            "source_used": None,
            "total_tweets": 0,
        }

        # Method 1: Rettiwt microservice (best - real tweets with engagement)
        status["rettiwt"]["tried"] = True
        tweets, rerr = await self._fetch_from_rettiwt_service(query, max_results)
        if tweets:
            all_tweets.extend(tweets)
            status["rettiwt"]["ok"] = True
            status["rettiwt"]["count"] = len(tweets)
            if status["source_used"] is None:
                status["source_used"] = "rettiwt"
            print(f"[Twitter] Got {len(tweets)} REAL tweets from Rettiwt service")
        else:
            status["rettiwt"]["error"] = rerr

        # Method 2: Nitter RSS fallback (real tweets, no engagement metrics)
        if len(all_tweets) < max_results:
            status["nitter"]["tried"] = True
            remaining = max_results - len(all_tweets)
            nitter_tweets, nerr = await self._fetch_nitter_rss(query, remaining)
            if nitter_tweets:
                all_tweets.extend(nitter_tweets)
                status["nitter"]["ok"] = True
                status["nitter"]["count"] = len(nitter_tweets)
                if status["source_used"] is None:
                    status["source_used"] = "nitter"
                print(f"[Twitter] Got {len(nitter_tweets)} tweets from Nitter RSS")
            else:
                status["nitter"]["error"] = nerr

        # Method 3: CryptoPanic (real social mentions)
        if len(all_tweets) < 5:
            status["cryptopanic"]["tried"] = True
            crypto_tweets, cerr = await self._fetch_crypto_social(query, max_results)
            if crypto_tweets:
                all_tweets.extend(crypto_tweets)
                status["cryptopanic"]["ok"] = True
                status["cryptopanic"]["count"] = len(crypto_tweets)
                if status["source_used"] is None:
                    status["source_used"] = "cryptopanic"
                print(f"[Twitter] Got {len(crypto_tweets)} social mentions from CryptoPanic")
            else:
                status["cryptopanic"]["error"] = cerr

        if not all_tweets:
            print(f"[Twitter] WARNING: No real tweets found for '{query}'. All sources failed.")

        # Tag all tweets with data_source_real flag
        for t in all_tweets:
            t["data_source_real"] = True

        status["total_tweets"] = len(all_tweets)
        self.last_source_status = status
        return all_tweets[:max_results]

    async def _fetch_from_rettiwt_service(self, query: str, max_results: int) -> tuple[list[dict], Optional[str]]:
        """
        Fetch from the Node.js Rettiwt microservice.
        Returns (tweets, error_string_or_none).
        """
        try:
            url = f"{TWITTER_SERVICE_URL}/search"
            response = await self.client.get(
                url,
                params={"q": query, "count": min(max_results, 50)},
                timeout=15.0,
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("error"):
                    err = str(data["error"])[:120]
                    print(f"[Twitter] Rettiwt service error: {err}")
                    return [], f"rettiwt_upstream: {err}"

                tweets = []
                for t in data.get("tweets", []):
                    tweets.append({
                        "text": t.get("text", ""),
                        "author": f"@{t.get('username', 'unknown')}",
                        "date": t.get("timestamp", datetime.utcnow().isoformat()),
                        "url": f"https://x.com/{t.get('username')}/status/{t.get('id', '')}",
                        "source": "twitter",
                        "likes": t.get("likes", 0),
                        "retweets": t.get("retweets", 0),
                        "views": t.get("views", 0),
                        "replies": t.get("replies", 0),
                    })
                if not tweets:
                    return [], "empty_response"
                return tweets, None
            return [], f"http_{response.status_code}"
        except httpx.ConnectError:
            if self._service_available is not False:
                print("[Twitter] Rettiwt microservice not running (start: cd twitter-service && npm start)")
                self._service_available = False
            return [], "service_not_running"
        except Exception as e:
            print(f"[Twitter] Rettiwt service error: {e}")
            return [], f"exception: {str(e)[:100]}"

    async def _fetch_nitter_rss(self, query: str, max_results: int) -> tuple[list[dict], Optional[str]]:
        """Fetch from Nitter RSS feeds (free, no auth). Returns (tweets, error_string_or_none)."""
        tweets: list[dict] = []
        search_query = query.replace(" ", "+")
        last_err: Optional[str] = None

        for instance in self.NITTER_INSTANCES:
            try:
                url = f"{instance}/search/rss?f=tweets&q={search_query}"
                response = await self.client.get(url, timeout=10.0)
                if response.status_code == 200:
                    feed = feedparser.parse(response.text)
                    for entry in feed.entries[:max_results]:
                        tweets.append({
                            "text": entry.get("title", "") or entry.get("summary", ""),
                            "author": entry.get("author", "unknown"),
                            "date": entry.get("published", datetime.utcnow().isoformat()),
                            "url": entry.get("link", ""),
                            "source": "twitter",
                            "likes": 0,
                            "retweets": 0,
                        })
                    if tweets:
                        return tweets, None
                else:
                    last_err = f"{instance}: http_{response.status_code}"
            except Exception as e:
                err_msg = str(e)[:100]
                print(f"[Twitter] Nitter {instance} failed: {err_msg}")
                last_err = f"{instance}: {err_msg}"
                continue

        return tweets, last_err or "all_nitter_instances_failed"

    async def _fetch_crypto_social(self, query: str, max_results: int) -> tuple[list[dict], Optional[str]]:
        """Fetch from free crypto social aggregators. Returns (tweets, error_string_or_none)."""
        tweets: list[dict] = []
        try:
            url = f"https://cryptopanic.com/api/free/v1/posts/?filter=hot&currencies={query.upper()}"
            response = await self.client.get(url, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                for post in data.get("results", [])[:max_results]:
                    tweets.append({
                        "text": post.get("title", ""),
                        "author": post.get("source", {}).get("title", "unknown"),
                        "date": post.get("published_at", datetime.utcnow().isoformat()),
                        "url": post.get("url", ""),
                        "source": "cryptopanic",
                        "likes": post.get("votes", {}).get("positive", 0),
                        "retweets": 0,
                    })
                if not tweets:
                    return [], "empty_response"
                return tweets, None
            return [], f"http_{response.status_code}"
        except Exception as e:
            err = str(e)[:100]
            print(f"[Twitter] CryptoPanic failed: {err}")
            return [], f"exception: {err}"

    async def close(self):
        await self.client.aclose()
