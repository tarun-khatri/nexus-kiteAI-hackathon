"""
NEXUS - CoinGecko Price Data (REAL DATA with retry + cache)
Fetches real-time crypto prices, market data, and historical data.
CoinGecko free tier: 30 requests/minute, no API key required for basic endpoints.

Features:
- Dynamic token ID resolution (supports ANY token, not just hardcoded list)
- Retry logic with exponential backoff
- In-memory TTL cache to prevent rate limiting
- NEVER returns fake prices - returns error flag if all attempts fail
"""

import asyncio
import time
import httpx
from datetime import datetime
from typing import Optional

from backend.config import settings


class ResponseCache:
    """Simple in-memory TTL cache - no external dependencies"""

    def __init__(self):
        self._cache: dict[str, tuple[float, any]] = {}  # key -> (expires_at, data)

    def get(self, key: str):
        entry = self._cache.get(key)
        if entry and time.time() < entry[0]:
            return entry[1]
        if entry:
            del self._cache[key]
        return None

    def set(self, key: str, data, ttl_seconds: int):
        self._cache[key] = (time.time() + ttl_seconds, data)


class CoinGeckoClient:
    """Fetches real crypto market data from CoinGecko with retry logic"""

    BASE_URL = "https://api.coingecko.com/api/v3"

    # Known token mappings (fast path - avoids search API call)
    TOKEN_MAP = {
        "KITE": "kite-ai",
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "USDC": "usd-coin",
        "USDT": "tether",
        "BNB": "binancecoin",
        "AVAX": "avalanche-2",
        "NEAR": "near",
        "DOT": "polkadot",
        "MATIC": "matic-network",
        "ADA": "cardano",
        "DOGE": "dogecoin",
        "SHIB": "shiba-inu",
        "LINK": "chainlink",
        "UNI": "uniswap",
        "AAVE": "aave",
        "ARB": "arbitrum",
        "OP": "optimism",
        "APT": "aptos",
        "SUI": "sui",
        "SEI": "sei-network",
        "TIA": "celestia",
        "JUP": "jupiter-exchange-solana",
        "WIF": "dogwifcoin",
        "PEPE": "pepe",
        "BONK": "bonk",
        "RENDER": "render-token",
        "FET": "fetch-ai",
        "TAO": "bittensor",
        "INJ": "injective-protocol",
        "ATOM": "cosmos",
        "XRP": "ripple",
        "LTC": "litecoin",
    }

    # Cache for dynamic token resolution
    _token_cache: dict[str, str] = {}

    # Cache TTLs (seconds)
    CACHE_TTL_PRICE = 60         # Current price: 1 minute
    CACHE_TTL_HISTORICAL = 300   # Historical data: 5 minutes
    CACHE_TTL_TRENDING = 120     # Trending: 2 minutes
    CACHE_TTL_FEAR_GREED = 300   # Fear & Greed: 5 minutes

    def __init__(self):
        self._cg_headers = {"Accept": "application/json"}
        if settings.coingecko_api_key:
            self._cg_headers["x-cg-demo-api-key"] = settings.coingecko_api_key
        self._cache = ResponseCache()
        # Per-call source health telemetry. Updated each fetch so DataAgent can
        # surface which source actually served the data.
        self.last_source_status: dict = {}

    def _new_client(self, timeout: float = 10.0) -> httpx.AsyncClient:
        """Create a fresh HTTP client per request to avoid event loop contention"""
        return httpx.AsyncClient(timeout=timeout, headers=self._cg_headers)

    async def _resolve_token_id(self, token: str) -> str:
        """Resolve ANY token symbol to its CoinGecko ID, with search fallback"""
        upper = token.upper()

        # Fast path: known mapping
        if upper in self.TOKEN_MAP:
            return self.TOKEN_MAP[upper]

        # Cache hit
        if upper in self._token_cache:
            return self._token_cache[upper]

        # Dynamic search: query CoinGecko search API
        try:
            url = f"{self.BASE_URL}/search"
            async with self._new_client() as client:
                response = await client.get(url, params={"query": token})
            if response.status_code == 200:
                data = response.json()
                coins = data.get("coins", [])
                for coin in coins:
                    if coin.get("symbol", "").upper() == upper:
                        coin_id = coin["id"]
                        self._token_cache[upper] = coin_id
                        print(f"[CoinGecko] Resolved {upper} -> {coin_id}")
                        return coin_id
                # If exact match not found, use first result
                if coins:
                    coin_id = coins[0]["id"]
                    self._token_cache[upper] = coin_id
                    print(f"[CoinGecko] Approximate: {upper} -> {coin_id}")
                    return coin_id
        except Exception as e:
            print(f"[CoinGecko] Search failed for {token}: {e}")

        return token.lower()

    async def _request_with_retry(self, url: str, params: dict = None, max_retries: int = 2) -> Optional[dict]:
        """Make HTTP request with fresh client per attempt"""
        for attempt in range(1, max_retries + 1):
            try:
                async with self._new_client(timeout=8.0) as client:
                    response = await client.get(url, params=params)

                    if response.status_code == 200:
                        return response.json()
                    elif response.status_code == 429:
                        wait = min(2 ** attempt, 3)
                        print(f"[CoinGecko] Rate limited. Retry {attempt}/{max_retries} in {wait}s")
                        await asyncio.sleep(wait)
                        continue
                    else:
                        print(f"[CoinGecko] HTTP {response.status_code} for {url}")
                        return None

            except Exception as e:
                print(f"[CoinGecko] Error: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(1)

        return None

    # CoinCap token ID mapping (different from CoinGecko)
    COINCAP_MAP = {
        "KITE": "kite-ai", "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
        "BNB": "binance-coin", "AVAX": "avalanche", "DOGE": "dogecoin",
        "ADA": "cardano", "XRP": "xrp", "DOT": "polkadot", "LINK": "chainlink",
        "UNI": "uniswap", "SHIB": "shiba-inu", "MATIC": "polygon",
        "ARB": "arbitrum", "OP": "optimism", "NEAR": "near-protocol",
        "ATOM": "cosmos", "LTC": "litecoin", "AAVE": "aave",
        "PEPE": "pepe", "SUI": "sui", "APT": "aptos",
    }

    async def get_current_price(self, token: str) -> dict:
        """
        Get current price with triple redundancy:
        1. CoinGecko (primary, 30 req/min)
        2. CoinCap (backup, free, no rate limit)
        3. CryptoCompare (fallback, free)
        NEVER returns fake data. Always returns from a real source.
        """
        cache_key = f"price:{token.upper()}"
        cached = self._cache.get(cache_key)
        if cached:
            self.last_source_status = {
                "source_used": cached.get("source", "cache"),
                "from_cache": True,
                "coingecko": {"tried": False},
                "coincap": {"tried": False},
                "cryptocompare": {"tried": False},
            }
            return cached

        status = {
            "source_used": None,
            "from_cache": False,
            "coingecko": {"ok": False, "tried": True, "error": None},
            "coincap": {"ok": False, "tried": False, "error": None},
            "cryptocompare": {"ok": False, "tried": False, "error": None},
        }

        # Source 1: CoinGecko
        result = await self._fetch_price_coingecko(token)
        if result:
            status["coingecko"]["ok"] = True
            status["source_used"] = "coingecko"
            self.last_source_status = status
            self._cache.set(cache_key, result, self.CACHE_TTL_PRICE)
            return result
        else:
            status["coingecko"]["error"] = "failed"

        # Source 2: CoinCap (free, unlimited)
        status["coincap"]["tried"] = True
        result = await self._fetch_price_coincap(token)
        if result:
            status["coincap"]["ok"] = True
            status["source_used"] = "coincap"
            self.last_source_status = status
            self._cache.set(cache_key, result, self.CACHE_TTL_PRICE)
            return result
        else:
            status["coincap"]["error"] = "failed"

        # Source 3: CryptoCompare (free, 100k req/month)
        status["cryptocompare"]["tried"] = True
        result = await self._fetch_price_cryptocompare(token)
        if result:
            status["cryptocompare"]["ok"] = True
            status["source_used"] = "cryptocompare"
            self.last_source_status = status
            self._cache.set(cache_key, result, self.CACHE_TTL_PRICE)
            return result
        else:
            status["cryptocompare"]["error"] = "failed"

        status["source_used"] = "unavailable"
        self.last_source_status = status
        print(f"[Price] WARNING: All 3 sources failed for {token}")
        return {
            "token": token.upper(),
            "price_usd": 0,
            "change_24h_pct": 0,
            "volume_24h": 0,
            "market_cap": 0,
            "source": "unavailable",
            "data_source_real": False,
            "error": f"All price sources failed for {token}",
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _fetch_price_coingecko(self, token: str) -> Optional[dict]:
        """CoinGecko - primary source (30 req/min free tier)"""
        token_id = await self._resolve_token_id(token)
        data = await self._request_with_retry(
            f"{self.BASE_URL}/simple/price",
            params={
                "ids": token_id,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
                "include_market_cap": "true",
                "include_last_updated_at": "true",
            },
        )
        if data and token_id in data:
            td = data[token_id]
            return {
                "token": token.upper(),
                "price_usd": td.get("usd", 0),
                "change_24h_pct": round(td.get("usd_24h_change", 0), 2),
                "volume_24h": td.get("usd_24h_vol", 0),
                "market_cap": td.get("usd_market_cap", 0),
                "last_updated": td.get("last_updated_at", 0),
                "source": "coingecko",
                "data_source_real": True,
                "timestamp": datetime.utcnow().isoformat(),
            }
        return None

    async def _fetch_price_coincap(self, token: str) -> Optional[dict]:
        """CoinCap - backup source (free, no rate limit, no key needed)"""
        try:
            cap_id = self.COINCAP_MAP.get(token.upper(), token.lower())
            async with httpx.AsyncClient(timeout=10.0) as cc:
                response = await cc.get(f"https://api.coincap.io/v2/assets/{cap_id}")
            if response.status_code == 200:
                asset = response.json().get("data", {})
                if asset and asset.get("priceUsd"):
                    price = float(asset["priceUsd"])
                    change = float(asset.get("changePercent24Hr", 0) or 0)
                    volume = float(asset.get("volumeUsd24Hr", 0) or 0)
                    mcap = float(asset.get("marketCapUsd", 0) or 0)
                    print(f"[CoinCap] Got price for {token}: ${price:.4f}")
                    return {
                        "token": token.upper(),
                        "price_usd": round(price, 6),
                        "change_24h_pct": round(change, 2),
                        "volume_24h": round(volume, 2),
                        "market_cap": round(mcap, 2),
                        "source": "coincap",
                        "data_source_real": True,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
        except Exception as e:
            print(f"[CoinCap] Failed for {token}: {e}")
        return None

    async def _fetch_price_cryptocompare(self, token: str) -> Optional[dict]:
        """CryptoCompare - third fallback (free, 100k req/month)"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as cc:
                response = await cc.get(
                    "https://min-api.cryptocompare.com/data/pricemultifull",
                    params={"fsyms": token.upper(), "tsyms": "USD"},
                )
            if response.status_code == 200:
                data = response.json().get("RAW", {}).get(token.upper(), {}).get("USD", {})
                if data and data.get("PRICE"):
                    print(f"[CryptoCompare] Got price for {token}: ${data['PRICE']:.4f}")
                    return {
                        "token": token.upper(),
                        "price_usd": round(data["PRICE"], 6),
                        "change_24h_pct": round(data.get("CHANGEPCT24HOUR", 0), 2),
                        "volume_24h": round(data.get("VOLUME24HOUR", 0), 2),
                        "market_cap": round(data.get("MKTCAP", 0), 2),
                        "source": "cryptocompare",
                        "data_source_real": True,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
        except Exception as e:
            print(f"[CryptoCompare] Failed for {token}: {e}")
        return None

    async def get_historical_prices(self, token: str, days: int = 30) -> list[dict]:
        """
        Get historical price data. CryptoCompare first (faster + more reliable),
        CoinGecko as backup.
        """
        cache_key = f"historical:{token.upper()}:{days}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        # Source 1: CryptoCompare (faster, free, reliable) - uses fresh client to avoid contention
        try:
            async with httpx.AsyncClient(timeout=15.0) as fresh_client:
                response = await fresh_client.get(
                    "https://min-api.cryptocompare.com/data/v2/histoday",
                    params={"fsym": token.upper(), "tsym": "USD", "limit": days},
                )
            if response.status_code == 200:
                entries = response.json().get("Data", {}).get("Data", [])
                if entries:
                    prices = [
                        {"timestamp": e["time"], "date": datetime.fromtimestamp(e["time"]).isoformat(), "price": e.get("close", 0)}
                        for e in entries if e.get("close", 0) > 0
                    ]
                    if len(prices) > 7:
                        print(f"[CryptoCompare] Got {len(prices)} historical prices for {token}")
                        self._cache.set(cache_key, prices, self.CACHE_TTL_HISTORICAL)
                        return prices
        except Exception as e:
            print(f"[CryptoCompare] Historical failed: {e}")

        # Source 2: CoinGecko (backup)
        token_id = await self._resolve_token_id(token)
        data = await self._request_with_retry(
            f"{self.BASE_URL}/coins/{token_id}/market_chart",
            params={"vs_currency": "usd", "days": str(days)},
        )
        if data and data.get("prices"):
            prices = [
                {"timestamp": ts / 1000, "date": datetime.fromtimestamp(ts / 1000).isoformat(), "price": p}
                for ts, p in data["prices"]
            ]
            self._cache.set(cache_key, prices, self.CACHE_TTL_HISTORICAL)
            return prices

        print(f"[Price] WARNING: No historical data from any source for {token}")
        return []

    async def get_trending(self) -> list[dict]:
        """Get trending coins on CoinGecko (free)"""
        data = await self._request_with_retry(f"{self.BASE_URL}/search/trending")
        if data:
            trending = []
            for item in data.get("coins", []):
                coin = item.get("item", {})
                trending.append({
                    "name": coin.get("name", ""),
                    "symbol": coin.get("symbol", ""),
                    "market_cap_rank": coin.get("market_cap_rank", 0),
                    "price_btc": coin.get("price_btc", 0),
                })
            return trending
        return []

    async def get_fear_greed_index(self) -> dict:
        """Get the crypto fear & greed index (free API)"""
        try:
            async with self._new_client() as client:
                response = await client.get("https://api.alternative.me/fng/?limit=1")
            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    entry = data["data"][0]
                    return {
                        "value": int(entry.get("value", 50)),
                        "classification": entry.get("value_classification", "Neutral"),
                        "timestamp": entry.get("timestamp", ""),
                        "data_source_real": True,
                    }
        except Exception:
            pass
        return {"value": 0, "classification": "Unavailable", "timestamp": "", "data_source_real": False}

    async def close(self):
        pass  # No persistent client to close - fresh clients per request
