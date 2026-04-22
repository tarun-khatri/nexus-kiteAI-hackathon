"""
NEXUS - DataAgent
The Information Collector.

Collects real-time data from multiple free sources:
- Twitter/social media sentiment
- Crypto prices from CoinGecko
- News articles from RSS + CryptoPanic
- Whale (large) transactions

Other agents pay DataAgent via x402 for this data.
Price: $0.0001 per query
"""

import time
from datetime import datetime

from backend.agents.base_agent import BaseAgent
from backend.data_sources.twitter_scraper import TwitterScraper
from backend.data_sources.coingecko import CoinGeckoClient
from backend.data_sources.news_fetcher import NewsFetcher
from backend.data_sources.whale_tracker import WhaleTracker


class DataAgent(BaseAgent):
    """
    DataAgent - The raw data collector of the Nexus economy.
    Fetches data from free sources and sells it to other agents.
    """

    def __init__(self):
        super().__init__(
            agent_id="data_agent",
            name="Nexus-DataAgent-v1",
            description="Collects real-time data from Twitter, markets, news, and on-chain sources",
            capabilities=["twitter_data", "price_data", "whale_data", "news_data", "data_collection"],
            price_per_query=0.0001,
            keywords=[
                "data", "collect", "fetch", "tweets", "twitter", "price",
                "whale", "news", "headlines", "social", "market data",
                "latest", "happening", "info about", "what about",
            ],
            example_queries=[
                "Fetch KITE data",
                "Get tweets for ETH",
                "Whale activity for BTC",
                "Latest news on SOL",
            ],
            # Data-flow declarations (used by ReportAgent's topo-sort dispatcher).
            # DataAgent is a PRODUCER: needs nothing, produces all data buckets.
            consumes=[],
            provides=["raw_data"],
        )
        # Initialize free data sources
        self.twitter = TwitterScraper()
        self.coingecko = CoinGeckoClient()
        self.news = NewsFetcher()
        self.whale_tracker = WhaleTracker()

    def prepare_request(self, capability: str, context: dict) -> dict:
        """DataAgent always fetches all data types -- it doesn't need anything from context."""
        return {
            "type": "fetch_all",
            "capability": capability,
            "query": context.get("query", "KITE"),
            "data_types": ["twitter", "price", "whale", "news", "historical"],
        }

    async def handle_request(self, request: dict) -> dict:
        """
        Main entry point. Other agents call this with a request like:
        {"type": "fetch_all", "query": "KITE", "data_types": ["twitter", "price", "whale", "news"]}
        """
        start = await self.start_work(f"Fetching data for: {request.get('query', 'unknown')}")

        query = request.get("query", "KITE")
        data_types = request.get("data_types", ["twitter", "price", "whale", "news"])

        result = {
            "agent": self.name,
            "query": query,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {},
        }

        # Fetch data types - historical first (needed for technicals), then rest in parallel
        import asyncio

        # Historical FIRST (critical for RSI/MACD/Bollinger)
        if "historical" in data_types:
            try:
                result["data"]["historical"] = await self.coingecko.get_historical_prices(query, days=30)
                print(f"[DataAgent] Historical: {len(result['data']['historical'])} points")
            except Exception as e:
                print(f"[DataAgent] Historical failed: {e}")
                result["data"]["historical"] = []

        # Then fetch remaining in parallel
        tasks = {}
        if "twitter" in data_types:
            tasks["twitter"] = self.fetch_twitter(query)
        if "price" in data_types:
            tasks["price"] = self.fetch_price(query)
        if "whale" in data_types:
            tasks["whale"] = self.fetch_whale(query)
        if "news" in data_types:
            tasks["news"] = self.fetch_news(query)
        if "fear_greed" in data_types:
            tasks["fear_greed"] = self.coingecko.get_fear_greed_index()

        if tasks:
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for key, res in zip(tasks.keys(), results):
                if isinstance(res, Exception):
                    print(f"[DataAgent] {key} failed: {res}")
                    result["data"][key] = {}
                else:
                    result["data"][key] = res

        # === Aggregate per-source health into a single `data_sources_status`
        # field so the frontend can show which sources succeeded/failed. This
        # is how NEXUS surfaces its internal fallback "thinking" to the user.
        sources_status = {}
        degraded = []

        def _check(category: str, scraper_obj):
            st = getattr(scraper_obj, "last_source_status", {}) or {}
            if not st:
                return
            sources_status[category] = st
            used = st.get("source_used") or "unavailable"
            if used == "unavailable":
                degraded.append(f"{category}:all_failed")
                return
            # Any tried-but-failed sub-source = degraded
            for sub, info in st.items():
                if isinstance(info, dict) and info.get("tried") and not info.get("ok"):
                    degraded.append(f"{category}.{sub}")

        if "twitter" in data_types:
            _check("twitter", self.twitter)
        if "price" in data_types or "historical" in data_types:
            _check("price", self.coingecko)
        if "whale" in data_types:
            _check("whale", self.whale_tracker)
        if "news" in data_types:
            _check("news", self.news)

        result["data_sources_status"] = sources_status
        result["degraded_sources"] = degraded

        duration = await self.complete_work(f"Data fetched for {query}", start)
        result["duration_ms"] = duration

        return result

    async def fetch_twitter(self, query: str) -> dict:
        """Fetch Twitter/social data about a topic"""
        tweets = await self.twitter.fetch_tweets(query, max_results=30)
        return {
            "tweets": tweets,
            "total_count": len(tweets),
            "sources": list(set(t.get("source", "unknown") for t in tweets)),
        }

    async def fetch_price(self, token: str) -> dict:
        """Fetch current price data from CoinGecko (free)"""
        return await self.coingecko.get_current_price(token)

    async def fetch_whale(self, token: str) -> dict:
        """Fetch whale transaction data"""
        return await self.whale_tracker.get_whale_activity(token)

    async def fetch_news(self, query: str) -> dict:
        """Fetch news articles from free sources"""
        articles = await self.news.fetch_news(query, max_results=15)
        return {
            "articles": articles,
            "total_count": len(articles),
            "sources": list(set(a.get("provider", "unknown") for a in articles)),
        }

    async def cleanup(self):
        """Close all HTTP clients"""
        await self.twitter.close()
        await self.coingecko.close()
        await self.news.close()
        await self.whale_tracker.close()
