"""
NEXUS External Agent: GoPlus Security

Standalone agent that registers with NEXUS marketplace and provides
token security analysis: rug pull detection, honeypot detection,
contract verification, tax checks, owner permission analysis.

Data source: GoPlus Security API (https://api.gopluslabs.io)
- Free, no API key required
- Covers Ethereum, BSC, Polygon, Arbitrum, Base, Solana, etc.
- Returns risk indicators that help identify scams

This is a UNIQUE capability -- none of the NEXUS built-in agents
can assess token security. Shows the marketplace extending NEXUS
with entirely new types of intelligence.

Run: uvicorn app:app --port 5003
"""

import os
import httpx
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI

NEXUS_URL = os.getenv("NEXUS_URL", "http://localhost:8000")
AGENT_PORT = int(os.getenv("AGENT_PORT", "5003"))
PUBLIC_URL = os.getenv("PUBLIC_URL", f"http://localhost:{AGENT_PORT}")

GOPLUS_BASE = "https://api.gopluslabs.io/api/v1"

# Chain name -> GoPlus chain_id
CHAIN_MAP = {
    "ETHEREUM": "1", "ETH": "1",
    "BSC": "56", "BNB": "56",
    "POLYGON": "137", "MATIC": "137",
    "ARBITRUM": "42161", "ARB": "42161",
    "OPTIMISM": "10", "OP": "10",
    "BASE": "8453",
    "AVALANCHE": "43114", "AVAX": "43114",
    "FANTOM": "250", "FTM": "250",
    "SOLANA": "solana", "SOL": "solana",
}


async def register_with_nexus():
    """Register this agent in the NEXUS marketplace on startup."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{NEXUS_URL}/api/marketplace/register",
                json={
                    "name": "GoPlus-Security-Agent-v1",
                    "description": (
                        "Autonomous rug pull and honeypot detection for any ERC-20 token. "
                        "Checks contract verification, buy/sell taxes, owner privileges, "
                        "blacklist functions, mint permissions, and LP lock status across "
                        "Ethereum, BSC, Polygon, Arbitrum, Base, Solana, and more. "
                        "Powered by GoPlus Security (free, no API key)."
                    ),
                    "capabilities": ["token_security", "rug_detection"],
                    "price_per_query": 0.0002,
                    "callback_url": f"{PUBLIC_URL}/invoke",
                    "owner_address": "0xSecurity_Agent_Owner",
                    "keywords": [
                        "rug", "rugpull", "rug pull", "honeypot", "scam",
                        "safe", "safety", "is it safe", "risk", "legit",
                        "token security", "audit token", "verify contract",
                    ],
                    "example_queries": [
                        "Is token 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 safe?",
                        "Check for honeypot on 0xdAC17F958D2ee523a2206206994597C13D831ec7",
                        "Rug pull risk for 0xB8c77482e45F1F44dE1745F52C74426C631bDD52",
                    ],
                    # Rich, schema-typed capability declarations. The orchestrator
                    # validates input against these before paying and routing.
                    "capability_specs": [
                        {
                            "name": "token_security",
                            "description": "Full GoPlus security analysis for an EVM contract (risk score, honeypot, taxes, LP, ownership).",
                            "input_schema": {
                                "type": "object",
                                "properties": {
                                    "identifier": {"type": "string", "format": "evm_address"},
                                    "chain": {
                                        "type": "string",
                                        "enum": list(CHAIN_MAP.keys()),
                                    },
                                },
                                "required": ["identifier"],
                            },
                            "output_schema": {
                                "type": "object",
                                "properties": {
                                    "risk_level": {"type": "string"},
                                    "risk_score": {"type": "number"},
                                    "findings": {"type": "array"},
                                },
                            },
                            "enrichment_suggestions": [],
                            "price_usdc": 0.0002,
                            "timeout_ms": 20000,
                        },
                        {
                            "name": "rug_detection",
                            "description": "Rug-pull and honeypot red flags for an EVM contract address.",
                            "input_schema": {
                                "type": "object",
                                "properties": {
                                    "identifier": {"type": "string", "format": "evm_address"},
                                    "chain": {
                                        "type": "string",
                                        "enum": list(CHAIN_MAP.keys()),
                                    },
                                },
                                "required": ["identifier"],
                            },
                            "output_schema": {
                                "type": "object",
                                "properties": {
                                    "risk_level": {"type": "string"},
                                    "is_honeypot": {"type": "boolean"},
                                    "warnings": {"type": "array"},
                                },
                            },
                            "enrichment_suggestions": [],
                            "price_usdc": 0.0002,
                            "timeout_ms": 20000,
                        },
                    ],
                },
            )
            if response.status_code == 200:
                data = response.json()
                print(f"[Security Agent] Registered in NEXUS marketplace!")
                print(f"[Security Agent] Agent ID: {data.get('agent_id')}")
                passport = data.get('passport_id') or 'local-only (on-chain registration skipped or already exists)'
                print(f"[Security Agent] Passport: {str(passport)[:40]}...")
            else:
                print(f"[Security Agent] Registration failed: {response.text}")
        except Exception as e:
            print(f"[Security Agent] Could not register (NEXUS not running?): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 50)
    print("  NEXUS External Agent: GoPlus Security")
    print("  Rug pull + honeypot detection")
    print("  Data source: GoPlus (free, no API key)")
    print("=" * 50)
    await register_with_nexus()
    yield


app = FastAPI(title="GoPlus Security Agent", lifespan=lifespan)


def _parse_security_data(token_data: dict) -> dict:
    """
    Parse GoPlus raw response into structured risk assessment.
    GoPlus returns string "0"/"1" for boolean flags - normalize to bool.
    """
    def as_bool(val, default=False):
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        return str(val).strip() == "1"

    def as_pct(val, default=0.0):
        try:
            return round(float(val) * 100, 2) if val else default
        except (ValueError, TypeError):
            return default

    is_honeypot = as_bool(token_data.get("is_honeypot"))
    is_open_source = as_bool(token_data.get("is_open_source"))
    is_proxy = as_bool(token_data.get("is_proxy"))
    is_mintable = as_bool(token_data.get("is_mintable"))
    can_take_back_ownership = as_bool(token_data.get("can_take_back_ownership"))
    transfer_pausable = as_bool(token_data.get("transfer_pausable"))
    is_blacklisted = as_bool(token_data.get("is_blacklisted"))
    has_blacklist = as_bool(token_data.get("is_in_dex")) and as_bool(
        token_data.get("transfer_pausable")
    )
    owner_change_balance = as_bool(token_data.get("owner_change_balance"))
    slippage_modifiable = as_bool(token_data.get("slippage_modifiable"))

    buy_tax = as_pct(token_data.get("buy_tax"))
    sell_tax = as_pct(token_data.get("sell_tax"))

    # Owner may be "0x0000...0000" or "0x000...dEaD" (renounced) or a real address
    owner_address = str(token_data.get("owner_address") or "").lower()
    owner_renounced = (
        not owner_address
        or owner_address == "0x0000000000000000000000000000000000000000"
        or owner_address.endswith("dead")
    )

    # LP lock check - GoPlus provides lp_holders list
    lp_holders = token_data.get("lp_holders") or []
    lp_locked_pct = 0.0
    for lp in lp_holders:
        if as_bool(lp.get("is_locked")):
            try:
                lp_locked_pct += float(lp.get("percent") or 0) * 100
            except (ValueError, TypeError):
                pass
    lp_locked_pct = round(lp_locked_pct, 2)

    # Compute risk score (0-100, higher = safer)
    risk_score = 100
    flags = []

    if is_honeypot:
        risk_score -= 80
        flags.append("CRITICAL: Contract is a honeypot (cannot sell)")
    if not is_open_source:
        risk_score -= 20
        flags.append("Contract source code NOT verified on-chain")
    if is_proxy:
        risk_score -= 10
        flags.append("Proxy contract - logic can be upgraded by admin")
    if is_mintable:
        risk_score -= 15
        flags.append("Owner can mint new tokens (supply inflation risk)")
    if can_take_back_ownership:
        risk_score -= 25
        flags.append("Ownership can be reclaimed after renouncement")
    if transfer_pausable:
        risk_score -= 15
        flags.append("Transfers can be paused by owner")
    if owner_change_balance:
        risk_score -= 30
        flags.append("Owner can modify any wallet balance")
    if slippage_modifiable:
        risk_score -= 10
        flags.append("Owner can modify trading taxes")
    if buy_tax > 10:
        risk_score -= 15
        flags.append(f"High buy tax: {buy_tax}%")
    if sell_tax > 10:
        risk_score -= 20
        flags.append(f"High sell tax: {sell_tax}%")
    if sell_tax > 50:
        risk_score -= 30
        flags.append(f"CRITICAL: Extreme sell tax ({sell_tax}%) - likely honeypot")
    if not owner_renounced and not is_open_source:
        risk_score -= 10
        flags.append("Active owner with unverified contract")
    if lp_locked_pct < 50 and lp_holders:
        risk_score -= 15
        flags.append(f"Only {lp_locked_pct}% of LP is locked (rug pull risk)")

    risk_score = max(0, min(100, risk_score))

    # Classify risk level
    if risk_score >= 80:
        risk_level = "LOW"
        verdict = "Low risk - contract appears safe"
    elif risk_score >= 60:
        risk_level = "MEDIUM"
        verdict = "Medium risk - review flags before interacting"
    elif risk_score >= 30:
        risk_level = "HIGH"
        verdict = "High risk - multiple concerning indicators"
    else:
        risk_level = "CRITICAL"
        verdict = "CRITICAL risk - likely scam, do not interact"

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "verdict": verdict,
        "flags": {
            "is_honeypot": is_honeypot,
            "is_open_source": is_open_source,
            "is_proxy": is_proxy,
            "is_mintable": is_mintable,
            "can_take_back_ownership": can_take_back_ownership,
            "transfer_pausable": transfer_pausable,
            "owner_change_balance": owner_change_balance,
            "slippage_modifiable": slippage_modifiable,
            "owner_renounced": owner_renounced,
            "lp_locked_pct": lp_locked_pct,
            "buy_tax_pct": buy_tax,
            "sell_tax_pct": sell_tax,
        },
        "warnings": flags,
        "token_name": token_data.get("token_name"),
        "token_symbol": token_data.get("token_symbol"),
        "total_supply": token_data.get("total_supply"),
        "holder_count": token_data.get("holder_count"),
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agent": "GoPlus-Security-Agent-v1",
        "capabilities": ["token_security", "rug_detection"],
    }


import re

_EVM_ADDR_RE = re.compile(r"0x[0-9a-fA-F]{40}")


def _extract_address(request: dict) -> str:
    """Accept `identifier` (new typed path), `query` (legacy), or extract from
    natural-language text. Case-insensitive on the 0x prefix; preserves EIP-55
    checksum if the caller sent one. GoPlus API is queried with lowercase."""
    for key in ("identifier", "query", "address", "contract"):
        val = request.get(key)
        if isinstance(val, str) and val.strip():
            m = _EVM_ADDR_RE.search(val)
            if m:
                return m.group(0)
            # Not a match — try next field.
    return ""


@app.post("/invoke")
async def invoke(request: dict):
    """
    Callback invoked by NEXUS. Accepts either the new schema-typed shape
    `{identifier: "0x...", chain: "ETH"}` or the legacy `{query: "..."}` shape.
    """
    address = _extract_address(request)
    chain_name = str(request.get("chain") or "ETH").upper()
    chain_id = CHAIN_MAP.get(chain_name, "1")

    if not address:
        return {
            "agent": "GoPlus-Security-Agent-v1",
            "timestamp": datetime.utcnow().isoformat(),
            "error": "A 42-char EVM contract address is required (0x...). Case-insensitive.",
            "hint": "Pass `identifier` as a 0x-prefixed 40-hex contract address. Symbols are not supported.",
        }

    address_lower = address.lower()

    result = {
        "agent": "GoPlus-Security-Agent-v1",
        "query": address,
        "chain": chain_name,
        "timestamp": datetime.utcnow().isoformat(),
        "data": {},
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            url = f"{GOPLUS_BASE}/token_security/{chain_id}?contract_addresses={address_lower}"
            resp = await client.get(url)

            if resp.status_code != 200:
                result["data"]["error"] = f"GoPlus returned HTTP {resp.status_code}"
                return result

            payload = resp.json()
            if payload.get("code") != 1:
                result["data"]["error"] = payload.get("message", "GoPlus query failed")
                return result

            token_results = payload.get("result") or {}
            token_data = token_results.get(address_lower)

            if not token_data:
                result["data"] = {
                    "message": f"No security data for {address} on chain {chain_name}",
                    "source": "goplus",
                    "data_source_real": True,
                }
                return result

            assessment = _parse_security_data(token_data)
            assessment["source"] = "goplus"
            assessment["data_source_real"] = True
            assessment["chain_id"] = chain_id
            result["data"] = assessment

        except Exception as e:
            result["data"]["error"] = f"GoPlus fetch failed: {str(e)}"
            result["data"]["data_source_real"] = False

    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
