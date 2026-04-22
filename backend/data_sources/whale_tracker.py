"""
NEXUS - Whale Transaction Tracker (REAL DATA)
Detects large cryptocurrency transactions using real blockchain APIs.

Sources (priority order):
1. Helius API - Real Solana/Kite on-chain transaction data (free tier: 1M credits/month)
2. Whale Alert API - Cross-chain whale tracking
3. Etherscan/BlockScout - EVM chain large tx detection
4. DeFiLlama - Protocol TVL flows

NEVER generates fake transactions. Returns empty with warning if all sources fail.
"""

import httpx
from datetime import datetime
from typing import Optional
from backend.config import settings


# Known whale/exchange addresses for Kite ecosystem
KNOWN_WHALE_LABELS = {
    "0x0000000000000000000000000000000000000000": "Burn Address",
    "0xdead000000000000000000000000000000000000": "Dead Address",
}

# Token contract addresses for tracking
TOKEN_CONTRACTS = {
    "KITE": "0x904567252D8F48555b7447c67dCA23F0372E16be",
    "ETH": None,
    "BTC": None,
    "SOL": None,
}

# Whale threshold in USD
WHALE_THRESHOLD_USD = 10000


class WhaleTracker:
    """Tracks large crypto transactions using REAL blockchain data"""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=20.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NexusBot/1.0)"},
        )
        self.helius_key = getattr(settings, "helius_api_key", None) or ""
        self.last_source_status: dict = {}

    async def get_whale_activity(self, token: str) -> dict:
        """Get real whale (large) transactions for a token."""
        whale_txs: list[dict] = []
        status = {
            "source_used": None,
            "helius": {"ok": False, "tried": bool(self.helius_key), "count": 0},
            "whale_alert": {"ok": False, "tried": True, "count": 0},
            "kite_blockscout": {"ok": False, "tried": True, "count": 0},
        }

        # Source 1: Helius API (Solana/Kite real on-chain data)
        if self.helius_key:
            helius_txs = await self._fetch_helius_large_transfers(token)
            if helius_txs:
                whale_txs.extend(helius_txs)
                status["helius"]["ok"] = True
                status["helius"]["count"] = len(helius_txs)
                if status["source_used"] is None:
                    status["source_used"] = "helius"
                print(f"[Whale] Got {len(helius_txs)} REAL whale txs from Helius")

        # Source 2: Whale Alert public feed
        whale_alert_txs = await self._fetch_whale_alert(token)
        if whale_alert_txs:
            whale_txs.extend(whale_alert_txs)
            status["whale_alert"]["ok"] = True
            status["whale_alert"]["count"] = len(whale_alert_txs)
            if status["source_used"] is None:
                status["source_used"] = "whale_alert"
            print(f"[Whale] Got {len(whale_alert_txs)} whale alerts")

        # Source 3: Kite testnet large transactions via BlockScout
        kite_txs = await self._fetch_kite_large_txs(token)
        if kite_txs:
            whale_txs.extend(kite_txs)
            status["kite_blockscout"]["ok"] = True
            status["kite_blockscout"]["count"] = len(kite_txs)
            if status["source_used"] is None:
                status["source_used"] = "kite_blockscout"
            print(f"[Whale] Got {len(kite_txs)} large Kite txs from BlockScout")

        # Source 4: DeFiLlama protocol data
        protocol_data = await self._fetch_defi_llama(token)

        if not whale_txs:
            status["source_used"] = "unavailable"
            print(f"[Whale] WARNING: No real whale data found for {token}. All sources returned empty.")

        self.last_source_status = status

        return {
            "token": token.upper(),
            "whale_transactions": whale_txs,
            "net_flow": self._calculate_net_flow(whale_txs),
            "protocol_data": protocol_data,
            "large_buys": len([tx for tx in whale_txs if tx["type"] == "buy"]),
            "large_sells": len([tx for tx in whale_txs if tx["type"] == "sell"]),
            "total_volume_usd": sum(tx.get("amount_usd", 0) for tx in whale_txs),
            "analysis": self._interpret_whale_activity(whale_txs),
            "timestamp": datetime.utcnow().isoformat(),
            "sources": list(set(tx.get("source", "unknown") for tx in whale_txs)),
            "data_source_real": len(whale_txs) > 0,
        }

    async def _fetch_helius_large_transfers(self, token: str) -> list[dict]:
        """
        Fetch recent large transfers from Helius enhanced transaction API.
        Uses the free tier (1M credits/month, 10 req/sec).
        """
        if not self.helius_key:
            return []

        try:
            # Use Helius enhanced transactions API to get recent large transfers
            url = f"https://api.helius.xyz/v0/addresses/tokens/largest?api-key={self.helius_key}"

            # Alternatively, use the parsed transaction history for a known token
            # For Kite ecosystem, we check recent large transactions on the network
            search_url = f"https://api.helius.xyz/v0/token-metadata?api-key={self.helius_key}"

            # Check for large SOL transfers as proxy for whale activity
            rpc_url = f"https://mainnet.helius-rpc.com/?api-key={self.helius_key}"
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [
                    "So11111111111111111111111111111111111111112",  # SOL token program
                    {"limit": 20}
                ]
            }

            response = await self.client.post(rpc_url, json=payload, timeout=10.0)
            if response.status_code != 200:
                return []

            data = response.json()
            signatures = data.get("result", [])

            whale_txs = []
            # Get enhanced transaction details for recent signatures
            for sig in signatures[:10]:
                try:
                    tx_url = f"https://api.helius.xyz/v0/transactions/?api-key={self.helius_key}"
                    tx_resp = await self.client.post(
                        tx_url,
                        json={"transactions": [sig["signature"]]},
                        timeout=10.0,
                    )
                    if tx_resp.status_code == 200:
                        tx_data = tx_resp.json()
                        for tx in tx_data:
                            # Check for large native transfers
                            for transfer in tx.get("nativeTransfers", []):
                                amount_sol = transfer.get("amount", 0) / 1e9
                                if amount_sol >= 100:  # 100+ SOL = whale
                                    whale_txs.append({
                                        "type": "buy" if transfer.get("toUserAccount") else "sell",
                                        "amount_usd": round(amount_sol * 150, 2),  # Approximate SOL price
                                        "amount_tokens": round(amount_sol, 2),
                                        "address": transfer.get("fromUserAccount", "unknown")[:16] + "...",
                                        "to_address": transfer.get("toUserAccount", "unknown")[:16] + "...",
                                        "timestamp": datetime.utcnow().isoformat(),
                                        "tx_hash": sig["signature"][:20] + "...",
                                        "source": "helius",
                                        "significance": "high" if amount_sol > 1000 else "medium",
                                    })

                            # Check for large token transfers
                            for transfer in tx.get("tokenTransfers", []):
                                amount = transfer.get("tokenAmount", 0)
                                if amount >= WHALE_THRESHOLD_USD:
                                    whale_txs.append({
                                        "type": "transfer",
                                        "amount_usd": round(amount, 2),
                                        "amount_tokens": amount,
                                        "address": transfer.get("fromUserAccount", "unknown")[:16] + "...",
                                        "to_address": transfer.get("toUserAccount", "unknown")[:16] + "...",
                                        "timestamp": datetime.utcnow().isoformat(),
                                        "token_mint": transfer.get("mint", "unknown")[:16] + "...",
                                        "tx_hash": sig["signature"][:20] + "...",
                                        "source": "helius",
                                        "significance": "high",
                                    })
                except Exception:
                    continue

            return whale_txs

        except Exception as e:
            print(f"[Whale] Helius API error: {e}")
            return []

    async def _fetch_whale_alert(self, token: str) -> list[dict]:
        """Fetch from Whale Alert public RSS/API"""
        try:
            # Whale Alert has a public feed
            url = "https://api.whale-alert.io/feed"
            response = await self.client.get(url, timeout=10.0)
            if response.status_code == 200 and "application/json" in response.headers.get("content-type", ""):
                data = response.json()
                txs = []
                for tx in data.get("transactions", []):
                    if tx.get("symbol", "").upper() == token.upper() or token.upper() in ["BTC", "ETH", "SOL"]:
                        amount_usd = tx.get("amount_usd", 0)
                        if amount_usd >= WHALE_THRESHOLD_USD:
                            txs.append({
                                "type": "buy" if tx.get("to", {}).get("owner_type") == "exchange" else "sell",
                                "amount_usd": amount_usd,
                                "amount_tokens": tx.get("amount", 0),
                                "address": tx.get("from", {}).get("address", "unknown")[:16] + "...",
                                "timestamp": datetime.fromtimestamp(tx.get("timestamp", 0)).isoformat(),
                                "source": "whale_alert",
                                "significance": "high" if amount_usd > 1000000 else "medium",
                            })
                return txs
        except Exception as e:
            print(f"[Whale] Whale Alert error: {e}")

        return []

    async def _fetch_kite_large_txs(self, token: str) -> list[dict]:
        """Fetch large transactions from Kite testnet BlockScout explorer"""
        try:
            url = "https://testnet.kitescan.ai/api/v2/transactions"
            response = await self.client.get(
                url,
                params={"type": "token_transfer", "filter": "to|from"},
                timeout=10.0,
            )
            if response.status_code == 200:
                data = response.json()
                txs = []
                for item in data.get("items", [])[:20]:
                    value = int(item.get("value", "0")) / 1e18
                    if value >= 10:  # 10+ KITE = notable on testnet
                        txs.append({
                            "type": "transfer",
                            "amount_usd": round(value * 0.4, 2),
                            "amount_tokens": round(value, 2),
                            "address": item.get("from", {}).get("hash", "unknown")[:16] + "...",
                            "to_address": item.get("to", {}).get("hash", "unknown")[:16] + "...",
                            "timestamp": item.get("timestamp", datetime.utcnow().isoformat()),
                            "tx_hash": item.get("hash", "")[:20] + "...",
                            "source": "kite_explorer",
                            "significance": "medium",
                        })
                return txs
        except Exception as e:
            print(f"[Whale] Kite explorer error: {e}")

        return []

    async def _fetch_defi_llama(self, token: str) -> dict:
        """Fetch DeFi protocol data from DeFiLlama (free, unlimited)"""
        try:
            url = f"https://api.llama.fi/protocol/{token.lower()}"
            response = await self.client.get(url, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                return {
                    "tvl": data.get("tvl", 0),
                    "chain_tvls": data.get("chainTvls", {}),
                    "symbol": data.get("symbol", token.upper()),
                }
        except Exception:
            pass
        return {}

    def _calculate_net_flow(self, whale_txs: list[dict]) -> str:
        """Calculate whether whales are net buying or selling"""
        buy_volume = sum(tx.get("amount_usd", 0) for tx in whale_txs if tx.get("type") == "buy")
        sell_volume = sum(tx.get("amount_usd", 0) for tx in whale_txs if tx.get("type") == "sell")

        if not whale_txs:
            return "no_data"
        if buy_volume > sell_volume * 1.2:
            return "accumulation"
        elif sell_volume > buy_volume * 1.2:
            return "distribution"
        return "neutral"

    def _interpret_whale_activity(self, whale_txs: list[dict]) -> str:
        """Generate human-readable interpretation of whale activity"""
        if not whale_txs:
            return "No whale activity detected from monitored sources in the recent period."

        net_flow = self._calculate_net_flow(whale_txs)
        total_volume = sum(tx.get("amount_usd", 0) for tx in whale_txs)
        buy_count = len([tx for tx in whale_txs if tx.get("type") == "buy"])
        sell_count = len([tx for tx in whale_txs if tx.get("type") == "sell"])
        transfer_count = len([tx for tx in whale_txs if tx.get("type") == "transfer"])
        sources = list(set(tx.get("source", "unknown") for tx in whale_txs))

        base = f"Detected {len(whale_txs)} whale transactions (sources: {', '.join(sources)}). "

        if net_flow == "accumulation":
            return base + (
                f"{buy_count} large buys vs {sell_count} sells. "
                f"Total volume: ${total_volume:,.0f}. Whale accumulation indicates institutional confidence."
            )
        elif net_flow == "distribution":
            return base + (
                f"{sell_count} large sells vs {buy_count} buys. "
                f"Total volume: ${total_volume:,.0f}. Large holders may be taking profits."
            )
        else:
            return base + (
                f"{buy_count} buys, {sell_count} sells, {transfer_count} transfers. "
                f"Total volume: ${total_volume:,.0f}. No clear directional bias from whales."
            )

    async def close(self):
        await self.client.aclose()
