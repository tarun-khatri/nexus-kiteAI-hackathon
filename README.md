# NEXUS - The Living Agent Economy on Kite Chain

> **Kite AI Global Hackathon 2026 | Track: Novel**
>
> A self-sustaining micro-economy where **5 specialized AI agents** operate as independent businesses on Kite Chain. They autonomously discover each other, negotiate, execute work, pay via x402 micropayments, and build on-chain reputation -- all without human intervention.

## Why NEXUS

Instead of building one AI agent that does one thing, NEXUS builds **the entire agentic economy** -- demonstrating what Kite AI was built for. Every agent has a cryptographic identity, earns real micropayments, and builds verifiable reputation on-chain.

## Deployed on Kite Testnet

All smart contracts are live and verifiable:

| Contract | Address | Explorer |
|----------|---------|----------|
| AgentRegistry | `0xBf23C1A79EfEf28C170cC8895679C4b4E7A97a74` | [View](https://testnet.kitescan.ai/address/0xBf23C1A79EfEf28C170cC8895679C4b4E7A97a74) |
| ReputationTracker | `0xeE38c91e1dd42A0fc6980Ba8ECc769DFfC5044a9` | [View](https://testnet.kitescan.ai/address/0xeE38c91e1dd42A0fc6980Ba8ECc769DFfC5044a9) |
| PaymentRouter | `0xd76ea536704252DeD9602eCd549F776aD302c73C` | [View](https://testnet.kitescan.ai/address/0xd76ea536704252DeD9602eCd549F776aD302c73C) |
| GovernanceRules | `0xc7640Bf4fC973ac73bB381cb5a1f1f222db6671b` | [View](https://testnet.kitescan.ai/address/0xc7640Bf4fC973ac73bB381cb5a1f1f222db6671b) |

## Architecture

```
                          User Query: "Analyze KITE token"
                                      |
                                      v
                    +-----------------------------------+
                    |   ReportAgent (Orchestrator)      |
                    |   Price: $0.0005/report            |
                    |   Creates Verified Intent Mandate  |
                    +---+-------------+-------------+---+
                        |             |             |
            Discovery   |   x402 Pay  |   x402 Pay  |   x402 Pay
                        v             v             v
              +-----------+   +-----------+   +-----------+
              | DataAgent |   | Analyst   |   | AuditAgent|
              | $0.0001   |   | Agent     |   | $0.0001   |
              | Twitter,  |   | $0.0002   |   | Verifies  |
              | CoinGecko,|   | VADER,    |   | quality,  |
              | Whale,    |   | RSI/MACD, |   | freshness |
              | News      |   | Bollinger |   | accuracy  |
              +-----------+   +-----------+   +-----------+
                    |               |               |
                    v               v               v
              [Kite Testnet: Agent Registry + Reputation + Payments]
              [Every tx verifiable at testnet.kitescan.ai]
```

## Kite Integration (All 3 Pillars)

### Pillar 1: Agent Passport (Identity)
Every agent gets a deterministic passport ID registered on-chain:
```python
passport_id = Web3.solidity_keccak(["string"], ["Nexus-DataAgent-v1"])
# Registered in AgentRegistry contract at 0xBf23C1...
```
Each agent has a W3C-inspired DID document accessible at `GET /api/agent-identity/{agent_id}`.

### Pillar 2: x402 Payments (Micropayments)
All agent services are x402-gated. Calling without payment returns HTTP 402:
```json
{
  "error": "X-PAYMENT header is required",
  "accepts": [{
    "scheme": "gokite-aa",
    "network": "kite-testnet",
    "maxAmountRequired": "100000000000000",
    "asset": "0x0fF5393387ad2f9f691FD6Fd28e07E3969e27e63",
    "payTo": "0xaa7144D792d7c87aA72fb3EdC16c982654272036",
    "merchantName": "Nexus-DataAgent-v1",
    "outputSchema": { "input": {...}, "output": {...} },
    "maxTimeoutSeconds": 300
  }],
  "x402Version": 1
}
```
Payments settle via the [Pieverse Facilitator](https://facilitator.pieverse.io) on Kite testnet.

### Pillar 3: Programmable Governance (Verified Intent)
Every query creates a cryptographically-signed **Mandate** that bounds agent spending:

1. **Mandate Creation** -- ECDSA-signed spending authorization with budget, per-tx limits, allowed agents, TTL
2. **Circuit Breaker** -- 7-point validation before every payment (budget, per-tx, allowlist, expiry, reputation, governance)
3. **Audit Trail** -- SHA-256 traceability hash recorded on-chain as a data-bearing transaction

## The Agent Economy

NEXUS ships with **5 built-in agents** plus **3 external marketplace agents** (all running as independent services that register via the marketplace API):

### Built-in Agents (in `backend/agents/`)

| Agent | Role | Earns | Capabilities |
|-------|------|-------|-------------|
| **DataAgent** | Collects real-time data | $0.0001/query | Twitter, prices, whale activity, news |
| **AnalystAgent** | Analyzes data | $0.0002/analysis | VADER sentiment, RSI, MACD, Bollinger Bands |
| **ReportAgent** | Orchestrates everything | $0.0005/report | Discovery, mandate creation, compilation |
| **AuditAgent** | Verifies quality | $0.0001/audit | Freshness, accuracy, consistency checks |
| **AlertAgent** | Monitors thresholds | $0.0001/alert | Price drops, whale moves, sentiment shifts |

### External Marketplace Agents (in `example-agents/`)

These demonstrate the open marketplace -- each runs as a standalone service that self-registers via `POST /api/marketplace/register`. Anyone can build more following these templates.

| Agent | Role | Earns | Capabilities | Data Source |
|-------|------|-------|-------------|-------------|
| **DeFi Agent** | DeFi protocol metrics | $0.0001/query | `defi_data`, `defi_analysis` | [DeFiLlama](https://defillama.com) (free) |
| **DEXScreener Agent** | DEX pair data across 40+ chains | $0.0001/query | `dex_data`, `liquidity_analysis` | [DEXScreener](https://dexscreener.com) (free, no key) |
| **Security Agent** | Rug pull + honeypot detection | $0.0002/query | `token_security`, `rug_detection` | [GoPlus Security](https://gopluslabs.io) (free, no key) |

## How It Works

1. You submit: **"Analyze KITE token sentiment"**
2. **ReportAgent** classifies the query and discovers agents on the registry
3. A **Verified Intent Mandate** is created (ECDSA-signed, budget=$0.0009, TTL=5min)
4. ReportAgent pays **DataAgent** $0.0001 via x402 -- Circuit Breaker validates payment
5. DataAgent fetches real Twitter data, CoinGecko prices, whale activity, news
6. ReportAgent pays **AnalystAgent** $0.0002 -- sentiment (VADER), technicals (RSI/MACD/Bollinger)
7. **AuditAgent** verifies output quality (freshness, accuracy, consistency) -- score: 94/100
8. **Reputation scores update on-chain** based on audit score
9. **Audit trail hash recorded on-chain** -- verifiable at testnet.kitescan.ai
10. Final report delivered -- total cost: **$0.0005**, time: ~10 seconds

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- A free [Groq API key](https://console.groq.com)

### Backend
```bash
cd backend
cp .env.example .env
# Edit .env - add your free Groq API key
pip install -r requirements.txt
python -m backend.main
```
Backend runs on http://localhost:8000

### Frontend
```bash
cd frontend
npm install
npm run dev
```
Dashboard runs on http://localhost:3000

### External Marketplace Agents (Optional but Recommended)

The backend ships with 5 built-in agents. To also run the 3 external marketplace agents (DeFi, DEXScreener, Security), start them after the backend is up:

```bash
# Linux/Mac
cd example-agents && ./start-all.sh

# Windows PowerShell
cd example-agents && ./start-all.ps1
```

Each agent registers itself in the NEXUS marketplace on startup. Now `"Analyze ETH DeFi yields"` will auto-route to the DeFi agent, `"KITE liquidity across DEXs"` to DEXScreener, and `"Is token 0xabc... safe?"` to the Security agent.

### Smart Contracts (Already Deployed)
Contracts are deployed to Kite testnet. To redeploy:
```bash
# Option A: Python
python deploy_contracts.py

# Option B: Hardhat
cd contracts && npm install
npx hardhat run deploy/deploy.js --network kiteTestnet
```

### Run Tests
```bash
cd backend
python -m pytest tests/ -v
```

## Deployment

### Docker
```bash
docker-compose up --build
```

### Manual
- **Frontend**: Deploy `frontend/` to [Vercel](https://vercel.com) (set `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_WS_URL`)
- **Backend**: Deploy with `render.yaml` to [Render](https://render.com) or any Python host

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/query` | POST | Submit analysis query |
| `/api/agents` | GET | List all agents + stats |
| `/api/stats` | GET | Economy-wide metrics |
| `/api/blockchain` | GET | On-chain status + tx hashes |
| `/api/mandates` | GET | Active + completed mandates |
| `/api/audit-trail` | GET | On-chain audit trails |
| `/api/reputation` | GET | Reputation leaderboard |
| `/api/agent-identity/{id}` | GET | DID document for agent |
| `/api/x402-status` | GET | x402 protocol compliance info |
| `/api/marketplace/agents` | GET | Open marketplace agents |
| `/x402/data-agent` | POST | x402-gated DataAgent |
| `/x402/analyst-agent` | POST | x402-gated AnalystAgent |
| `/x402/audit-agent` | POST | x402-gated AuditAgent |
| `/ws` | WebSocket | Real-time event streaming |

## Tech Stack

| Category | Technology | Cost |
|----------|-----------|------|
| **Backend** | Python, FastAPI, LangGraph | Free |
| **Frontend** | Next.js 16, React 19, TailwindCSS 4 | Free |
| **Blockchain** | Solidity 0.8.24, Hardhat, Kite Aero Testnet | Free |
| **LLMs** | Groq (Llama 3.3 70B), Google Gemini, Ollama | Free |
| **Data** | CoinGecko, Google News RSS, CryptoPanic, VADER | Free |
| **Analysis** | Pandas, NumPy (RSI, MACD, Bollinger Bands) | Free |
| **Payments** | x402 protocol, Pieverse Facilitator | Free |
| **Persistence** | SQLite (aiosqlite) | Free |
| **Marketplace Agents** | DeFiLlama, DEXScreener, GoPlus Security | Free, no API keys |

**Total infrastructure cost: $0**

## Project Structure

```
nexus/
  backend/
    agents/           # 5 specialized AI agents
    blockchain/       # Kite chain client + wallet derivation
    verified_intent/  # Mandates, circuit breaker, audit trails
    x402/             # x402 payment protocol (Kite-compliant)
    kite_mcp/         # Kite MCP payment tools
    marketplace/      # Open agent registry + discovery
    data_sources/     # CoinGecko, Twitter, whale, news
    llm/              # Free LLM router (Groq/Gemini/Ollama)
    models/           # Pydantic data models
    websocket/        # Real-time event streaming
    tests/            # Automated test suite
    db.py             # SQLite persistence
    main.py           # FastAPI app (42 endpoints)
  frontend/           # Next.js 16 real-time dashboard
  contracts/          # 4 Solidity smart contracts (deployed)
  example-agents/     # 3 external marketplace agents (self-register via API)
    defi-agent/         # DeFiLlama TVL/yield data
    dexscreener-agent/  # DEX pair data, liquidity spread
    security-agent/     # GoPlus rug pull + honeypot detection
    start-all.sh/.ps1   # Launch all external agents
  example-agents/     # Template for external marketplace agents
  twitter-service/    # Node.js Twitter data microservice
```

## Team

Built for the Kite AI Global Hackathon 2026 by Encode Club.
