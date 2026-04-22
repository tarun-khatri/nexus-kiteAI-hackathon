"""
NEXUS Example External Agent: DeFi Metrics
Demonstrates how ANYONE can build an agent and register it in the NEXUS marketplace.

This standalone agent:
1. Registers itself with NEXUS marketplace on startup
2. Provides DeFi protocol data from DeFiLlama (free, no API key)
3. Gets paid in x402 micropayments for each query
4. Builds reputation through quality of responses

Run: uvicorn app:app --port 5001
"""

import asyncio
import os
import httpx
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI

# Env-var-driven config so this image runs behind any topology:
#   dev       : localhost defaults
#   docker    : NEXUS_URL=http://backend:8000  PUBLIC_URL=http://defi-agent:5001
#   split-host: NEXUS_URL=https://api.example  PUBLIC_URL=https://defi.example
NEXUS_URL = os.getenv("NEXUS_URL", "http://localhost:8000")
AGENT_PORT = int(os.getenv("AGENT_PORT", "5001"))
PUBLIC_URL = os.getenv("PUBLIC_URL", f"http://localhost:{AGENT_PORT}")


async def register_with_nexus():
    """Register this agent in the NEXUS marketplace"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{NEXUS_URL}/api/marketplace/register",
                json={
                    "name": "DeFiLlama-MetricsAgent-v1",
                    "description": "Provides real-time DeFi protocol TVL, yield/APY data, and chain analytics from DeFiLlama (free, no API key). Covers 3000+ protocols across 200+ chains.",
                    "capabilities": ["defi_data", "defi_analysis"],
                    "price_per_query": 0.0001,
                    "callback_url": f"{PUBLIC_URL}/invoke",
                    "owner_address": "0xDeFi_Agent_Owner",
                    "keywords": [
                        "defi", "yield", "apy", "tvl", "lending", "borrow",
                        "liquidity mining", "aave", "compound", "curve",
                        "staking rewards", "protocol",
                    ],
                    "example_queries": [
                        "Top DeFi protocols by TVL",
                        "Current best stablecoin yields on Arbitrum",
                        "AAVE TVL trend last 7 days",
                    ],
                    # Typed capability specs — identifier is free-form (symbol or protocol slug).
                    "capability_specs": [
                        {
                            "name": "defi_data",
                            "description": "Top DeFi protocols, TVL breakdown, and yield pools from DeFiLlama.",
                            "input_schema": {
                                "type": "object",
                                "properties": {
                                    "identifier": {"type": "string", "format": "string"},
                                },
                                "required": [],
                            },
                            "output_schema": {
                                "type": "object",
                                "properties": {
                                    "top_protocols": {"type": "array"},
                                    "top_yields": {"type": "array"},
                                    "chain_tvl": {"type": "array"},
                                },
                            },
                            "enrichment_suggestions": [],
                            "price_usdc": 0.0001,
                            "timeout_ms": 20000,
                        },
                        {
                            "name": "defi_analysis",
                            "description": "Analytic layer over DeFiLlama: APY trends, TVL momentum.",
                            "input_schema": {
                                "type": "object",
                                "properties": {
                                    "identifier": {"type": "string", "format": "string"},
                                },
                                "required": [],
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
                print(f"[DeFi Agent] Registered in NEXUS marketplace!")
                print(f"[DeFi Agent] Agent ID: {data.get('agent_id')}")
                passport = data.get('passport_id') or 'local-only (on-chain registration skipped or already exists)'
                print(f"[DeFi Agent] Passport: {str(passport)[:40]}...")
            else:
                print(f"[DeFi Agent] Registration failed: {response.text}")
        except Exception as e:
            print(f"[DeFi Agent] Could not register (NEXUS not running?): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 50)
    print("  NEXUS Example Agent: DeFi Metrics")
    print("  Powered by DeFiLlama (free, unlimited)")
    print("=" * 50)
    await register_with_nexus()
    yield


app = FastAPI(title="DeFi Metrics Agent", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "DeFiLlama-MetricsAgent-v1"}


@app.post("/invoke")
async def invoke(request: dict):
    """
    Callback endpoint that NEXUS marketplace calls.
    Fetches real DeFi data from DeFiLlama.
    Accepts either the new typed shape ({identifier: ...}) or legacy ({query: ...}).
    """
    query_type = request.get("type", "defi_data")
    raw = (request.get("identifier") or request.get("query") or "").strip()
    # Protocol / chain / symbol is whatever the user said — uppercase for the
    # chain_map lookup but preserve original for protocol-slug matching.
    token = raw.upper()

    async with httpx.AsyncClient(timeout=15.0) as client:
        result = {
            "agent": "DeFiLlama-MetricsAgent-v1",
            "query": token or "all",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {},
        }

        # Fire all three DeFiLlama requests in parallel — they're independent.
        # This cuts agent latency from ~24s (3 x 8s serial) to ~8s (parallel).
        async def _get(url: str):
            try:
                return await client.get(url)
            except Exception as e:
                return e

        protocols_resp, yields_resp, chains_resp = await asyncio.gather(
            _get("https://api.llama.fi/protocols"),
            _get("https://yields.llama.fi/pools"),
            _get("https://api.llama.fi/v2/chains"),
        )

        # Fetch top protocols by TVL
        try:
            resp = protocols_resp
            if isinstance(resp, Exception):
                raise resp
            if resp.status_code == 200:
                protocols = resp.json()

                # Filter by chain/token if specified
                if token:
                    # Find protocols related to the token's chain
                    chain_map = {
                        "ETH": "Ethereum", "SOL": "Solana", "BNB": "BSC",
                        "AVAX": "Avalanche", "MATIC": "Polygon", "ARB": "Arbitrum",
                        "OP": "Optimism", "KITE": "Kite",
                    }
                    chain = chain_map.get(token, token)
                    relevant = [
                        p for p in protocols
                        if chain.lower() in str(p.get("chains", [])).lower()
                        or token.lower() in p.get("symbol", "").lower()
                    ][:10]
                else:
                    relevant = sorted(protocols, key=lambda p: p.get("tvl", 0), reverse=True)[:10]

                result["data"]["top_protocols"] = [
                    {
                        "name": p.get("name"),
                        "symbol": p.get("symbol"),
                        "tvl": round(p.get("tvl", 0), 2),
                        "tvl_change_1d": round(p.get("change_1d", 0), 2) if p.get("change_1d") else 0,
                        "tvl_change_7d": round(p.get("change_7d", 0), 2) if p.get("change_7d") else 0,
                        "chains": p.get("chains", [])[:5],
                        "category": p.get("category"),
                    }
                    for p in relevant
                ]
                result["data"]["total_protocols"] = len(protocols)
        except Exception as e:
            result["data"]["protocols_error"] = str(e)

        # Fetch yield/APY data
        try:
            resp = yields_resp
            if isinstance(resp, Exception):
                raise resp
            if resp.status_code == 200:
                pools = resp.json().get("data", [])

                # Filter for top yields (stable pools only for safety)
                stable_pools = [
                    p for p in pools
                    if p.get("stablecoin", False)
                    and p.get("tvlUsd", 0) > 1000000  # >$1M TVL
                    and p.get("apy", 0) > 0
                ]
                top_yields = sorted(stable_pools, key=lambda p: p.get("apy", 0), reverse=True)[:10]

                result["data"]["top_yields"] = [
                    {
                        "pool": p.get("pool"),
                        "project": p.get("project"),
                        "chain": p.get("chain"),
                        "symbol": p.get("symbol"),
                        "apy": round(p.get("apy", 0), 2),
                        "tvl_usd": round(p.get("tvlUsd", 0), 2),
                        "stable": p.get("stablecoin", False),
                    }
                    for p in top_yields
                ]
        except Exception as e:
            result["data"]["yields_error"] = str(e)

        # Fetch chain TVL breakdown
        try:
            resp = chains_resp
            if isinstance(resp, Exception):
                raise resp
            if resp.status_code == 200:
                chains = resp.json()
                top_chains = sorted(chains, key=lambda c: c.get("tvl", 0), reverse=True)[:10]
                result["data"]["chain_tvl"] = [
                    {
                        "name": c.get("name"),
                        "tvl": round(c.get("tvl", 0), 2),
                        "token_symbol": c.get("tokenSymbol"),
                    }
                    for c in top_chains
                ]
        except Exception as e:
            result["data"]["chains_error"] = str(e)

        result["data"]["source"] = "defillama"
        result["data"]["data_source_real"] = True

        return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
