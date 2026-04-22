# NEXUS Architecture

## System Overview

NEXUS is a fully autonomous agent economy running on Kite Chain. Five AI agents operate as independent businesses -- discovering each other, negotiating via x402 micropayments, and building on-chain reputation.

## Agent Interaction Flow

```
User Query
    |
    v
[1] ReportAgent classifies query (LLM-powered)
    |
[2] DiscoveryEngine finds best agents by capability + reputation
    |
[3] MandateManager creates ECDSA-signed spending authorization
    |
[4] For each agent needed:
    |   CircuitBreaker validates payment (7 checks)
    |   -> PaymentRouter executes on-chain (Kite testnet)
    |   -> Agent performs work
    |   -> Result collected
    |
[5] AuditAgent verifies all outputs (5 quality checks)
    |
[6] ReputationTracker updates scores on-chain
    |
[7] AuditTrailBuilder records hash on-chain
    |
[8] Report compiled with LLM summary
    |
    v
Dashboard (WebSocket real-time)
```

## x402 Payment Flow

Each agent service is x402-gated per Kite's specification:

```
Agent A                    Agent B Service              Pieverse Facilitator
   |                            |                              |
   |-- POST /x402/data-agent ->|                              |
   |<-- HTTP 402 + accepts ----|                              |
   |                            |                              |
   |-- get_payer_addr --------->|                              |
   |-- approve_payment -------->| (signs with treasury key)    |
   |                            |                              |
   |-- POST + X-PAYMENT ------>|                              |
   |                            |-- verify ------------------>|
   |                            |-- settle ------------------>|
   |                            |<-- on-chain tx -------------|
   |<-- service response -------|                              |
```

**402 Response Format** (matches Kite weather API spec):
- `scheme`: "gokite-aa"
- `network`: "kite-testnet"
- `asset`: Test USDT (`0x0fF5393387ad2f9f691FD6Fd28e07E3969e27e63`)
- `outputSchema`: describes input/output for agent discoverability
- `x402Version`: 1

## Verified Intent Pipeline

### Mandate Creation
```
Query -> sha256(query) = context_hash
      -> sum(agent_prices) * 3.0 = total_budget
      -> max(agent_prices) * 2 = max_per_tx
      -> ECDSA sign(mandate_id, context_hash, budget, max_per_tx, expires)
      -> Mandate stored with 5-minute TTL
```

### Circuit Breaker (7 Checks)
Before every payment:
1. Mandate exists and is ACTIVE
2. cumulative_spent + amount <= total_budget
3. amount <= max_per_tx
4. to_agent in allowed_agents list
5. Mandate not expired (TTL check)
6. Agent reputation >= min_reputation (default 20)
7. On-chain GovernanceRules.checkAllowed() passes

### Audit Trail
```
report_hash = sha256(report_json)
traceability_hash = sha256(query + mandate + payments + report_hash)
tx = send_data_tx("NEXUS_AUDIT:{mandate_id}:{traceability_hash}")
-> Verifiable at testnet.kitescan.ai/tx/{tx_hash}
```

## Smart Contract Architecture

### AgentRegistry (Open Marketplace)
- `registerAgent(passportId, name, description, capabilities, price)` -- open to any wallet
- `getAgent(passportId)` -- query agent details
- Agents start with reputation 50/100

### ReputationTracker
- `recordSuccess(passportId, qualityScore)` -- +2 for score >= 90, +1 for >= 70
- `recordFailure(passportId)` -- -5 points
- Score clamped to [0, 100]

### PaymentRouter
- `payForService(from, to, amount, purpose)` -- records inter-agent payment
- `payForServiceWithMandate(from, to, amount, purpose, mandateId)` -- with audit trail
- Tracks totalEarned and totalSpent per agent

### GovernanceRules
- Global rules: max per-tx ($0.001), max per-day ($0.01), min reputation (20)
- Per-agent overrides possible
- Daily spending auto-resets at UTC midnight

## Data Source Fallback Chains

### Prices
CoinGecko (primary) -> CoinCap (backup) -> CryptoCompare (fallback)

### Twitter/Social
Rettiwt microservice (real tweets) -> Nitter RSS (fallback) -> CryptoPanic (last resort)

### News
Google News RSS + CryptoPanic + NewsAPI (all in parallel, deduplicated)

### Whale Activity
Helius API (Solana/Kite) -> Whale Alert -> Kite BlockScout -> DeFiLlama

## LLM Routing

```
Groq (Llama 3.3 70B, 30 req/min free)
  |-- fails -->
Gemini (2.0 Flash, 15 req/min free)
  |-- fails -->
Ollama (local, unlimited, no key)
  |-- fails -->
Structured error response (never crashes)
```

## WebSocket Event System

All state changes broadcast to the frontend dashboard in real-time:

| Event | When |
|-------|------|
| `agent_discovery` | Agent found for capability |
| `mandate_created` | Spending authorization signed |
| `circuit_breaker_approved` | Payment validated |
| `circuit_breaker_blocked` | Payment blocked (budget/reputation/etc) |
| `payment_sent` | x402 payment executed |
| `work_started` / `work_completed` | Agent busy/done |
| `audit_completed` | Quality score determined |
| `reputation_update` | Score changed on-chain |
| `audit_trail_recorded` | Hash recorded on-chain |
| `report_completed` | Final report ready |

## Open Marketplace

External agents can register and participate:

```bash
POST /api/marketplace/register
{
  "name": "DeFiLlama-MetricsAgent-v1",
  "capabilities": ["defi_data", "defi_analysis"],
  "price_per_query": 0.0001,
  "callback_url": "https://my-agent.example.com/invoke"
}
```

ReportAgent's DiscoveryEngine scores agents by: reputation (40%) + price (30%) + success rate (30%) and selects the best for each capability needed.

### Bundled External Agents (in `example-agents/`)

NEXUS ships with 3 reference external agents that each run as standalone FastAPI services and self-register with the marketplace on startup. They demonstrate the full registration -> discovery -> invocation -> payment flow with real external services.

| Agent | Port | Capabilities | Data Source | API Key? |
|-------|------|-------------|------------|----------|
| `defi-agent` | 5001 | `defi_data`, `defi_analysis` | DeFiLlama | None |
| `dexscreener-agent` | 5002 | `dex_data`, `liquidity_analysis` | DEXScreener | None |
| `security-agent` | 5003 | `token_security`, `rug_detection` | GoPlus Security | None |

**All three APIs require ZERO signup -- judges can clone the repo and run everything immediately.**

### Query -> Agent Routing Examples

The DiscoveryEngine routes queries based on classification:

| User Query | Classified As | Agents Hired |
|-----------|---------------|-------------|
| "Analyze KITE sentiment" | `token_analysis` | DataAgent + AnalystAgent + AuditAgent (built-in) |
| "ETH DeFi yields" | `defi_metrics` | **DeFi Agent** (external, from marketplace) |
| "KITE liquidity across DEXs" | `dex_analysis` | **DEXScreener Agent** (external) |
| "Is token 0xabc... safe?" | `security_check` | **Security Agent** (external) |
| "NFT floor prices" | `nft_analysis` | **None available** -> `no_agents_available` with hint |

The last row is the key proof: the marketplace knows what it CAN'T do and invites developers to register agents filling those gaps.
