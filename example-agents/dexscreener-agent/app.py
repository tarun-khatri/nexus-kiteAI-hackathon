"""
NEXUS External Agent: DEXScreener

Standalone agent that registers with NEXUS marketplace and provides
real-time DEX trading pair data across all chains (Ethereum, Solana,
BSC, Polygon, Arbitrum, Base, etc.).

Data source: DEXScreener API (https://api.dexscreener.com)
- 100% free, no API key required
- Covers 40+ chains, all major DEXs
- Returns price spread, liquidity depth, volume per DEX

This agent demonstrates how ANY developer can build an agent and
plug it into the NEXUS marketplace for x402 micropayments.

Run: uvicorn app:app --port 5002
"""

import os
import httpx
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI

NEXUS_URL = os.getenv("NEXUS_URL", "http://localhost:8000")
AGENT_PORT = int(os.getenv("AGENT_PORT", "5002"))
PUBLIC_URL = os.getenv("PUBLIC_URL", f"http://localhost:{AGENT_PORT}")

DEXSCREENER_BASE = "https://api.dexscreener.com"


async def register_with_nexus():
    """Register this agent in the NEXUS marketplace on startup."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{NEXUS_URL}/api/marketplace/register",
                json={
                    "name": "DEXScreener-Agent-v1",
                    "description": (
                        "Real-time DEX trading pair data across 40+ chains. "
                        "Returns price spread, liquidity depth, and 24h volume per DEX "
                        "(Uniswap, PancakeSwap, Raydium, etc.). Powered by DEXScreener (free, no API key)."
                    ),
                    "capabilities": ["dex_data", "liquidity_analysis"],
                    "price_per_query": 0.0001,
                    "callback_url": f"{PUBLIC_URL}/invoke",
                    "owner_address": "0xDEXScreener_Agent_Owner",
                    "keywords": [
                        "dex", "liquidity", "pool depth", "spread", "uniswap",
                        "pancakeswap", "raydium", "sushiswap", "pair price", "amm",
                    ],
                    "example_queries": [
                        "KITE liquidity across DEXs",
                        "Deepest pool for UNI",
                        "Price spread for PEPE across decentralized exchanges",
                    ],
                    "capability_specs": [
                        {
                            "name": "dex_data",
                            "description": "Real-time DEX pair data (price, liquidity, volume) across 40+ chains.",
                            "input_schema": {
                                "type": "object",
                                "properties": {
                                    "identifier": {"type": "string", "format": "string"},
                                },
                                "required": ["identifier"],
                            },
                            "output_schema": {
                                "type": "object",
                                "properties": {
                                    "top_pairs": {"type": "array"},
                                    "best_liquidity_dex": {"type": "string"},
                                    "price_spread_pct_across_dexs": {"type": "number"},
                                },
                            },
                            "enrichment_suggestions": [],
                            "price_usdc": 0.0001,
                            "timeout_ms": 20000,
                        },
                        {
                            "name": "liquidity_analysis",
                            "description": "Aggregate liquidity depth and cross-DEX spread analysis for a token.",
                            "input_schema": {
                                "type": "object",
                                "properties": {
                                    "identifier": {"type": "string", "format": "string"},
                                },
                                "required": ["identifier"],
                            },
                            "output_schema": {"type": "object"},
                            "enrichment_suggestions": [],
                            "price_usdc": 0.0001,
                            "timeout_ms": 20000,
                        },
                    ],
                },
            )
            if response.status_code == 200:
                data = response.json()
                print(f"[DEXScreener Agent] Registered in NEXUS marketplace!")
                print(f"[DEXScreener Agent] Agent ID: {data.get('agent_id')}")
                passport = data.get('passport_id') or 'local-only (on-chain registration skipped or already exists)'
                print(f"[DEXScreener Agent] Passport: {str(passport)[:40]}...")
            else:
                print(f"[DEXScreener Agent] Registration failed: {response.text}")
        except Exception as e:
            print(f"[DEXScreener Agent] Could not register (NEXUS not running?): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 50)
    print("  NEXUS External Agent: DEXScreener")
    print("  DEX pair data across 40+ chains")
    print("  Data source: DEXScreener (free, no API key)")
    print("=" * 50)
    await register_with_nexus()
    yield


app = FastAPI(title="DEXScreener Agent", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agent": "DEXScreener-Agent-v1",
        "capabilities": ["dex_data", "liquidity_analysis"],
    }


@app.post("/invoke")
async def invoke(request: dict):
    """
    Callback endpoint that NEXUS marketplace calls.
    Fetches real DEX pair data from DEXScreener.

    request = {
        "type": "dex_data" | "liquidity_analysis",
        "identifier": "KITE" | "0x...tokenAddress",  # new typed path
        "query": "KITE" | "0x...tokenAddress",       # legacy
    }
    """
    query = (request.get("identifier") or request.get("query") or "").strip()
    if not query:
        return {"error": "identifier (symbol or 0x address) is required"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        result = {
            "agent": "DEXScreener-Agent-v1",
            "query": query,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {},
        }

        try:
            # DEXScreener supports both symbol search and address lookup.
            # Case-insensitive on the 0x prefix so any checksum format works.
            if query.lower().startswith("0x") and len(query) == 42:
                url = f"{DEXSCREENER_BASE}/latest/dex/tokens/{query.lower()}"
            else:
                url = f"{DEXSCREENER_BASE}/latest/dex/search?q={query}"

            resp = await client.get(url)
            if resp.status_code != 200:
                result["data"]["error"] = f"DEXScreener returned HTTP {resp.status_code}"
                return result

            payload = resp.json()
            pairs = payload.get("pairs") or []

            if not pairs:
                result["data"] = {
                    "pairs_found": 0,
                    "message": f"No DEX pairs found for '{query}'",
                    "source": "dexscreener",
                    "data_source_real": True,
                }
                return result

            # Sort by liquidity (highest first) and take top 10
            pairs_sorted = sorted(
                pairs,
                key=lambda p: (p.get("liquidity") or {}).get("usd", 0) or 0,
                reverse=True,
            )[:10]

            top_pairs = []
            total_liquidity = 0.0
            total_volume_24h = 0.0

            for p in pairs_sorted:
                liquidity_usd = (p.get("liquidity") or {}).get("usd", 0) or 0
                volume_24h = (p.get("volume") or {}).get("h24", 0) or 0
                price_change_24h = (p.get("priceChange") or {}).get("h24", 0) or 0
                txns_24h = (p.get("txns") or {}).get("h24") or {}
                buys_24h = txns_24h.get("buys", 0) or 0
                sells_24h = txns_24h.get("sells", 0) or 0

                total_liquidity += liquidity_usd
                total_volume_24h += volume_24h

                top_pairs.append({
                    "dex": p.get("dexId", "unknown"),
                    "chain": p.get("chainId", "unknown"),
                    "pair_address": p.get("pairAddress"),
                    "base_token": (p.get("baseToken") or {}).get("symbol"),
                    "quote_token": (p.get("quoteToken") or {}).get("symbol"),
                    "price_usd": float(p.get("priceUsd") or 0),
                    "price_change_24h_pct": round(price_change_24h, 2),
                    "volume_24h_usd": round(volume_24h, 2),
                    "liquidity_usd": round(liquidity_usd, 2),
                    "buys_24h": buys_24h,
                    "sells_24h": sells_24h,
                    "url": p.get("url"),
                })

            # Find best liquidity DEX
            best = top_pairs[0] if top_pairs else None
            best_dex_label = (
                f"{best['dex']}-{best['chain']}" if best else "unknown"
            )

            # Compute liquidity/volume spread analysis
            prices = [p["price_usd"] for p in top_pairs if p["price_usd"] > 0]
            price_spread_pct = 0.0
            if len(prices) >= 2:
                min_p, max_p = min(prices), max(prices)
                if min_p > 0:
                    price_spread_pct = round(((max_p - min_p) / min_p) * 100, 2)

            result["data"] = {
                "pairs_found": len(pairs),
                "top_pairs": top_pairs,
                "total_liquidity_usd": round(total_liquidity, 2),
                "total_volume_24h_usd": round(total_volume_24h, 2),
                "best_liquidity_dex": best_dex_label,
                "price_spread_pct_across_dexs": price_spread_pct,
                "chains_present": list(set(p["chain"] for p in top_pairs)),
                "dexs_present": list(set(p["dex"] for p in top_pairs)),
                "source": "dexscreener",
                "data_source_real": True,
            }

        except Exception as e:
            result["data"]["error"] = f"DEXScreener fetch failed: {str(e)}"
            result["data"]["data_source_real"] = False

        return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
